"""Splink probabilistic linkage of SEC filers to GLEIF LEI records, on DuckDB.

Inputs come from the warehouse (staging views); output is data/mdm/company_matches.parquet,
which dbt reads as source mdm.company_matches (set BW_HAS_MDM=true).

Thresholds (ADR-006): match probability >= UPPER -> "match"; between LOWER and UPPER ->
"review" (stewardship queue); below LOWER -> dropped.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd
import splink.comparison_level_library as cll
import splink.comparison_library as cl
from splink import DuckDBAPI, Linker, SettingsCreator, block_on

from mdm.standardise import sec_country, standardise_city, standardise_name, standardise_postal_code

log = logging.getLogger(__name__)

UPPER = 0.90
LOWER = 0.50
MODEL_VERSION = "splink4-v1"

COLUMNS = [
    "unique_id",
    "source",
    "name_orig",
    "name_std",
    "name_prefix3",
    "city_std",
    "zip5",
    "zip3",
    "country",
    "tickers",
    "other_names",
]


@dataclass
class MatchResult:
    predictions: pd.DataFrame
    matches: pd.DataFrame
    linker: Linker


def prepare_sec(df: pd.DataFrame) -> pd.DataFrame:
    """df columns: cik, company_name, business_city, business_state, business_zip, tickers (comma list)."""
    out = pd.DataFrame(
        {
            "unique_id": "CIK:" + df["cik"].astype(str),
            "source": "sec",
            "name_orig": df["company_name"],
            "name_std": df["company_name"].map(standardise_name),
            "city_std": df["business_city"].map(standardise_city),
            "country": df["business_state"].map(sec_country),
        }
    )
    out["zip5"] = [standardise_postal_code(z, c) for z, c in zip(df["business_zip"], out["country"], strict=True)]
    out["tickers"] = df["tickers"].fillna("").map(lambda s: [t.strip().upper() for t in s.split(",") if t.strip()])
    out["other_names"] = [[] for _ in range(len(out))]
    return _finish(out)


def prepare_gleif(df: pd.DataFrame) -> pd.DataFrame:
    """df columns: lei, legal_name, other_name_1..3, hq_city, hq_country, hq_postal_code."""
    others = df[["other_name_1", "other_name_2", "other_name_3"]].apply(
        lambda r: [str(v).upper() for v in r if isinstance(v, str) and v], axis=1
    )
    out = pd.DataFrame(
        {
            "unique_id": "LEI:" + df["lei"],
            "source": "gleif",
            "name_orig": df["legal_name"],
            "name_std": df["legal_name"].map(standardise_name),
            "city_std": df["hq_city"].map(standardise_city),
            "country": df["hq_country"],
        }
    )
    out["zip5"] = [standardise_postal_code(z, c) for z, c in zip(df["hq_postal_code"], df["hq_country"], strict=True)]
    out["tickers"] = [[] for _ in range(len(out))]
    out["other_names"] = others
    return _finish(out)


def _finish(out: pd.DataFrame) -> pd.DataFrame:
    out["name_prefix3"] = out["name_std"].str[:3]
    out["zip3"] = out["zip5"].str[:3]
    return out[COLUMNS]


def settings() -> SettingsCreator:
    ticker_in_other_names = cl.CustomComparison(
        output_column_name="ticker",
        comparison_levels=[
            cll.CustomLevel("len(tickers_l) = 0 and len(tickers_r) = 0", label_for_charts="no ticker").configure(
                is_null_level=True
            ),
            cll.CustomLevel(
                "list_has_any(tickers_l, other_names_r) or list_has_any(tickers_r, other_names_l)",
                label_for_charts="ticker found in GLEIF other names",
            ),
            cll.ElseLevel(),
        ],
    )
    postal = cl.CustomComparison(
        output_column_name="postal_code",
        comparison_levels=[
            cll.NullLevel("zip5"),
            cll.ExactMatchLevel("zip5"),
            cll.ExactMatchLevel("zip3"),
            cll.ElseLevel(),
        ],
    )
    return SettingsCreator(
        link_type="link_only",
        unique_id_column_name="unique_id",
        blocking_rules_to_generate_predictions=[
            block_on("country", "name_prefix3"),
            block_on("zip5"),
        ],
        comparisons=[
            cl.JaroWinklerAtThresholds("name_std", [0.97, 0.92, 0.85]),
            cl.JaroWinklerAtThresholds("city_std", [0.92]),
            postal,
            cl.ExactMatch("country"),
            ticker_in_other_names,
        ],
        retain_intermediate_calculation_columns=True,
        retain_matching_columns=True,
    )


def train_and_predict(
    sec: pd.DataFrame, gleif: pd.DataFrame, report_dir: Path | None = None, max_pairs: float = 5e6
) -> MatchResult:
    con = duckdb.connect()
    db_api = DuckDBAPI(connection=con)
    linker = Linker([sec, gleif], settings(), db_api, input_table_aliases=["sec", "gleif"])
    linker.training.estimate_probability_two_random_records_match([block_on("name_std", "country")], recall=0.7)
    linker.training.estimate_u_using_random_sampling(max_pairs=max_pairs, seed=42)
    # EM twice with different blocking, so every comparison gets m estimates (spec step 4)
    linker.training.estimate_parameters_using_expectation_maximisation(block_on("country", "name_prefix3"))
    linker.training.estimate_parameters_using_expectation_maximisation(block_on("zip5"))
    predictions = linker.inference.predict(threshold_match_probability=LOWER).as_pandas_dataframe()
    if report_dir:
        report_dir.mkdir(parents=True, exist_ok=True)
        linker.visualisations.match_weights_chart().save(str(report_dir / "match_weights_chart.html"))
        linker.misc.save_model_to_json(str(report_dir / "splink_model.json"), overwrite=True)
    return MatchResult(predictions, to_matches(predictions), linker)


def to_matches(predictions: pd.DataFrame) -> pd.DataFrame:
    """One best LEI per SEC filer; status 'match' above UPPER, 'review' between thresholds."""
    if predictions.empty:
        return pd.DataFrame(
            columns=[
                "source_company_bk_type",
                "source_company_bk",
                "lei",
                "match_probability",
                "match_weight",
                "match_status",
                "model_version",
            ]
        )
    p = predictions.copy()
    sec_is_l = p["unique_id_l"].str.startswith("CIK:")
    p["cik_uid"] = p["unique_id_l"].where(sec_is_l, p["unique_id_r"])
    p["lei_uid"] = p["unique_id_r"].where(sec_is_l, p["unique_id_l"])
    p = p.sort_values(["cik_uid", "match_probability"], ascending=[True, False])
    best = p.drop_duplicates("cik_uid")
    return pd.DataFrame(
        {
            "source_company_bk_type": "CIK",
            "source_company_bk": best["cik_uid"].str.removeprefix("CIK:"),
            "lei": best["lei_uid"].str.removeprefix("LEI:"),
            "match_probability": best["match_probability"],
            "match_weight": best["match_weight"],
            "match_status": ["match" if v >= UPPER else "review" for v in best["match_probability"]],
            "model_version": MODEL_VERSION,
        }
    ).reset_index(drop=True)


def load_inputs(warehouse: Path, gleif_countries: tuple[str, ...] = ("US",)) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read SEC profiles and GLEIF entities from the local warehouse (DuckDB)."""
    con = duckdb.connect(str(warehouse), read_only=True)
    # Only SEC registrants that filed a financial statement in the warehouse: the submissions
    # file also lists ~1 M insiders, funds and individuals that never appear in the marts and
    # would make the candidate pairs explode on the full data.
    sec = con.execute("""
        select c.cik, c.company_name, c.business_city, c.business_state, c.business_zip, c.tickers
        from staging.stg_sec_submissions__companies as c
        where c.hk_company in (
            select p.hk_company from business_vault.bv_company_periods as p
        )
    """).df()
    placeholders = ", ".join("?" for _ in gleif_countries)
    gleif = con.execute(
        f"""
        select lei, legal_name, other_name_1, other_name_2, other_name_3, hq_city, hq_country, hq_postal_code
        from staging.stg_gleif__entities
        where hq_country in ({placeholders}) or legal_country in ({placeholders})
    """,
        list(gleif_countries) * 2,
    ).df()
    return sec, gleif


def run(warehouse: Path, out_dir: Path) -> pd.DataFrame:
    sec_raw, gleif_raw = load_inputs(warehouse)
    result = train_and_predict(prepare_sec(sec_raw), prepare_gleif(gleif_raw), out_dir / "reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    result.matches.to_parquet(out_dir / "company_matches.parquet", index=False)
    result.predictions.to_parquet(out_dir / "candidate_pairs.parquet", index=False)
    log.info("matches: %s", result.matches["match_status"].value_counts().to_dict())
    return result.matches
