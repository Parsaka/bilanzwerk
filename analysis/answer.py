"""Turn the analysis outputs into the four-line answer (H1-H4). Numbers come only from the run."""

from __future__ import annotations

import math

import pandas as pd


def _nan(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _status(held: bool, *values) -> tuple[str, str]:
    """(machine status, German word). Missing numbers mean the test could not be run."""
    if any(_nan(v) for v in values):
        return "not_determinable", "nicht bestimmbar"
    return ("held", "bestätigt") if held else ("not_held", "nicht bestätigt")


_WORD_EN = {"held": "held", "not_held": "not held", "not_determinable": "not determinable"}


def _fmt(x: float, digits: int = 1) -> str:
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{digits}f}"


def h1(lead: dict) -> dict:
    held = lead["estimate"] > 0 and lead["ci_low"] > 0
    status, word = _status(held, lead["estimate"], lead["ci_low"])
    return {
        "hypothesis": "H1 lead time",
        "held": held,
        "status": status,
        "text_de": (
            f"H1 {word}: Das CCC-Signal wurde im Median "
            f"{_fmt(lead['median_ccc'])} Monate vor der Insolvenz rot, das Z''-Signal "
            f"{_fmt(lead['median_z'])} Monate; Differenz {_fmt(lead['estimate'])} Monate "
            f"(95%-KI {_fmt(lead['ci_low'])} bis {_fmt(lead['ci_high'])})."
        ),
        "text_en": (
            f"H1 {_WORD_EN[status]}: the CCC flag turned red a median {_fmt(lead['median_ccc'])} months "
            f"before bankruptcy, the Z'' flag {_fmt(lead['median_z'])} months; difference "
            f"{_fmt(lead['estimate'])} months (95% CI {_fmt(lead['ci_low'])} to {_fmt(lead['ci_high'])})."
        ),
        **lead,
    }


def h2(diff: dict) -> dict:
    held = diff["ci_low"] > 0
    status, word = _status(held, diff["estimate"], diff["ci_low"])
    return {
        "hypothesis": "H2 accuracy",
        "held": held,
        "status": status,
        "text_de": (
            f"H2 {word}: PR-AUC M2 minus M1 = "
            f"{_fmt(diff['estimate'], 3)} (95%-KI {_fmt(diff['ci_low'], 3)} bis {_fmt(diff['ci_high'], 3)})."
        ),
        "text_en": (
            f"H2 {_WORD_EN[status]}: PR-AUC M2 minus M1 = "
            f"{_fmt(diff['estimate'], 3)} (95% CI {_fmt(diff['ci_low'], 3)} to {_fmt(diff['ci_high'], 3)})."
        ),
        **diff,
    }


def h3(diff: dict) -> dict:
    held = diff["ci_low"] > 0
    status, word = _status(held, diff["estimate"], diff["ci_low"])
    return {
        "hypothesis": "H3 sector view",
        "held": held,
        "status": status,
        "text_de": (
            f"H3 {word}: PR-AUC sektorrelativ minus absolut = "
            f"{_fmt(diff['estimate'], 3)} (95%-KI {_fmt(diff['ci_low'], 3)} bis {_fmt(diff['ci_high'], 3)})."
        ),
        "text_en": (
            f"H3 {_WORD_EN[status]}: PR-AUC sector-relative minus absolute = "
            f"{_fmt(diff['estimate'], 3)} (95% CI {_fmt(diff['ci_low'], 3)} to {_fmt(diff['ci_high'], 3)})."
        ),
        **diff,
    }


def h4(by_sector: pd.DataFrame, material_eur_bn: float = 1.0) -> dict:
    total = float(by_sector["cash_opportunity_eur_bn"].sum()) if len(by_sector) else float("nan")
    top = by_sector.iloc[0] if len(by_sector) else None
    held = bool(top is not None and top["cash_opportunity_eur_bn"] >= material_eur_bn)
    status, word = _status(held, None if top is None else total)
    return {
        "hypothesis": "H4 euro value",
        "held": held,
        "status": status,
        "total_eur_bn": total,
        "top_sector": None if top is None else top["sector_de"],
        "top_sector_eur_bn": None if top is None else float(top["cash_opportunity_eur_bn"]),
        "text_de": (
            f"H4 {word}: Working-Capital-Potenzial gesamt "
            f"{_fmt(total)} Mrd. EUR; größter Hebel "
            f"{'n/a' if top is None else top['sector_de']} mit "
            f"{'n/a' if top is None else _fmt(float(top['cash_opportunity_eur_bn']))} Mrd. EUR."
        ),
        "text_en": (
            f"H4 {_WORD_EN[status]}: working-capital potential EUR {_fmt(total)} bn in total; largest lever "
            f"{'n/a' if top is None else top['sector_en']} with EUR "
            f"{'n/a' if top is None else _fmt(float(top['cash_opportunity_eur_bn']))} bn."
        ),
    }
