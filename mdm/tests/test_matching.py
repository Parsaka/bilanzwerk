import pandas as pd

from mdm import evaluate, matching


def _sec():
    return pd.DataFrame(
        {
            "cik": [1, 2, 3],
            "company_name": ["APPLE INC", "ALPHABET INC.", "TINY WIDGETS CORP"],
            "business_city": ["CUPERTINO", "MOUNTAIN VIEW", "AUSTIN"],
            "business_state": ["CA", "CA", "TX"],
            "business_zip": ["95014", "94043", "73301"],
            "tickers": ["AAPL", "GOOGL,GOOG", ""],
        }
    )


def _gleif():
    return pd.DataFrame(
        {
            "lei": ["HWUPKR0MPOU8FGXBT394", "5493006MHB84DD0ZWV18", "529900XXXXXXXXXXXX01"],
            "legal_name": ["Apple Inc.", "Alphabet Inc.", "Apple Hospitality REIT, Inc."],
            "other_name_1": ["AAPL", None, None],
            "other_name_2": [None, None, None],
            "other_name_3": [None, None, None],
            "hq_city": ["Cupertino", "Mountain View", "Richmond"],
            "hq_country": ["US", "US", "US"],
            "hq_postal_code": ["95014", "94043-1351", "23219"],
        }
    )


def test_prepare_produces_identical_schemas():
    s, g = matching.prepare_sec(_sec()), matching.prepare_gleif(_gleif())
    assert list(s.columns) == list(g.columns) == matching.COLUMNS
    assert s.loc[0, "name_std"] == g.loc[0, "name_std"] == "APPLE"
    assert g.loc[1, "zip5"] == "94043"


def test_to_matches_picks_best_lei_and_sets_status():
    preds = pd.DataFrame(
        {
            "unique_id_l": ["CIK:1", "CIK:1", "LEI:L2"],
            "unique_id_r": ["LEI:L1", "LEI:L3", "CIK:2"],
            "match_probability": [0.99, 0.6, 0.7],
            "match_weight": [10.0, 1.0, 2.0],
        }
    )
    m = matching.to_matches(preds).set_index("source_company_bk")
    assert m.loc["1", "lei"] == "L1" and m.loc["1", "match_status"] == "match"
    assert m.loc["2", "lei"] == "L2" and m.loc["2", "match_status"] == "review"


def test_precision_recall_counts_only_labelled_rows():
    labelled = pd.DataFrame({"match_probability": [0.95, 0.92, 0.6, 0.55, 0.97], "is_match": ["1", "0", "1", "0", ""]})
    r = evaluate.precision_recall(labelled, 0.9)
    assert (r["tp"], r["fp"], r["fn"], r["n_labelled"]) == (1, 1, 1, 4)
    assert r["precision"] == 0.5 and r["recall"] == 0.5


def test_settings_build():
    assert matching.settings() is not None


def test_sample_fills_short_bands_from_the_others():
    from mdm.evaluate import sample

    # 10 pairs in the lowest band, 500 in the top band, nothing in between
    probs = [0.55] * 10 + [0.995] * 500
    pairs = pd.DataFrame(
        {"unique_id_l": range(len(probs)), "unique_id_r": range(len(probs)), "match_probability": probs}
    )
    out = sample(pairs, 300)
    assert len(out) == 300
    assert (out["match_probability"] < 0.7).sum() == 10
    assert out["is_match"].eq("").all()


def test_n_unclear_is_reported():
    labelled = pd.DataFrame({"match_probability": [0.95, 0.6, 0.97], "is_match": ["1", "0", ""]})
    assert evaluate.precision_recall(labelled, 0.9)["n_unclear"] == 1


def _name_level(name_l: str, name_r: str) -> str:
    """The name comparison level Splink assigns to two otherwise identical records."""
    import duckdb
    from splink import DuckDBAPI, Linker

    def rec(uid, name, source):
        frame = pd.DataFrame(
            {
                "cik": [uid],
                "company_name": [name],
                "business_city": ["X"],
                "business_state": ["NY"],
                "business_zip": ["10001"],
                "tickers": [""],
            }
        )
        out = matching.prepare_sec(frame)
        out["source"] = source
        return out

    left, right = rec(1, name_l, "sec"), rec(2, name_r, "gleif")
    linker = Linker([left, right], matching.settings(), DuckDBAPI(connection=duckdb.connect()))
    row = linker.inference.compare_two_records(left.iloc[0].to_dict(), right.iloc[0].to_dict()).as_pandas_dataframe()
    levels = matching.name_comparison().get_comparison("duckdb").as_dict()["comparison_levels"]
    return levels[len(levels) - 1 - int(row["gamma_name_std"].iloc[0])]["label_for_charts"]


def test_name_levels_separate_series_and_subsidiaries():
    assert _name_level("AMAZON.COM, INC.", "AMAZON COM INC") == "exact (spaces ignored)"
    assert (
        _name_level("KINDER MORGAN ENERGY PARTNERS, L.P.", "KINDER MORGAN ENERGY PARTNERS L P")
        == "exact (spaces ignored)"
    )
    assert (
        _name_level("Venture Lending & Leasing VII, Inc.", "Venture Lending & Leasing IX, Inc.")
        == "series or vehicle marks differ"
    )
    assert _name_level("Waste Connections US, Inc.", "Waste Connections, Inc.") == "series or vehicle marks differ"
    assert _name_level("General Mills Services, Inc.", "General Mills, Inc.") == "one name is the other plus words"
    assert _name_level("PETCO HEALTH AND WELNESS COMPANY, INC.", "Petco Health & Wellness Company, Inc.").startswith(
        "Jaro"
    )


def test_rescore_keeps_labels_and_takes_the_newer_probability():
    labelled = pd.DataFrame(
        {
            "unique_id_l": ["LEI:A", "LEI:B"],
            "unique_id_r": ["CIK:1", "CIK:2"],
            "match_probability": [0.95, 0.6],
            "is_match": ["0", "1"],
        }
    )
    # the newer run lists the first pair the other way round and drops the second
    newer = pd.DataFrame({"unique_id_l": ["CIK:1"], "unique_id_r": ["LEI:A"], "match_probability": [0.2]})
    out = evaluate.rescore(labelled, newer)
    assert out["match_probability"].tolist() == [0.2, 0.0]
    assert out["match_probability_before"].tolist() == [0.95, 0.6]
    assert out["is_match"].tolist() == ["0", "1"]


def test_sample_can_exclude_labelled_pairs():
    pairs = pd.DataFrame(
        {
            "unique_id_l": [f"LEI:{i}" for i in range(20)],
            "unique_id_r": [f"CIK:{i}" for i in range(20)],
            "match_probability": [0.95] * 20,
        }
    )
    out = evaluate.sample(pairs, 30, exclude=pairs.head(5))
    assert len(out) == 15 and not set(out["unique_id_l"]) & {f"LEI:{i}" for i in range(5)}
