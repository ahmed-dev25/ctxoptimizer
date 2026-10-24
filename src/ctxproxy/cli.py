"""Command line interface (SPEC section 15).

Only ``--version`` exists in P0-1. The ``run``, ``status``, ``env``, ``doctor``
and ``export`` commands land in P1-6.
"""

from __future__ import annotations

from typing import Annotated

import typer

from ctxproxy import __version__

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Local, deterministic cost optimizer for AI coding agents.",
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit(code=0)


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            is_eager=True,
            callback=_version_callback,
            help="Show the ctxproxy version and exit.",
        ),
    ] = False,
) -> None:
    """ctxproxy command line."""


if __name__ == "__main__":
    main()
