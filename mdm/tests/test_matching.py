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
