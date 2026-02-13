"""Main window scaffolding for the ImageChoom GUI."""

from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from imagechoom.executor import RunResult, run_workflow
from imagechoom.promptlab import PromptLabWidget
from imagechoom.settings import AppSettings, check_a1111_health, load_settings, save_settings
from imagechoom.workflows import discover_workflows, normalize_workflow_for_run, read_workflow_text


class RunWorker(QThread):
    """QThread wrapper for workflow execution."""

    finished_run = Signal(object)
    log_line = Signal(str)

    def __init__(
        self,
        *,
        normalized_text: str,
        run_name: str,
        settings: AppSettings,
    ) -> None:
        super().__init__()
        self.normalized_text = normalized_text
        self.run_name = run_name
        self.settings = settings

    def run(self) -> None:
        result = run_workflow(
            self.normalized_text,
            self.run_name,
            self.settings,
            on_log=self.log_line.emit,
        )
        self.finished_run.emit(result)


@dataclass(slots=True)
class QueuedRun:
    run_name: str
    normalized_text: str


class MainWindow(QMainWindow):
    """Primary application window with sidebar navigation and stacked pages."""

    SECTION_NAMES = ("Workflows", "Presets", "Prompt Lab", "Runs")

    def __init__(self, *, imagechoom_root: Path) -> None:
        super().__init__()
        self.imagechoom_root = imagechoom_root
        self.settings = load_settings(self.imagechoom_root)
        self._run_worker: RunWorker | None = None
        self._run_queue: list[QueuedRun] = []

        self._workflow_items = discover_workflows(self.imagechoom_root)

        self.setObjectName("mainWindow")
        self.setWindowTitle("ImageChoom")
        self.resize(980, 700)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("navigationSidebar")
        self.sidebar.addItems(self.SECTION_NAMES)

        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("mainPageStack")
        self.page_stack.addWidget(self._build_workflows_page())
        self.page_stack.addWidget(self._build_placeholder_page("Presets"))
        self.page_stack.addWidget(self._build_prompt_lab_page())
        self.page_stack.addWidget(self._build_runs_page())

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

        detail_layout.addWidget(self._build_settings_panel())
        detail_layout.addWidget(self._build_run_panel())

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

        run_logs_label = QLabel("Run logs")
        detail_layout.addWidget(run_logs_label)
        self.run_logs_text = QPlainTextEdit()
        self.run_logs_text.setReadOnly(True)
        self.run_logs_text.setMaximumBlockCount(2000)
        detail_layout.addWidget(self.run_logs_text, 1)

        gallery_label = QLabel("Generated images")
        detail_layout.addWidget(gallery_label)
        self.gallery_scroll = QScrollArea()
        self.gallery_scroll.setWidgetResizable(True)
        gallery_widget = QWidget()
        self.gallery_layout = QGridLayout(gallery_widget)
        self.gallery_layout.setContentsMargins(8, 8, 8, 8)
        self.gallery_layout.setHorizontalSpacing(12)
        self.gallery_layout.setVerticalSpacing(12)
        self.gallery_scroll.setWidget(gallery_widget)
        detail_layout.addWidget(self.gallery_scroll, 1)

        workflows_splitter.addWidget(self.workflow_list)
        workflows_splitter.addWidget(detail_panel)
        workflows_splitter.setStretchFactor(0, 0)
        workflows_splitter.setStretchFactor(1, 1)

        outer_layout.addWidget(workflows_splitter)

        self.workflow_list.currentRowChanged.connect(self._handle_workflow_selection_change)
        if self._workflow_items:
            self.workflow_list.setCurrentRow(0)

        return page

    def _build_settings_panel(self) -> QWidget:
        box = QGroupBox("A1111 Settings")
        layout = QGridLayout(box)

        layout.addWidget(QLabel("URL"), 0, 0)
        self.a1111_url_input = QLineEdit(self.settings.a1111_url)
        layout.addWidget(self.a1111_url_input, 0, 1, 1, 2)

        layout.addWidget(QLabel("Timeout (s)"), 1, 0)
        self.a1111_timeout_input = QSpinBox()
        self.a1111_timeout_input.setRange(1, 3600)
        self.a1111_timeout_input.setValue(self.settings.a1111_timeout)
        layout.addWidget(self.a1111_timeout_input, 1, 1)

        self.cancel_on_timeout_input = QCheckBox("Cancel on timeout")
        self.cancel_on_timeout_input.setChecked(self.settings.cancel_on_timeout)
        layout.addWidget(self.cancel_on_timeout_input, 1, 2)

        buttons_row = QHBoxLayout()
        self.save_settings_button = QPushButton("Save Settings")
        self.save_settings_button.clicked.connect(self._save_settings_from_ui)
        buttons_row.addWidget(self.save_settings_button)

        self.health_check_button = QPushButton("Health Check")
        self.health_check_button.clicked.connect(self._run_health_check)
        buttons_row.addWidget(self.health_check_button)
        buttons_row.addStretch(1)

        layout.addLayout(buttons_row, 2, 0, 1, 3)

        self.outputs_root_label = QLabel(f"Outputs root: {self.settings.outputs_root}")
        self.outputs_root_label.setWordWrap(True)
        layout.addWidget(self.outputs_root_label, 3, 0, 1, 3)

        self.health_check_status = QLabel("")
        self.health_check_status.setWordWrap(True)
        layout.addWidget(self.health_check_status, 4, 0, 1, 3)

        return box

    def _build_run_panel(self) -> QWidget:
        panel = QWidget()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self.run_button = QPushButton("Run")
        self.run_button.clicked.connect(self._run_selected_workflow)
        layout.addWidget(self.run_button)

        self.run_status_label = QLabel("Idle")
        layout.addWidget(self.run_status_label)
        layout.addStretch(1)
        return panel

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

    def _build_prompt_lab_page(self) -> QWidget:
        return PromptLabWidget(
            imagechoom_root=self.imagechoom_root,
            on_enqueue_workflow=self._enqueue_promptlab_workflow,
        )

    def _build_runs_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("runsPage")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)

        self.runs_queue_list = QListWidget()
        layout.addWidget(QLabel("Queued Prompt Lab jobs"))
        layout.addWidget(self.runs_queue_list, 1)

        controls = QHBoxLayout()
        self.run_next_button = QPushButton("Run Next")
        self.run_next_button.clicked.connect(self._run_next_queued_job)
        controls.addWidget(self.run_next_button)

        self.remove_queue_item_button = QPushButton("Remove Selected")
        self.remove_queue_item_button.clicked.connect(self._remove_selected_queue_item)
        controls.addWidget(self.remove_queue_item_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.run_queue_status = QLabel("Queue idle")
        layout.addWidget(self.run_queue_status)
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
            self.workflow_normalized_text.setPlainText(read_workflow_text(workflow.path))
            self.workflow_preview_title.show()
            self.workflow_normalized_text.show()
            self.workflow_warnings_label.hide()

    def _save_settings_from_ui(self) -> None:
        self.settings = AppSettings(
            a1111_url=self.a1111_url_input.text().strip() or "http://127.0.0.1:7860",
            a1111_timeout=int(self.a1111_timeout_input.value()),
            cancel_on_timeout=self.cancel_on_timeout_input.isChecked(),
            outputs_root=self.settings.outputs_root,
        )
        path = save_settings(self.settings)
        self.health_check_status.setText(f"Saved: {path}")

    def _run_health_check(self) -> None:
        self._save_settings_from_ui()
        ok, detail = check_a1111_health(self.settings.a1111_url, self.settings.a1111_timeout)
        status = "Success" if ok else "Failed"
        self.health_check_status.setText(f"{status}: {detail}")

    def _run_selected_workflow(self) -> None:
        index = self.workflow_list.currentRow()
        if not (0 <= index < len(self._workflow_items)):
            QMessageBox.warning(self, "Run", "Select a workflow first.")
            return

        self._save_settings_from_ui()
        workflow = self._workflow_items[index]
        normalized = normalize_workflow_for_run(workflow.path)

        self.run_logs_text.clear()
        self._clear_gallery()
        self.run_status_label.setText("Running...")
        self.run_button.setEnabled(False)

        self._run_worker = RunWorker(
            normalized_text=normalized.normalized_text,
            run_name=workflow.name,
            settings=self.settings,
        )
        self._run_worker.log_line.connect(self._append_run_log_line)
        self._run_worker.finished_run.connect(self._on_run_finished)
        self._run_worker.start()

    def _enqueue_promptlab_workflow(self, run_name: str, normalized_text: str) -> None:
        self._run_queue.append(QueuedRun(run_name=run_name, normalized_text=normalized_text))
        self.runs_queue_list.addItem(run_name)
        self.run_queue_status.setText(f"Queued jobs: {len(self._run_queue)}")
        self.sidebar.setCurrentRow(3)

    def _remove_selected_queue_item(self) -> None:
        index = self.runs_queue_list.currentRow()
        if not (0 <= index < len(self._run_queue)):
            return
        del self._run_queue[index]
        self.runs_queue_list.takeItem(index)
        self.run_queue_status.setText(f"Queued jobs: {len(self._run_queue)}")

    def _run_next_queued_job(self) -> None:
        if self._run_worker is not None and self._run_worker.isRunning():
            QMessageBox.warning(self, "Runs", "A run is already in progress.")
            return
        if not self._run_queue:
            QMessageBox.information(self, "Runs", "No queued jobs.")
            return

        self._save_settings_from_ui()
        queued = self._run_queue.pop(0)
        self.runs_queue_list.takeItem(0)
        self.run_queue_status.setText(f"Running queued job: {queued.run_name}")
        self.run_logs_text.clear()
        self._clear_gallery()
        self.run_status_label.setText("Running...")
        self.run_button.setEnabled(False)
        self.sidebar.setCurrentRow(0)

        self._run_worker = RunWorker(
            normalized_text=queued.normalized_text,
            run_name=queued.run_name,
            settings=self.settings,
        )
        self._run_worker.log_line.connect(self._append_run_log_line)
        self._run_worker.finished_run.connect(self._on_run_finished)
        self._run_worker.finished_run.connect(self._on_queue_run_finished)
        self._run_worker.start()

    def _append_run_log_line(self, line: str) -> None:
        self.run_logs_text.appendPlainText(line)

    def _on_run_finished(self, result: RunResult) -> None:
        self.run_button.setEnabled(True)
        self.run_logs_text.setPlainText("\n".join(result.log_lines))
        if result.success:
            self.run_status_label.setText(f"Done ({len(result.image_paths)} images)")
        else:
            self.run_status_label.setText("Failed")

        self._populate_gallery(result.image_paths)

    def _on_queue_run_finished(self, _: RunResult) -> None:
        if self._run_queue:
            self.run_queue_status.setText(f"Queued jobs remaining: {len(self._run_queue)}")
        else:
            self.run_queue_status.setText("Queue idle")

    def _clear_gallery(self) -> None:
        while self.gallery_layout.count():
            item = self.gallery_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _populate_gallery(self, image_paths: list[Path]) -> None:
        self._clear_gallery()
        if not image_paths:
            self.gallery_layout.addWidget(QLabel("No images yet."), 0, 0)
            return

        columns = 3
        for index, image_path in enumerate(image_paths):
            row = index // columns
            col = index % columns

            tile = QWidget()
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(0, 0, 0, 0)

            thumb = QLabel()
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pixmap = QPixmap(str(image_path))
            if not pixmap.isNull():
                thumb.setPixmap(
                    pixmap.scaled(
                        220,
                        220,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            else:
                thumb.setText("(failed to load image)")
            tile_layout.addWidget(thumb)

            caption = QLabel(image_path.name)
            caption.setWordWrap(True)
            tile_layout.addWidget(caption)

            self.gallery_layout.addWidget(tile, row, col)
