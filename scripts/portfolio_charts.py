"""Charts for the README from the files of one real-data run (branch real-data-results).

  git archive origin/real-data-results results | tar -x -C /tmp/r
  uv run python scripts/portfolio_charts.py --results /tmp/r/results --out docs/images

These are static previews rendered with matplotlib from the run's CSV/JSON files, not
screenshots of the Power BI report; each chart names the run it comes from. No number is
typed by hand.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ACCENT, ACCENT_2, GREY = "#2a78d6", "#eb6834", "#c4c3be"
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"
MODELS = {
    "M0_zscore_rule": "M0 Z''-Regel",
    "M1_logit_z": "M1 Z'' (Logit)",
    "M2_logit_z_wc": "M2 Z'' + Working Capital",
    "M2r_logit_z_wc_relative": "M2r sektorrelativ",
    "S1_discrete_time_hazard": "S1 Hazard",
    "M3_lightgbm_all": "M3 LightGBM, alle KPIs",
}


def de(x: float, nd: int = 1) -> str:
    return f"{x:,.{nd}f}".replace(",", " ").replace(".", ",")


def style(ax, title: str, source: str) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=10, length=0)
    ax.figure.text(0.01, 0.97, title, fontsize=13, fontweight="bold", color=INK, va="top")
    ax.figure.text(0.01, 0.015, source, fontsize=8, color=INK_2, va="bottom")


def fig(h: float = 4.6):
    f, ax = plt.subplots(figsize=(9, h), dpi=150)
    f.patch.set_facecolor(SURFACE)
    return f, ax


def sectors(r: Path, out: Path, src: str) -> None:
    df = pd.read_csv(r / "analysis/wc_opportunity_by_sector.csv").sort_values("cash_opportunity_eur_bn")
    f, ax = fig(5.0)
    colours = [GREY] * (len(df) - 1) + [ACCENT]
    ax.barh(df.sector_de, df.cash_opportunity_eur_bn, color=colours, height=0.62)
    for y, (v, n) in enumerate(zip(df.cash_opportunity_eur_bn, df.companies, strict=True)):
        ax.text(v + 4, y, f"{de(v, 0)} Mrd. € · {de(n, 0)} Unt.", va="center", fontsize=9, color=INK_2)
    ax.set_xlim(0, df.cash_opportunity_eur_bn.max() * 1.32)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_xticklabels([])
    total = df.cash_opportunity_eur_bn.sum()
    style(ax, f"H4: {de(total, 0)} Mrd. € Liquidität, wenn jeder Sektor seinen CCC-Median erreicht", src)
    f.subplots_adjust(left=0.30, right=0.98, top=0.88, bottom=0.08)
    f.savefig(out / "h4_wc_potential_by_sector.png")
    plt.close(f)


def leadtime(a: dict, out: Path, src: str) -> None:
    h1 = a["H1"]
    rows = [
        ("Z''-Flagge", h1["median_z"], 1 - h1["share_never_red_z"], h1["share_z_available_last"]),
        ("CCC-Flagge", h1["median_ccc"], 1 - h1["share_never_red_ccc"], h1["share_ccc_available_last"]),
    ]
    f, axes = plt.subplots(1, 3, figsize=(9, 3.4), dpi=150)
    f.patch.set_facecolor(SURFACE)
    panels = [
        ("Median-Vorlauf (Monate)", 1, de),
        ("bis zum Ereignis rot", 2, lambda v: f"{de(100 * v, 0)} %"),
        ("im letzten Quartal berechenbar", 3, lambda v: f"{de(100 * v, 0)} %"),
    ]
    for ax, (label, i, fmt) in zip(axes, panels, strict=True):
        vals = [row[i] for row in rows]
        ax.barh([row[0] for row in rows], vals, color=[ACCENT, GREY], height=0.55)
        top = max(vals) if max(vals) > 0 else 1
        for y, v in enumerate(vals):
            ax.text(v + top * 0.03, y, fmt(v), va="center", fontsize=10, color=INK)
        ax.set_xlim(0, top * 1.45)
        ax.set_xticks([])
        ax.invert_yaxis()
        ax.set_title(label, fontsize=10, color=INK_2, loc="left")
        ax.set_facecolor(SURFACE)
        for side in ("top", "right", "bottom", "left"):
            ax.spines[side].set_visible(False)
        ax.tick_params(colors=INK, labelsize=10, length=0)
    for ax in axes[1:]:
        ax.set_yticklabels([])
    f.text(
        0.01,
        0.97,
        f"H1: Z'' warnt {de(-h1['estimate'])} Monate früher als die CCC "
        f"(95%-KI {de(-h1['ci_high'])} bis {de(-h1['ci_low'])}), {h1['n_companies']} Insolvenzen",
        fontsize=13,
        fontweight="bold",
        color=INK,
        va="top",
    )
    f.text(0.01, 0.015, src, fontsize=8, color=INK_2)
    f.subplots_adjust(left=0.13, right=0.98, top=0.75, bottom=0.12, wspace=0.12)
    f.savefig(out / "h1_lead_time.png")
    plt.close(f)


def models(r: Path, out: Path, src: str) -> None:
    df = pd.read_csv(r / "analysis/backtest_pooled.csv")
    df = df[df.model.isin(MODELS)].copy()
    df["label"] = df.model.map(MODELS)
    df = df.sort_values("pr_auc")
    f, ax = fig(4.2)
    colours = [ACCENT if m == "M3_lightgbm_all" else GREY for m in df.model]
    ax.barh(df.label, df.pr_auc, color=colours, height=0.6)
    for y, (v, rc) in enumerate(zip(df.pr_auc, df.recall_top5, strict=True)):
        label = f"{de(v, 3)}  · Recall Top 5 %: {de(100 * rc, 0)} %"
        ax.text(v + 0.0008, y, label, va="center", fontsize=9, color=INK_2)
    ax.set_xlim(0, df.pr_auc.max() * 1.6)
    ax.set_xticks([])
    n, pos = int(df.n.iloc[0]), int(df.n_pos.iloc[0])
    style(ax, "PR-AUC im rollierenden Backtest 2014\u20132025: M3 ist der Champion", src)
    ax.set_title(
        f"{de(n, 0)} Beobachtungen, {de(pos, 0)} Insolvenzen (Basisrate {de(100 * pos / n, 2)} %)",
        fontsize=9,
        color=INK_2,
        loc="left",
    )
    f.subplots_adjust(left=0.30, right=0.98, top=0.80, bottom=0.08)
    f.savefig(out / "models_pr_auc.png")
    plt.close(f)


def by_year(r: Path, out: Path, src: str) -> None:
    df = pd.read_csv(r / "analysis/backtest_by_year.csv")
    f, ax = fig(4.2)
    for model, colour, name in [("M3_lightgbm_all", ACCENT, "M3"), ("M1_logit_z", ACCENT_2, "M1 Z''")]:
        d = df[df.model == model].sort_values("test_year")
        ax.plot(d.test_year, d.pr_auc, color=colour, linewidth=2, marker="o", markersize=5, label=name)
        ax.text(d.test_year.iloc[-1] + 0.25, d.pr_auc.iloc[-1], name, color=INK, fontsize=9, va="center")
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: de(v, 2)))
    ax.set_axisbelow(True)
    ax.set_xticks(sorted(df.test_year.unique()))
    ax.tick_params(axis="x", labelsize=8)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    style(ax, "PR-AUC je Testjahr: M3 liegt in jedem Jahr über Z'' allein", src)
    f.subplots_adjust(left=0.08, right=0.94, top=0.86, bottom=0.12)
    f.savefig(out / "backtest_by_year.png")
    plt.close(f)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--results", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("docs/images"))
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    run = (args.results / "RUN.txt").read_text().splitlines()[0].rsplit("/", 1)[-1]
    src = (
        f"Quelle: Bilanzwerk, Lauf auf echten Daten {run} (SEC FSDS 2009q2\u20132026q3), "
        "mit matplotlib aus den Ergebnisdateien gerendert"
    )
    a = json.loads((args.results / "analysis/answer.json").read_text())
    sectors(args.results, args.out, src)
    leadtime(a, args.out, src)
    models(args.results, args.out, src)
    by_year(args.results, args.out, src)


if __name__ == "__main__":
    main()
