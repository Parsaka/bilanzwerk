"""Check the bankruptcy label against the text of the 8-K.

The main label (ADR-001) is an 8-K whose EDGAR item list contains 1.03. Reading the filings
behind the case studies showed two ways such a filing can be a wrong label:

* the item list is wrong: the text has no Item 1.03 (J C Penney, 28.01.2014, accession
  0001166126-14-000005, is an amended tax-benefit rights plan under Item 3.03);
* the debtor is a subsidiary, not the filer (FirstEnergy, 05.04.2018: FirstEnergy Solutions and
  FENOC, "each wholly owned subsidiaries of FirstEnergy Corp.").

This module fetches the first document of every such filing from EDGAR, looks for Item 1.03 in
the text and reads the sentence that names the debtors. It reports and does not relabel: the
label stays as fixed in ADR-001 before the first model, and the counts are published next to
the result. The debtor test is a heuristic on wording; the snippet of every filing is kept so a
person can check any row.
"""

from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

log = logging.getLogger(__name__)

ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{acc}.txt"
# The 8-K body is the first document of the submission; exhibits follow. Reading this many bytes
# is enough for the body and keeps large filings (some carry 80 documents) cheap.
MAX_BYTES = 400_000

_TEXT = re.compile(r"<TEXT>(.*?)(?:</TEXT>|$)", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_ITEM = re.compile(r"item\s*1\s*\.\s*03\b", re.I)
_HEADING = re.compile(r"item\s*1\s*\.\s*03\s*\.?\s*[-\u2013\u2014:]?\s*bankruptcy\s+or\s+receivership", re.I)
# the verb that names the debtors: "X ... filed voluntary petitions", "... commenced cases"
_FILED = re.compile(r"\b(filed|commenced|was\s+placed|were\s+placed|consented)\b", re.I)
# the filer is among the debtors: "X Inc. and certain of its subsidiaries filed ..."
_FILER_AND_SUBS = re.compile(
    r"\band\s+((certain|all|each|substantially\s+all|some|several|most|\w+)\s+(of\s+)?)?(its|their)\s+"
    r"([\w-]+\s+){0,3}subsidiar",
    re.I,
)
# only a subsidiary is the debtor: "..., wholly owned subsidiaries of X, filed", "the Company's
# subsidiary X filed", "our subsidiary X filed"
_SUBSIDIARY = re.compile(
    r"subsidiar(y|ies)\s+of\b|(company|registrant|corporation)[\u2019']s\s+([\w-]+\s+){0,3}subsidiar"
    r"|\b(its|our)\s+([\w-]+\s+){0,3}subsidiar",
    re.I,
)
# how much text before the verb holds its subject
_SUBJECT_CHARS = 450


@dataclass(frozen=True)
class Verdict:
    item_in_text: bool
    debtor: str  # filer | subsidiary_only | unclear | no_item
    snippet: str


def body_text(raw: str) -> str:
    """Plain text of the first document of an EDGAR full submission (.txt)."""
    m = _TEXT.search(raw)
    text = m.group(1) if m else raw
    return _SPACE.sub(" ", html.unescape(_TAG.sub(" ", text))).strip()


def classify(body: str) -> Verdict:
    """Is Item 1.03 in the text, and is the filer itself among the debtors?

    The subject of the first "filed"/"commenced" after the Item 1.03 heading is read: "X and
    certain of its subsidiaries" counts as the filer; "a subsidiary of X", "the Company's
    subsidiary" or "its subsidiary" without the filer counts as subsidiary only. Anything else
    with a filing verb counts as the filer, and a section without one as unclear.
    """
    heading = _HEADING.search(body)
    any_item = heading or _ITEM.search(body)
    if not any_item:
        return Verdict(False, "no_item", body[:300])
    section = body[any_item.end() : any_item.end() + 3000]
    verb = _FILED.search(section)
    if not verb:
        return Verdict(True, "unclear", section[:600])
    subject = section[max(0, verb.start() - _SUBJECT_CHARS) : verb.end()]
    snippet = section[max(0, verb.start() - _SUBJECT_CHARS) : verb.end() + 150]
    if _FILER_AND_SUBS.search(subject):
        return Verdict(True, "filer", snippet)
    if _SUBSIDIARY.search(subject):
        return Verdict(True, "subsidiary_only", snippet)
    return Verdict(True, "filer", snippet)


def label_filings(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Every 8-K behind the main label, with the CIK that filed it."""
    df = con.execute("""
        select e.company_id, e.event_date, e.filing, max(hc.company_bk) as filer_cik
        from marts.fact_event as e
        left join raw_vault.hub_filing as hf on hf.filing_bk = e.filing
        left join raw_vault.link_filing_company as l on l.hk_filing = hf.hk_filing
        left join raw_vault.hub_company as hc on hc.hk_company = l.hk_company and hc.company_bk_type = 'CIK'
        where e.is_main_label = 1 and e.filing is not null
        group by e.company_id, e.event_date, e.filing
        order by e.event_date, e.filing
    """).df()
    first = df.groupby("company_id")["event_date"].transform("min")
    df["is_first_event"] = (df["event_date"] == first).astype(int)
    return df


def fetch(session, cik: str | int, accession: str) -> str:
    url = ARCHIVE.format(cik=int(cik), acc_nodash=accession.replace("-", ""), acc=accession)
    with session.get(url, stream=True) as response:
        chunks, size = [], 0
        for chunk in response.iter_content(chunk_size=1 << 16):
            chunks.append(chunk)
            size += len(chunk)
            if size >= MAX_BYTES:
                break
    return b"".join(chunks).decode("utf-8", errors="ignore")


def summarise(df: pd.DataFrame) -> dict:
    done = df[df["fetched"] == 1]
    first = done[done["is_first_event"] == 1]

    def counts(frame: pd.DataFrame) -> dict:
        c = frame["debtor"].value_counts().to_dict()
        return {
            "filings": len(frame),
            "item_missing_in_text": int(c.get("no_item", 0)),
            "subsidiary_only": int(c.get("subsidiary_only", 0)),
            "unclear": int(c.get("unclear", 0)),
            "filer_is_debtor": int(c.get("filer", 0)),
        }

    return {
        "filings_in_label": len(df),
        "fetched": len(done),
        "not_fetched": int(len(df) - len(done)),
        "all_filings": counts(done),
        "first_event_per_company": counts(first),
        "method": "analysis/label_audit.py: Item 1.03 searched in the first document; debtor sentence read by "
        "wording rules (heuristic, see snippet per row). Labels are not changed.",
    }


def run(warehouse: Path, out_dir: Path, session=None, limit: int | None = None) -> dict:
    con = duckdb.connect(str(warehouse), read_only=True)
    df = label_filings(con)
    con.close()
    if limit:
        df = df.head(limit)
    if session is None:
        from ingestion.common.config import get_settings
        from ingestion.common.http import PoliteSession

        session = PoliteSession(get_settings())
    rows = []
    for i, r in enumerate(df.itertuples(index=False)):
        rec = {"fetched": 0, "item_in_text": None, "debtor": None, "snippet": None}
        if pd.notna(r.filer_cik):
            try:
                v = classify(body_text(fetch(session, r.filer_cik, r.filing)))
                rec = {"fetched": 1, "item_in_text": int(v.item_in_text), "debtor": v.debtor, "snippet": v.snippet}
            except Exception as exc:
                log.warning("label audit: %s %s: %s", r.filer_cik, r.filing, exc)
        rows.append(rec)
        if i % 250 == 0:
            log.info("label audit: %d of %d filings", i, len(df))
    out = pd.concat([df.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    out_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_dir / "label_audit.csv", index=False)
    summary = summarise(out)
    (out_dir / "label_audit.json").write_text(json.dumps(summary, indent=2))
    return summary
