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

from mdm.standardise import (
    legal_form,
    name_marks,
    sec_country,
    standardise_city,
    standardise_name,
    standardise_postal_code,
)

log = logging.getLogger(__name__)

UPPER = 0.90
LOWER = 0.50
MODEL_VERSION = "splink4-v3"
# An automatic "match" needs strong name evidence: the same standardised name or a near-typo.
# Every other name level (series marks differ, one name is the other plus words, looser
# Jaro-Winkler) goes to the stewardship queue however close the address is: fund families and
# subsidiaries share addresses, which breaks the independence the Fellegi-Sunter weights assume.
# Of the 85 hand-labelled matches none sat on those levels (README, "Model v3").
AUTO_MATCH_LEVELS = ("exact (spaces ignored)", "Jaro-Winkler >= 0.97")
LABELLED_PAIRS = Path("mdm/labelled_pairs.csv")

COLUMNS = [
    "unique_id",
    "source",
    "name_orig",
    "name_std",
    "name_prefix3",
    "name_marks",
    "legal_form",
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
            "legal_form": df["company_name"].map(legal_form),
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
            "legal_form": df["legal_name"].map(legal_form),
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
    out["name_marks"] = out["name_std"].map(name_marks)
    out["zip3"] = out["zip5"].str[:3]
    return out[COLUMNS]


def name_comparison() -> cl.CustomComparison:
    """Name levels, strongest first. Exact also accepts the same letters without spaces
    ("AMAZONCOM" vs "AMAZON COM"). Different series/vehicle marks and one name being the other
    plus trailing words (a subsidiary or fund of it) come before the fuzzy levels, so a high
    Jaro-Winkler score cannot outvote them."""
    compact = "replace(name_std_l, ' ', '') = replace(name_std_r, ' ', '')"
    extends = "(starts_with(name_std_l || ' ', name_std_r || ' ') or starts_with(name_std_r || ' ', name_std_l || ' '))"
    return cl.CustomComparison(
        output_column_name="name_std",
        comparison_levels=[
            cll.NullLevel("name_std"),
            cll.CustomLevel(f"name_std_l = name_std_r or {compact}", label_for_charts="exact (spaces ignored)"),
            cll.CustomLevel("name_marks_l <> name_marks_r", label_for_charts="series or vehicle marks differ"),
            cll.CustomLevel(extends, label_for_charts="one name is the other plus words"),
            cll.JaroWinklerLevel("name_std", 0.97).configure(label_for_charts="Jaro-Winkler >= 0.97"),
            cll.JaroWinklerLevel("name_std", 0.92).configure(label_for_charts="Jaro-Winkler >= 0.92"),
            cll.JaroWinklerLevel("name_std", 0.85).configure(label_for_charts="Jaro-Winkler >= 0.85"),
            cll.ElseLevel(),
        ],
    )


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
            name_comparison(),
            cl.JaroWinklerAtThresholds("city_std", [0.92]),
            postal,
            cl.ExactMatch("country"),
            cl.ExactMatch("legal_form"),
            ticker_in_other_names,
        ],
        retain_intermediate_calculation_columns=True,
        retain_matching_columns=True,
        # the reviewer needs the names as filed, not only the standardised ones
        additional_columns_to_retain=["name_orig", "tickers", "other_names"],
    )


