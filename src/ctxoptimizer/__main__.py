"""Module entry point for ``python -m ctxoptimizer``."""

from __future__ import annotations

from ctxoptimizer.cli import app


def main() -> None:
    """Run the command line interface."""
    app()


if __name__ == "__main__":
    main()
