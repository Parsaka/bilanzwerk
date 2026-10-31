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
def match(
    warehouse: Path = DATA / "bilanzwerk.duckdb", out_dir: Path = DATA / "mdm", inputs: Path | None = None
) -> None:
    """`--inputs results/mdm_inputs` reruns on the SEC and GLEIF rows a real-data run saved."""
    logging.basicConfig(level=logging.INFO)
    matches = matching.run(warehouse, out_dir, inputs)
    typer.echo(matches["match_status"].value_counts().to_string())


@app.command()
def sample(
    pairs: Path = DATA / "mdm" / "candidate_pairs.parquet",
    out: Path = Path("mdm/labelled_pairs.csv"),
    n: int = 300,
    exclude: Path | None = None,
) -> None:
    """`--exclude mdm/labelled_pairs.csv` draws a fresh, out-of-sample set for a newer model."""
    if out.exists():
        raise typer.BadParameter(f"{out} exists; it holds hand labels and is never overwritten")
    done = pd.read_csv(exclude, dtype=str) if exclude else None
    evaluate.sample(pd.read_parquet(pairs), n, exclude=done).to_csv(out, index=False)
    typer.echo(f"wrote {out}; label the is_match column by hand")


@app.command()
def score(
    labelled: Path = Path("mdm/labelled_pairs.csv"),
    threshold: float = matching.UPPER,
    out: Path = Path("mdm/reports/evaluation.json"),
) -> None:
    typer.echo(json.dumps(evaluate.score(labelled, threshold, out)["chosen"], indent=2, default=float))


@app.command()
def rescore(
    labelled: Path = Path("mdm/labelled_pairs.csv"),
    pairs: Path = DATA / "mdm" / "candidate_pairs.parquet",
    threshold: float = matching.UPPER,
    out: Path = Path("mdm/reports/evaluation_rescored.json"),
    rescored: Path | None = None,
) -> None:
    """The hand labels scored against the probabilities of the current model run."""
    frame = evaluate.rescore(pd.read_csv(labelled, dtype={"is_match": str}), pd.read_parquet(pairs))
    if rescored:
        frame.to_csv(rescored, index=False)
    report = {
        "model_version": matching.MODEL_VERSION,
        "chosen": evaluate.precision_recall(frame, threshold),
        "curve": [evaluate.precision_recall(frame, t) for t in evaluate.CURVE],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=float))
    typer.echo(json.dumps(report["chosen"], indent=2, default=float))


if __name__ == "__main__":
    app()
