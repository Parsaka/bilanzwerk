from analysis.pipeline import _kpi_names_de, driver_label, driver_labels


def test_driver_label_uses_seed_names():
    names = _kpi_names_de()
    assert driver_label("EQUITY_RATIO__value", names) == names["EQUITY_RATIO"]
    assert driver_label("ZPP__chg4q", names) == "Altman Z'' (1995) (Δ Jahr)"
    assert driver_label("CCC__pct", names).endswith("(Sektorperzentil)")


def test_unknown_feature_keeps_code():
    assert driver_label("SOMETHING__else", {}) == "SOMETHING else"


def test_driver_labels_takes_top_three():
    out = driver_labels(["ZPP__value", "DSO__chg1q", "CCC__pct", "DIO__value"])
    assert out.count(", ") == 2
    assert "DIO" not in out
