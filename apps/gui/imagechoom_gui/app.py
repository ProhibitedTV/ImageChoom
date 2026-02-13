"""Application bootstrap for ImageChoom GUI."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .paths import resolve_imagechoom_root


def run_app(argv: Sequence[str] | None = None) -> int:
    """Create the Qt app and run the main window."""
    app_args = list(argv) if argv is not None else sys.argv
    app = QApplication(app_args)
    imagechoom_root = resolve_imagechoom_root(Path(__file__))
    window = MainWindow(imagechoom_root=imagechoom_root)
    window.show()
    return app.exec()
