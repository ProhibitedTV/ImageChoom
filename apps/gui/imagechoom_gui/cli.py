"""CLI entrypoint for launching the ImageChoom GUI."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QLabel


def main() -> int:
    """Create and run the Qt application."""
    app = QApplication(sys.argv)
    label = QLabel("ImageChoom GUI is running")
    label.setWindowTitle("ImageChoom")
    label.resize(320, 80)
    label.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
