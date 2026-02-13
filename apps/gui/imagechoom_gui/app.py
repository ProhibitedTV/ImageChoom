"""Application bootstrap for ImageChoom GUI."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def run_app(argv: Sequence[str] | None = None) -> int:
    """Create the Qt app and run the main window."""
    app_args = list(argv) if argv is not None else sys.argv
    app = QApplication(app_args)
    window = MainWindow()
    window.show()
    return app.exec()
