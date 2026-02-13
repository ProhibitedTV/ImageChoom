"""Main window scaffolding for the ImageChoom GUI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QMainWindow,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from imagechoom.workflows import discover_workflows, normalize_workflow_for_run, read_workflow_text


class MainWindow(QMainWindow):
    """Primary application window with sidebar navigation and stacked pages."""

    SECTION_NAMES = ("Workflows", "Presets", "Prompt Lab", "Runs")

    def __init__(self, *, imagechoom_root: Path) -> None:
        super().__init__()
        self.imagechoom_root = imagechoom_root

        self._workflow_items = discover_workflows(self.imagechoom_root)

        self.setObjectName("mainWindow")
        self.setWindowTitle("ImageChoom")
        self.resize(980, 640)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("navigationSidebar")
        self.sidebar.addItems(self.SECTION_NAMES)

        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("mainPageStack")
        self.page_stack.addWidget(self._build_workflows_page())
        for section_name in self.SECTION_NAMES[1:]:
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

    def _build_workflows_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("workflowsPage")

        outer_layout = QVBoxLayout(page)
        outer_layout.setContentsMargins(16, 16, 16, 16)

        workflows_splitter = QSplitter(Qt.Orientation.Horizontal)
        workflows_splitter.setObjectName("workflowsSplitter")

        self.workflow_list = QListWidget()
        self.workflow_list.setObjectName("workflowList")
        for workflow in self._workflow_items:
            self.workflow_list.addItem(f"{workflow.name} ({workflow.type})")

        detail_panel = QWidget()
        detail_panel.setObjectName("workflowDetailPanel")
        detail_layout = QVBoxLayout(detail_panel)

        self.workflow_path_label = QLabel("Select a workflow")
        self.workflow_path_label.setObjectName("workflowPathLabel")
        self.workflow_path_label.setWordWrap(True)
        detail_layout.addWidget(self.workflow_path_label)

        self.workflow_warnings_label = QLabel("")
        self.workflow_warnings_label.setObjectName("workflowWarningsLabel")
        self.workflow_warnings_label.setWordWrap(True)
        self.workflow_warnings_label.hide()
        detail_layout.addWidget(self.workflow_warnings_label)

        source_label = QLabel("Source (.choom)")
        source_label.setObjectName("workflowSourceLabel")
        detail_layout.addWidget(source_label)

        self.workflow_source_text = QPlainTextEdit()
        self.workflow_source_text.setObjectName("workflowSourceText")
        self.workflow_source_text.setReadOnly(True)
        detail_layout.addWidget(self.workflow_source_text, 1)

        self.workflow_preview_title = QLabel("Normalized v1 preview")
        self.workflow_preview_title.setObjectName("workflowPreviewLabel")
        detail_layout.addWidget(self.workflow_preview_title)

        self.workflow_normalized_text = QPlainTextEdit()
        self.workflow_normalized_text.setObjectName("workflowNormalizedText")
        self.workflow_normalized_text.setReadOnly(True)
        detail_layout.addWidget(self.workflow_normalized_text, 1)

        workflows_splitter.addWidget(self.workflow_list)
        workflows_splitter.addWidget(detail_panel)
        workflows_splitter.setStretchFactor(0, 0)
        workflows_splitter.setStretchFactor(1, 1)

        outer_layout.addWidget(workflows_splitter)

        self.workflow_list.currentRowChanged.connect(self._handle_workflow_selection_change)
        if self._workflow_items:
            self.workflow_list.setCurrentRow(0)

        return page

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

    def _handle_workflow_selection_change(self, index: int) -> None:
        if not (0 <= index < len(self._workflow_items)):
            self.workflow_path_label.setText("Select a workflow")
            self.workflow_source_text.clear()
            self.workflow_normalized_text.clear()
            self.workflow_preview_title.hide()
            self.workflow_normalized_text.hide()
            self.workflow_warnings_label.hide()
            return

        workflow = self._workflow_items[index]
        self.workflow_path_label.setText(f"{workflow.path.relative_to(self.imagechoom_root)}")
        self.workflow_source_text.setPlainText(read_workflow_text(workflow.path))

        if workflow.type == "legacy":
            normalized = normalize_workflow_for_run(workflow.path)
            self.workflow_normalized_text.setPlainText(normalized.normalized_text)
            self.workflow_preview_title.show()
            self.workflow_normalized_text.show()
            if normalized.warnings:
                warning_text = "Warnings:\n- " + "\n- ".join(normalized.warnings)
                self.workflow_warnings_label.setText(warning_text)
                self.workflow_warnings_label.show()
            else:
                self.workflow_warnings_label.hide()
        else:
            self.workflow_preview_title.hide()
            self.workflow_normalized_text.hide()
            self.workflow_warnings_label.hide()
