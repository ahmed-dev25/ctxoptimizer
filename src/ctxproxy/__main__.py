"""Module entry point for ``python -m ctxproxy``."""

from __future__ import annotations

from ctxproxy.cli import app


def main() -> None:
    """Run the command line interface."""
    app()


if __name__ == "__main__":
    main()