def train_and_predict(
    sec: pd.DataFrame,
    gleif: pd.DataFrame,
    report_dir: Path | None = None,
    max_pairs: float = 3e7,
    labels: pd.DataFrame | None = None,
) -> MatchResult:
    """Train and predict.

    With hand labels (mdm/labelled_pairs.csv), the name m probabilities come from the labelled
    matches (Laplace +1 per level) and EM, blocked on the exact name, trains the address and legal
    form comparisons. Unsupervised EM alone learned the name m from fund families sharing one
    address and gave an exact name less weight than a shared ZIP code (model v2, see README).
    Without labels (CI fixture) the model falls back to EM on two blockings.
    """
    con = duckdb.connect()
    db_api = DuckDBAPI(connection=con)
    aliases = ["sec", "gleif"]
    linker = Linker([sec, gleif], settings(), db_api, input_table_aliases=aliases)
    linker.training.estimate_probability_two_random_records_match([block_on("name_std", "country")], recall=0.7)
    linker.training.estimate_u_using_random_sampling(max_pairs=max_pairs, seed=42)
    positives = _labelled_matches(labels)
    if positives is not None:
        linker.table_management.register_table(positives, "bw_labelled_matches", overwrite=True)
        linker.training.estimate_m_from_pairwise_labels("bw_labelled_matches")
        model = linker.misc.save_model_to_json()
        smooth_name_m(model, len(positives))
        # a fresh connection: the first linker has registered the input tables under these aliases
        linker = Linker([sec, gleif], model, DuckDBAPI(connection=duckdb.connect()), input_table_aliases=aliases)
        linker.training.estimate_parameters_using_expectation_maximisation(block_on("name_std"))
    else:
        # EM twice with different blocking, so every comparison gets m estimates (spec step 4)
        linker.training.estimate_parameters_using_expectation_maximisation(block_on("country", "name_prefix3"))
        linker.training.estimate_parameters_using_expectation_maximisation(block_on("zip5"))
    predictions = linker.inference.predict(threshold_match_probability=LOWER).as_pandas_dataframe()
    if report_dir:
        report_dir.mkdir(parents=True, exist_ok=True)
        linker.visualisations.match_weights_chart().save(str(report_dir / "match_weights_chart.html"))
        linker.misc.save_model_to_json(str(report_dir / "splink_model.json"), overwrite=True)
    return MatchResult(predictions, to_matches(predictions), linker)


def _labelled_matches(labels: pd.DataFrame | None) -> pd.DataFrame | None:
    """Pairs labelled 1, in the shape Splink's estimate_m_from_pairwise_labels reads."""
    if labels is None:
        return None
    pos = labels[labels["is_match"].astype(str).str.replace(r"\.0$", "", regex=True) == "1"]
    if pos.empty:
        return None

    def side(uid: pd.Series) -> pd.Series:
        return uid.str.startswith("CIK:").map({True: "sec", False: "gleif"})

    return pd.DataFrame(
        {
            "source_dataset_l": side(pos["unique_id_l"]).to_numpy(),
            "unique_id_l": pos["unique_id_l"].to_numpy(),
            "source_dataset_r": side(pos["unique_id_r"]).to_numpy(),
            "unique_id_r": pos["unique_id_r"].to_numpy(),
        }
    )


def smooth_name_m(model: dict, n_matches: int) -> None:
    """Laplace +1 on the name levels: a level no labelled match fell into gets a small m instead
    of none (which Splink would treat as no evidence at all)."""
    levels = [
        lvl
        for comp in model["comparisons"]
        if comp["output_column_name"] == "name_std"
        for lvl in comp["comparison_levels"]
        if not lvl.get("is_null_level")
    ]
    counts = [round((lvl.get("m_probability") or 0.0) * n_matches) for lvl in levels]
    for lvl, count in zip(levels, counts, strict=True):
        lvl["m_probability"] = (count + 1) / (n_matches + len(levels))


def _auto_match_gammas() -> set[int]:
    """gamma_name_std values of AUTO_MATCH_LEVELS (Splink numbers levels from the bottom, null = -1)."""
    levels = name_comparison().get_comparison("duckdb").as_dict()["comparison_levels"]
    non_null = [lvl for lvl in levels if not lvl.get("is_null_level")]
    return {len(non_null) - 1 - i for i, lvl in enumerate(non_null) if lvl.get("label_for_charts") in AUTO_MATCH_LEVELS}


