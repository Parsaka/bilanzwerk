"""Command line entry point: `bilanzwerk <source> ...`."""

from __future__ import annotations

import logging
from datetime import date
from typing import Annotated

import typer

from ingestion import ecb, esef, gleif, sec_fsds, sec_submissions
from ingestion.common.config import get_settings
from ingestion.common.manifest import Manifest

app = typer.Typer(help="Bilanzwerk loaders. Every loader is idempotent: a rerun loads nothing new.")


@app.callback()
def main(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )


@app.command("sec-fsds")
def cmd_sec_fsds(
    start: Annotated[str, typer.Option(help="first quarter, e.g. 2009q2")] = "2009q2",
    end: Annotated[str | None, typer.Option(help="last quarter; default: last completed")] = None,
) -> None:
    quarters = sec_fsds.list_quarters(sec_fsds.Quarter.parse(start), sec_fsds.Quarter.parse(end) if end else None)
    result = sec_fsds.run(get_settings(), quarters)
    typer.echo(result)


@app.command("sec-submissions")
def cmd_sec_submissions() -> None:
    typer.echo(sec_submissions.run(get_settings()))


@app.command("esef")
def cmd_esef(countries: Annotated[list[str] | None, typer.Option()] = None, min_year: int = 2020) -> None:
    typer.echo(esef.run(get_settings(), countries, min_year))


@app.command("gleif")
def cmd_gleif(full: bool = False) -> None:
    typer.echo(gleif.run(get_settings(), full=full))


@app.command("ecb")
def cmd_ecb(start: Annotated[str | None, typer.Option()] = None) -> None:
    typer.echo(ecb.run(get_settings(), start=date.fromisoformat(start) if start else None))


@app.command("manifest")
def cmd_manifest(source: str | None = None) -> None:
    for row in Manifest(get_settings().manifest_path).rows(source):
        typer.echo("\t".join("" if v is None else str(v) for v in row))


if __name__ == "__main__":
    app()
