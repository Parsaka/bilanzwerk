from __future__ import annotations

from datetime import date
from decimal import Decimal

from ingestion import esef

DOC = {
    "documentInfo": {"documentType": "https://xbrl.org/2021/xbrl-json"},
    "facts": {
        "f1": {
            "value": "1000000",
            "decimals": -3,
            "dimensions": {
                "concept": "ifrs-full:Revenue",
                "entity": "scheme:529900NNUPAGGOMPXZ31",
                "period": "2023-01-01T00:00:00/2024-01-01T00:00:00",
                "unit": "iso4217:EUR",
            },
        },
        "f2": {
            "value": "5000",
            "decimals": 0,
            "dimensions": {
                "concept": "ifrs-full:Inventories",
                "entity": "scheme:529900NNUPAGGOMPXZ31",
                "period": "2024-01-01T00:00:00",
                "unit": "iso4217:EUR",
            },
        },
        "f3": {
            "value": "7",
            "decimals": 0,
            "dimensions": {
                "concept": "ifrs-full:Revenue",
                "entity": "scheme:529900NNUPAGGOMPXZ31",
                "period": "2023-01-01T00:00:00/2024-01-01T00:00:00",
                "unit": "iso4217:EUR",
                "ifrs-full:SegmentsAxis": "x:Retail",
            },
        },
        "f4": {
            "value": "Some text",
            "dimensions": {
                "concept": "ifrs-full:NameOfReportingEntity",
                "entity": "scheme:529900NNUPAGGOMPXZ31",
                "period": "2023-01-01T00:00:00/2024-01-01T00:00:00",
            },
        },
    },
}


def test_parse_period_uses_inclusive_ends():
    assert esef.parse_period("2023-01-01T00:00:00/2024-01-01T00:00:00") == (date(2023, 1, 1), date(2023, 12, 31), False)
    assert esef.parse_period("2024-01-01T00:00:00") == (None, date(2023, 12, 31), True)
    assert esef.parse_period("2023-12-31") == (None, date(2023, 12, 31), True)


def test_flatten_keeps_only_numeric_totals():
    rows = list(esef.flatten_facts("fx1", DOC))
    assert {r["concept"] for r in rows} == {"ifrs-full:Revenue", "ifrs-full:Inventories"}
    rev = next(r for r in rows if r["concept"] == "ifrs-full:Revenue")
    assert rev["value"] == Decimal("1000000.000000")
    assert rev["lei"] == "529900NNUPAGGOMPXZ31"
    assert rev["decimals"] == -3
