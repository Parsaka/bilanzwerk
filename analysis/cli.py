"""`bw-analysis run | events | case --cik N | label-audit`"""

from __future__ import annotations

import json
import logging

import duckdb
import typer

from analysis import data, label_audit, pipeline
from analysis.config import AnalysisConfig

app = typer.Typer(help="Early-warning analysis: backtest, statistics, explanations, risk score write-back.")


@app.command()
def run(no_mlflow: bool = False) -> None:
    logging.basicConfig(level=logging.INFO)
    doc = pipeline.run(log_mlflow=not no_mlflow)
    for h in ("H1", "H2", "H3", "H4"):
        typer.echo(doc[h]["text_de"])


@app.command()
def events() -> None:
    """Event count check (spec, week 5): positives per year for both labels."""
    md = data.build(AnalysisConfig())
    typer.echo(md.label_note)
    typer.echo(data.positives_per_year(md.frame).to_string())


@app.command()
def case(cik: int) -> None:
    cfg = AnalysisConfig()
    con = duckdb.connect(str(cfg.warehouse), read_only=True)
    df = pipeline.case_timeline(con, cik)
    out = cfg.out_dir / "results" / f"case_{cik}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    typer.echo(json.dumps({"rows": len(df), "file": str(out)}))


@app.command("label-audit")
def label_audit_cmd(limit: int = 0) -> None:
    """Read the 8-K behind every main-label event on EDGAR and report wrong item lists and
    subsidiary-only bankruptcies (needs access to sec.gov). The labels are not changed."""
    logging.basicConfig(level=logging.INFO)
    cfg = AnalysisConfig()
    summary = label_audit.run(cfg.warehouse, cfg.out_dir / "results", limit=limit or None)
    typer.echo(json.dumps(summary, indent=2))


if __name__ == "__main__":
    app()
