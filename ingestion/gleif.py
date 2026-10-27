"""GLEIF LEI golden copy loader (LEI-CDF level 1 and relationship records, CSV variant).

Full golden copy once, then daily delta files. Privacy by design: only an allowlist of columns
is kept. Mail-routing and additional address lines (which can hold names of contact persons)
are never landed, and "c/o" / "attn" fragments are removed from address lines.
See docs/data-classification.md.
"""

from __future__ import annotations

import logging
import re
import zipfile
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

from ingestion.common.config import Settings
from ingestion.common.http import PoliteSession, sha256_file
from ingestion.common.manifest import STATUS_FAILED, STATUS_LOADED, Manifest, ManifestRow
from ingestion.common.parquet import write_partition

log = logging.getLogger(__name__)

SOURCE = "gleif"
PUBLISHES_URL = "https://goldencopy.gleif.org/api/v2/golden-copies/publishes/latest"

N_OTHER_NAMES = 5

LEI_COLUMNS: dict[str, str] = {
    "LEI": "lei",
    "Entity.LegalName": "legal_name",
    **{f"Entity.OtherEntityNames.OtherEntityName.{i}": f"other_name_{i}" for i in range(1, N_OTHER_NAMES + 1)},
    "Entity.LegalAddress.FirstAddressLine": "legal_address_line",
    "Entity.LegalAddress.City": "legal_city",
    "Entity.LegalAddress.Region": "legal_region",
    "Entity.LegalAddress.Country": "legal_country",
    "Entity.LegalAddress.PostalCode": "legal_postal_code",
    "Entity.HeadquartersAddress.FirstAddressLine": "hq_address_line",
    "Entity.HeadquartersAddress.City": "hq_city",
    "Entity.HeadquartersAddress.Region": "hq_region",
    "Entity.HeadquartersAddress.Country": "hq_country",
    "Entity.HeadquartersAddress.PostalCode": "hq_postal_code",
    "Entity.LegalJurisdiction": "legal_jurisdiction",
    "Entity.EntityCategory": "entity_category",
    "Entity.LegalForm.EntityLegalFormCode": "legal_form_code",
    "Entity.LegalForm.OtherLegalForm": "legal_form_other",
    "Entity.EntityStatus": "entity_status",
    "Registration.InitialRegistrationDate": "initial_registration_date",
    "Registration.LastUpdateDate": "last_update_date",
    "Registration.RegistrationStatus": "registration_status",
    "Registration.NextRenewalDate": "next_renewal_date",
}

RR_COLUMNS: dict[str, str] = {
    "Relationship.StartNode.NodeID": "child_lei",
    "Relationship.EndNode.NodeID": "parent_lei",
    "Relationship.RelationshipType": "relationship_type",
    "Relationship.RelationshipStatus": "relationship_status",
    "Registration.RegistrationStatus": "registration_status",
    "Registration.LastUpdateDate": "last_update_date",
}

ADDRESS_FIELDS = ("legal_address_line", "hq_address_line")
# "c/o Jane Doe", "Attn: John Smith", "z. Hd. Herr Müller" up to the next comma
PERSON_FRAGMENT = re.compile(r"(?i)\b(c/o|attn\.?:?|attention:?|z\.\s?hd\.?)\s*[^,]*,?\s*")


def scrub_address(values: pa.ChunkedArray | pa.Array) -> pa.Array:
    cleaned = pc.replace_substring_regex(values, PERSON_FRAGMENT.pattern, "")
    cleaned = pc.utf8_trim_whitespace(cleaned)
    return pc.if_else(pc.equal(cleaned, ""), pa.scalar(None, pa.string()), cleaned)


def _read_csv_stream(fh, columns: dict[str, str]):
    reader = pacsv.open_csv(
        fh,
        read_options=pacsv.ReadOptions(block_size=1 << 25),
        convert_options=pacsv.ConvertOptions(
            include_columns=list(columns),
            include_missing_columns=True,
            column_types={c: pa.string() for c in columns},
            strings_can_be_null=True,
        ),
    )
    for batch in reader:
        tbl = pa.Table.from_batches([batch]).rename_columns([columns[c] for c in batch.schema.names])
        yield tbl


def transform_lei(tbl: pa.Table) -> pa.Table:
    for col in ADDRESS_FIELDS:
        idx = tbl.schema.get_field_index(col)
        tbl = tbl.set_column(idx, col, scrub_address(tbl.column(col)))
    return tbl


def land_file(
    path: Path,
    kind: str,
    variant: str,
    publish_date: str,
    settings: Settings,
    manifest: Manifest,
    url: str | None = None,
) -> int:
    """kind: 'lei2' or 'rr'; variant: 'full' or 'delta'."""
    digest = sha256_file(path)
    if manifest.is_loaded(SOURCE, digest):
        return 0
    columns = LEI_COLUMNS if kind == "lei2" else RR_COLUMNS
    table_name = "entities" if kind == "lei2" else "relationships"
    total = 0
    try:
        with zipfile.ZipFile(path) as zf:
            member = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
            with zf.open(member) as fh:
                for i, chunk in enumerate(_read_csv_stream(fh, columns)):
                    tbl = transform_lei(chunk) if kind == "lei2" else chunk
                    write_partition(
                        tbl,
                        settings.raw_root / SOURCE / table_name,
                        {"variant": variant, "publish_date": publish_date},
                        name=f"part-{i:05d}",
                    )
                    total += tbl.num_rows
    except Exception as exc:
        manifest.record(
            ManifestRow(
                SOURCE,
                path.name,
                publish_date,
                url,
                digest,
                path.stat().st_size,
                None,
                table_name,
                STATUS_FAILED,
                str(exc)[:1000],
            )
        )
        raise
    manifest.record(
        ManifestRow(SOURCE, path.name, publish_date, url, digest, path.stat().st_size, total, table_name, STATUS_LOADED)
    )
    return total


def _csv_url(block: dict) -> str:
    return block["csv"]["url"]


def run(settings: Settings, full: bool = False, session: PoliteSession | None = None) -> dict[str, int]:
    """full=True loads the full golden copy (first run); otherwise the last-day delta."""
    session = session or PoliteSession(settings)
    manifest = Manifest(settings.manifest_path)
    meta = session.get(PUBLISHES_URL).json()["data"]
    publish_date = (meta.get("publish_date") or date.today().isoformat())[:10]
    variant = "full" if full or not manifest.loaded_files(SOURCE) else "delta"
    out = {}
    for kind in ("lei2", "rr"):
        block = meta[kind]["full_file"] if variant == "full" else meta[kind]["delta_files"]["LastDay"]
        url = _csv_url(block)
        target = settings.download_root / SOURCE / f"{kind}_{variant}_{publish_date}.csv.zip"
        if not target.exists():
            session.download(url, target)
        out[kind] = land_file(target, kind, variant, publish_date, settings, manifest, url)
    return out
