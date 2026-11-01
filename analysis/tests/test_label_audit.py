"""The label audit reads the debtor from the 8-K wording; texts adapted from real filings."""

import pandas as pd

from analysis.label_audit import body_text, classify, summarise

HEADER = "<SEC-HEADER>ITEM INFORMATION: Bankruptcy or Receivership</SEC-HEADER><DOCUMENT><TEXT><html><body>"

FILER = (
    "Item 1.03. Bankruptcy or Receivership. Voluntary Petition for Reorganization On May 15, 2020, "
    "J. C. Penney Company, Inc. (the &#8220;Company&#8221;) and certain of its subsidiaries commenced "
    "voluntary cases under chapter 11 of title 11 of the United States Code."
)
SUBSIDIARY = (
    "Item 1.03 Bankruptcy or Receivership. On March 31, 2018, FirstEnergy Solutions Corp., together with "
    "its subsidiaries, and FirstEnergy Nuclear Operating Company, each wholly owned subsidiaries of "
    "FirstEnergy Corp., filed voluntary petitions for bankruptcy protection under Chapter 11."
)
NO_ITEM = (
    "Item 1.01 Entry into a Material Definitive Agreement. Item 3.03 below is incorporated herein by "
    "reference. Item 3.03 Material Modification to Rights of Security Holders. Amendment of Rights Agreement."
)


def doc(text: str) -> str:
    return HEADER + "<p>" + text + "</p></body></html></TEXT></DOCUMENT><DOCUMENT><TEXT>Exhibit 99.1 Item 1.03"


def test_body_is_first_document_only():
    body = body_text(doc(NO_ITEM))
    assert "Exhibit 99.1" not in body and "<p>" not in body


def test_filer_and_subsidiaries_is_filer():
    v = classify(body_text(doc(FILER)))
    assert v.item_in_text and v.debtor == "filer"


def test_only_subsidiary_is_flagged():
    v = classify(body_text(doc(SUBSIDIARY)))
    assert v.item_in_text and v.debtor == "subsidiary_only"
    assert "wholly owned subsidiaries" in v.snippet


def test_item_missing_in_text():
    v = classify(body_text(doc(NO_ITEM)))
    assert not v.item_in_text and v.debtor == "no_item"


def test_summary_counts_first_event_per_company():
    df = pd.DataFrame(
        {
            "company_id": ["a", "a", "b", "c"],
            "is_first_event": [1, 0, 1, 1],
            "fetched": [1, 1, 1, 0],
            "debtor": ["no_item", "filer", "subsidiary_only", None],
        }
    )
    s = summarise(df)
    assert s["fetched"] == 3 and s["not_fetched"] == 1
    assert s["first_event_per_company"]["item_missing_in_text"] == 1
    assert s["first_event_per_company"]["subsidiary_only"] == 1
    assert s["all_filings"]["filer_is_debtor"] == 1


def test_company_subsidiary_without_filer_is_flagged():
    text = (
        "Item 1.03 Bankruptcy or Receivership. On June 2, 2015, the Company's indirect subsidiary, "
        "Acme Mining LLC, filed a voluntary petition under Chapter 11."
    )
    assert classify(body_text(doc(text))).debtor == "subsidiary_only"


def test_plain_filer_is_filer():
    text = "Item 1.03 Bankruptcy or Receivership. On June 2, 2015, Acme Corp. filed a voluntary petition."
    assert classify(body_text(doc(text))).debtor == "filer"
