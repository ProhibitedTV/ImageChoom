"""Main window scaffolding for the ImageChoom GUI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    """Primary application window with sidebar navigation and stacked pages."""

    SECTION_NAMES = ("Workflows", "Presets", "Prompt Lab", "Runs")

    def __init__(self, *, imagechoom_root: Path) -> None:
        super().__init__()
        self.imagechoom_root = imagechoom_root

        self.setObjectName("mainWindow")
        self.setWindowTitle("ImageChoom")
        self.resize(980, 640)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("navigationSidebar")
        self.sidebar.addItems(self.SECTION_NAMES)

        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("mainPageStack")
        for section_name in self.SECTION_NAMES:
            self.page_stack.addWidget(self._build_placeholder_page(section_name))

        layout_splitter = QSplitter(Qt.Orientation.Horizontal)
        layout_splitter.setObjectName("mainLayoutSplitter")
        layout_splitter.addWidget(self.sidebar)
        layout_splitter.addWidget(self.page_stack)
        layout_splitter.setStretchFactor(0, 0)
        layout_splitter.setStretchFactor(1, 1)

        root = QWidget()
        root.setObjectName("mainWindowRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(layout_splitter)
        self.setCentralWidget(root)

        self.sidebar.currentRowChanged.connect(self._handle_sidebar_index_change)
        self.sidebar.setCurrentRow(0)

    def _build_placeholder_page(self, section_name: str) -> QWidget:
        page = QWidget()
        page.setObjectName(f"{section_name.lower().replace(' ', '_')}Page")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)

        label = QLabel(f"{section_name} page")
        label.setObjectName(f"{section_name.lower().replace(' ', '_')}PlaceholderLabel")
        layout.addWidget(label)
        root_hint_label = QLabel(f"Repo root: {self.imagechoom_root}")
        root_hint_label.setObjectName(
            f"{section_name.lower().replace(' ', '_')}RootPathLabel"
        )
        root_hint_label.setWordWrap(True)
        layout.addWidget(root_hint_label)
        layout.addStretch(1)

        return page

    def _handle_sidebar_index_change(self, index: int) -> None:
        if 0 <= index < self.page_stack.count():
            self.page_stack.setCurrentIndex(index)
