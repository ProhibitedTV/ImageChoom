"""CLI entrypoint for launching the ImageChoom GUI."""

from __future__ import annotations

from .app import run_app


def main() -> int:
    """Run the GUI process."""
    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
