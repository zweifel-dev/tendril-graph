"""Entry point for `python -m tendril` and the installed `tendril` console script."""

from tendril.cli.main import main


def main_entry() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    main_entry()