def to_matches(predictions: pd.DataFrame) -> pd.DataFrame:
    """One best LEI per SEC filer; status 'match' above UPPER, 'review' between thresholds.
    A pair that needs a steward (`needs_review`) is 'review' at most."""
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
    # Several LEIs can tie for the best probability (same name and address, e.g. a company and
    # its branch). The pick is then made by LEI so that two runs give the same golden record
    # (an unstable sort gave 170 of 5 384 filers another LEI on rerun), and the tie itself is a
    # steward's decision, so such a filer is never an automatic match.
    p["_p"] = p["match_probability"].round(9)  # float noise between runs must not reorder ties
    p["_tied"] = tied_best(p)
    p = p.sort_values(["cik_uid", "_p", "lei_uid"], ascending=[True, False, True], kind="mergesort")
    best = p.drop_duplicates("cik_uid")
    best_tied = best["_tied"].tolist()
    return pd.DataFrame(
        {
            "source_company_bk_type": "CIK",
            "source_company_bk": best["cik_uid"].str.removeprefix("CIK:"),
            "lei": best["lei_uid"].str.removeprefix("LEI:"),
            "match_probability": best["match_probability"],
            "match_weight": best["match_weight"],
            "match_status": [
                "match" if v >= UPPER and not ruled else "review"
                for v, ruled in zip(
                    best["match_probability"],
                    [r or t for r, t in zip(needs_review(best), best_tied, strict=True)],
                    strict=True,
                )
            ],
            "model_version": MODEL_VERSION,
        }
    ).reset_index(drop=True)


def tied_best(pairs: pd.DataFrame) -> pd.Series:
    """True for a pair whose SEC filer has more than one LEI at the best probability."""
    sec_is_l = pairs["unique_id_l"].str.startswith("CIK:")
    cik = pairs["unique_id_l"].where(sec_is_l, pairs["unique_id_r"])
    prob = pairs["match_probability"].round(9)
    best = prob.groupby(cik).transform("max")
    n_best = (prob == best).groupby(cik).transform("sum")
    return (prob == best) & (n_best > 1)


def needs_review(pairs: pd.DataFrame) -> list[bool]:
    """True where a person must decide whatever the probability: the name is not on an
    AUTO_MATCH_LEVELS level, or both legal forms are known and differ ("Amazon.com, LLC" vs
    "Amazon.com, Inc."; of the 9 labelled exact-name pairs like that, 4 were matches, 5 not)."""
    if "gamma_name_std" not in pairs.columns:
        return [False] * len(pairs)
    auto = _auto_match_gammas()
    weak_name = ~pairs["gamma_name_std"].astype(int).isin(auto)
    if {"legal_form_l", "legal_form_r"} <= set(pairs.columns):
        forms_differ = (
            pairs["legal_form_l"].notna()
            & pairs["legal_form_r"].notna()
            & (pairs["legal_form_l"] != pairs["legal_form_r"])
        )
    else:
        forms_differ = pd.Series(False, index=pairs.index)
    return (weak_name | forms_differ).tolist()


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


def run(warehouse: Path, out_dir: Path, inputs: Path | None = None) -> pd.DataFrame:
    """Match from the warehouse, or from the inputs a real-data run saved (`inputs/sec.parquet`,
    `inputs/gleif.parquet`), so the model can be changed and rerun without rebuilding the vault."""
    if inputs:
        sec_raw, gleif_raw = pd.read_parquet(inputs / "sec.parquet"), pd.read_parquet(inputs / "gleif.parquet")
    else:
        sec_raw, gleif_raw = load_inputs(warehouse)
        (out_dir / "inputs").mkdir(parents=True, exist_ok=True)
        sec_raw.to_parquet(out_dir / "inputs" / "sec.parquet", index=False)
        gleif_raw.to_parquet(out_dir / "inputs" / "gleif.parquet", index=False)
    labels = pd.read_csv(LABELLED_PAIRS, dtype={"is_match": str}) if LABELLED_PAIRS.exists() else None
    result = train_and_predict(prepare_sec(sec_raw), prepare_gleif(gleif_raw), out_dir / "reports", labels=labels)
    out_dir.mkdir(parents=True, exist_ok=True)
    result.matches.to_parquet(out_dir / "company_matches.parquet", index=False)
    result.predictions.to_parquet(out_dir / "candidate_pairs.parquet", index=False)
    log.info("matches: %s", result.matches["match_status"].value_counts().to_dict())
    return result.matches
