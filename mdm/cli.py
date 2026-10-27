"""`python -m mdm.cli match|sample|score`"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pandas as pd
import typer

from mdm import evaluate, matching

app = typer.Typer(help="Company master data: Splink matching to GLEIF, review sample, evaluation.")
DATA = Path(os.environ.get("BW_DATA_ROOT", "data"))


@app.command()
def match(warehouse: Path = DATA / "bilanzwerk.duckdb", out_dir: Path = DATA / "mdm") -> None:
    logging.basicConfig(level=logging.INFO)
    matches = matching.run(warehouse, out_dir)
    typer.echo(matches["match_status"].value_counts().to_string())


@app.command()
def sample(
    pairs: Path = DATA / "mdm" / "candidate_pairs.parquet", out: Path = Path("mdm/labelled_pairs.csv"), n: int = 300
) -> None:
    if out.exists():
        raise typer.BadParameter(f"{out} exists; it holds hand labels and is never overwritten")
    evaluate.sample(pd.read_parquet(pairs), n).to_csv(out, index=False)
    typer.echo(f"wrote {out}; label the is_match column by hand")


@app.command()
def score(
    labelled: Path = Path("mdm/labelled_pairs.csv"),
    threshold: float = matching.UPPER,
    out: Path = Path("mdm/reports/evaluation.json"),
) -> None:
    typer.echo(json.dumps(evaluate.score(labelled, threshold, out)["chosen"], indent=2, default=float))


if __name__ == "__main__":
    app()
