"""Main window scaffolding for the ImageChoom GUI."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from imagechoom.executor import RunResult, run_workflow
from imagechoom.promptlab import PromptLabWidget, generate_prompt_spec, promptspec_to_v1_toolcall
from imagechoom.run_queue import PromptLabConfig, QueueJob, QueueStore, RunRecord
from imagechoom.settings import AppSettings, check_a1111_health, load_settings, save_settings
from choomlang.dsl import parse_dsl
from imagechoom.workflows import (
    A1111Txt2ImgCall,
    discover_workflows,
    normalize_workflow_for_run,
    parse_v1_toolcall_lines,
    read_workflow_text,
    render_v1_toolcall_lines,
)


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


class QueueWorker(QThread):
    """Background worker that drains persisted jobs and records runs."""

    log_line = Signal(str)
    run_recorded = Signal(object)
    queue_status = Signal(str)

    def __init__(self, *, queue_store: QueueStore, settings: AppSettings) -> None:
        super().__init__()
        self.queue_store = queue_store
        self.settings = settings
        self._running = True
        self._continuous_enabled = False

    def enable_continuous(self) -> None:
        self._continuous_enabled = True

    def request_pause(self) -> None:
        self._continuous_enabled = False

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        while self._running:
            if not self._continuous_enabled:
                self.msleep(200)
                continue

            job = self.queue_store.pop_next_job()
            if job is None:
                self.queue_status.emit("Queue idle")
                self.msleep(300)
                continue

            remaining = len(self.queue_store.list_jobs())
            self.queue_status.emit(f"Running {job.run_name} ({remaining} queued)")
            record = self._execute_job(job)
            self.queue_store.append_run(record)
            self.run_recorded.emit(record)

            if not self._continuous_enabled:
                self.queue_status.emit("Paused after current job")

    def _execute_job(self, job: QueueJob) -> RunRecord:
        try:
            if job.job_type == "GenerateThenRun":
                if job.promptlab is None:
                    raise ValueError("GenerateThenRun job missing Prompt Lab config")
                return self._run_generate_then_run(job)
            return self._run_workflow_text(job)
        except Exception as exc:  # noqa: BLE001 - persist for history
            return RunRecord(
                id=str(uuid.uuid4()),
                timestamp=_now_iso(),
                job_type=job.job_type,
                run_name=job.run_name,
                theme=job.promptlab.theme if job.promptlab else "",
                status="failed",
                prompt_json={},
                normalized_text=job.normalized_text or "",
                artifacts_dir="",
                image_paths=[],
                error=str(exc),
            )

    def _run_workflow_text(self, job: QueueJob) -> RunRecord:
        normalized_text = job.normalized_text or ""
        self.log_line.emit(f"Running workflow text: {job.run_name}")
        result = run_workflow(normalized_text, job.run_name, self.settings, on_log=self.log_line.emit)
        return RunRecord(
            id=str(uuid.uuid4()),
            timestamp=_now_iso(),
            job_type=job.job_type,
            run_name=job.run_name,
            theme="",
            status="success" if result.success else "failed",
            prompt_json={},
            normalized_text=normalized_text,
            artifacts_dir=str(result.run_dir),
            image_paths=[str(path) for path in result.image_paths],
            error=result.error,
        )

    def _run_generate_then_run(self, job: QueueJob) -> RunRecord:
        config = job.promptlab
        assert config is not None
        self.log_line.emit(f"Generating prompt with Ollama for theme: {config.theme}")
        prompt = generate_prompt_spec(
            model=config.model,
            theme=config.theme,
            preset=config.preset,
            creativity=config.creativity,
            timeout_s=config.timeout_s,
        )
        normalized_text = promptspec_to_v1_toolcall(prompt.spec)
        run_name = job.run_name
        self.log_line.emit("Executing generated workflow in A1111")
        result = run_workflow(normalized_text, run_name, self.settings, on_log=self.log_line.emit)
        return RunRecord(
            id=str(uuid.uuid4()),
            timestamp=_now_iso(),
            job_type=job.job_type,
            run_name=run_name,
            theme=config.theme,
            status="success" if result.success else "failed",
            prompt_json=prompt.raw_json,
            normalized_text=normalized_text,
            artifacts_dir=str(result.run_dir),
            image_paths=[str(path) for path in result.image_paths],
            error=result.error,
        )


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class MainWindow(QMainWindow):
    """Primary application window with sidebar navigation and stacked pages."""

    SECTION_NAMES = ("Workflows", "Presets", "Prompt Lab", "Runs")

    def __init__(self, *, imagechoom_root: Path) -> None:
        super().__init__()
        self.imagechoom_root = imagechoom_root
        self.settings = load_settings(self.imagechoom_root)
        self._run_worker: RunWorker | None = None
        self._run_records: list[RunRecord] = []
        self._selected_run: RunRecord | None = None

        self._workflow_items = discover_workflows(self.imagechoom_root)
        self._workflow_editor_calls: list[A1111Txt2ImgCall] = []
        self._suspend_sync = False
        self._current_workflow_path: Path | None = None
        self.queue_store = QueueStore()
        self._run_records = self.queue_store.list_runs()

        self._queue_worker = QueueWorker(queue_store=self.queue_store, settings=self.settings)
        self._queue_worker.log_line.connect(self._append_run_log_line)
        self._queue_worker.queue_status.connect(self._set_queue_status)
        self._queue_worker.run_recorded.connect(self._on_run_recorded)
        self._queue_worker.start()

        self.setObjectName("mainWindow")
        self.setWindowTitle("ImageChoom")
        self.resize(1100, 760)

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

        self._refresh_queue_list()
        self._refresh_runs_table()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._queue_worker.stop()
        self._queue_worker.wait(1000)
        super().closeEvent(event)

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
        self.workflow_path_label.setWordWrap(True)
        detail_layout.addWidget(self.workflow_path_label)

        self.workflow_warnings_label = QLabel("")
        self.workflow_warnings_label.setWordWrap(True)
        self.workflow_warnings_label.hide()
        detail_layout.addWidget(self.workflow_warnings_label)

        detail_layout.addWidget(self._build_settings_panel())
        detail_layout.addWidget(self._build_workflow_editor_actions())
        detail_layout.addWidget(self._build_run_panel())

        editor_splitter = QSplitter(Qt.Orientation.Horizontal)
        editor_splitter.setObjectName("workflowEditorSplitter")

        self.workflow_form_editor = self._build_workflow_form_editor()
        editor_splitter.addWidget(self.workflow_form_editor)

        raw_panel = QWidget()
        raw_layout = QVBoxLayout(raw_panel)
        raw_layout.setContentsMargins(0, 0, 0, 0)
        raw_layout.addWidget(QLabel("Raw v1 DSL (.choom)"))
        self.workflow_raw_text = QPlainTextEdit()
        self.workflow_raw_text.textChanged.connect(self._sync_from_raw_editor)
        raw_layout.addWidget(self.workflow_raw_text, 1)
        editor_splitter.addWidget(raw_panel)
        editor_splitter.setStretchFactor(0, 0)
        editor_splitter.setStretchFactor(1, 1)

        detail_layout.addWidget(editor_splitter, 1)

        detail_layout.addWidget(QLabel("Validation"))
        self.workflow_validation_text = QPlainTextEdit()
        self.workflow_validation_text.setReadOnly(True)
        self.workflow_validation_text.setMaximumBlockCount(500)
        detail_layout.addWidget(self.workflow_validation_text)

        detail_layout.addWidget(QLabel("Run logs"))
        self.run_logs_text = QPlainTextEdit()
        self.run_logs_text.setReadOnly(True)
        self.run_logs_text.setMaximumBlockCount(2000)
        detail_layout.addWidget(self.run_logs_text, 1)

        detail_layout.addWidget(QLabel("Generated images"))
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

    def _build_workflow_editor_actions(self) -> QWidget:
        panel = QWidget()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self.new_workflow_button = QPushButton("New v1 Workflow")
        self.new_workflow_button.clicked.connect(self._new_v1_workflow)
        layout.addWidget(self.new_workflow_button)

        self.create_from_promptlab_button = QPushButton("Create from Prompt Lab output")
        self.create_from_promptlab_button.clicked.connect(self._create_from_promptlab_output)
        layout.addWidget(self.create_from_promptlab_button)

        self.validate_workflow_button = QPushButton("Validate")
        self.validate_workflow_button.clicked.connect(self._validate_workflow_lines)
        layout.addWidget(self.validate_workflow_button)

        self.save_workflow_button = QPushButton("Save")
        self.save_workflow_button.clicked.connect(self._save_workflow)
        layout.addWidget(self.save_workflow_button)

        self.save_workflow_as_button = QPushButton("Save As")
        self.save_workflow_as_button.clicked.connect(self._save_workflow_as)
        layout.addWidget(self.save_workflow_as_button)

        layout.addStretch(1)
        return panel

    def _build_workflow_form_editor(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Structured fields (first a1111_txt2img call)"))

        form = QFormLayout()
        self.workflow_prompt_input = QPlainTextEdit()
        self.workflow_prompt_input.setMaximumHeight(100)
        self.workflow_prompt_input.textChanged.connect(self._sync_from_form_editor)
        form.addRow("Prompt", self.workflow_prompt_input)

        self.workflow_negative_input = QPlainTextEdit()
        self.workflow_negative_input.setMaximumHeight(80)
        self.workflow_negative_input.textChanged.connect(self._sync_from_form_editor)
        form.addRow("Negative", self.workflow_negative_input)

        self.workflow_width_input = QSpinBox()
        self.workflow_width_input.setRange(64, 4096)
        self.workflow_width_input.valueChanged.connect(self._sync_from_form_editor)
        form.addRow("Width", self.workflow_width_input)

        self.workflow_height_input = QSpinBox()
        self.workflow_height_input.setRange(64, 4096)
        self.workflow_height_input.valueChanged.connect(self._sync_from_form_editor)
        form.addRow("Height", self.workflow_height_input)

        self.workflow_steps_input = QSpinBox()
        self.workflow_steps_input.setRange(1, 300)
        self.workflow_steps_input.valueChanged.connect(self._sync_from_form_editor)
        form.addRow("Steps", self.workflow_steps_input)

        self.workflow_cfg_input = QDoubleSpinBox()
        self.workflow_cfg_input.setRange(0.0, 50.0)
        self.workflow_cfg_input.setDecimals(2)
        self.workflow_cfg_input.setSingleStep(0.1)
        self.workflow_cfg_input.valueChanged.connect(self._sync_from_form_editor)
        form.addRow("CFG", self.workflow_cfg_input)

        self.workflow_sampler_input = QLineEdit()
        self.workflow_sampler_input.textChanged.connect(self._sync_from_form_editor)
        form.addRow("Sampler", self.workflow_sampler_input)

        self.workflow_seed_input = QSpinBox()
        self.workflow_seed_input.setRange(-1_000_000_000, 1_000_000_000)
        self.workflow_seed_input.valueChanged.connect(self._sync_from_form_editor)
        form.addRow("Seed", self.workflow_seed_input)

        self.workflow_n_input = QSpinBox()
        self.workflow_n_input.setRange(1, 100)
        self.workflow_n_input.valueChanged.connect(self._sync_from_form_editor)
        form.addRow("N", self.workflow_n_input)

        self.workflow_base_url_input = QLineEdit()
        self.workflow_base_url_input.textChanged.connect(self._sync_from_form_editor)
        form.addRow("base_url", self.workflow_base_url_input)

        layout.addLayout(form)
        layout.addStretch(1)
        return panel

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
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(QLabel(f"{section_name} page"))
        root_hint_label = QLabel(f"Repo root: {self.imagechoom_root}")
        root_hint_label.setWordWrap(True)
        layout.addWidget(root_hint_label)
        layout.addStretch(1)
        return page

    def _build_prompt_lab_page(self) -> QWidget:
        self.prompt_lab_widget = PromptLabWidget(
            imagechoom_root=self.imagechoom_root,
            on_enqueue_workflow=self._enqueue_promptlab_workflow,
            on_enqueue_generate_jobs=self._enqueue_generate_jobs,
            on_start_continuous=self._start_continuous,
            on_stop_continuous=self._stop_continuous,
        )
        return self.prompt_lab_widget

    def _build_runs_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)

        layout.addWidget(QLabel("Queued jobs"))
        self.runs_queue_list = QListWidget()
        layout.addWidget(self.runs_queue_list)

        queue_controls = QHBoxLayout()
        self.remove_queue_item_button = QPushButton("Remove Selected")
        self.remove_queue_item_button.clicked.connect(self._remove_selected_queue_item)
        queue_controls.addWidget(self.remove_queue_item_button)
        queue_controls.addStretch(1)
        layout.addLayout(queue_controls)

        self.run_queue_status = QLabel("Queue idle")
        layout.addWidget(self.run_queue_status)

        layout.addWidget(QLabel("Run history (latest first)"))
        self.runs_table = QTableWidget(0, 5)
        self.runs_table.setHorizontalHeaderLabels(["Time", "Type", "Name", "Theme", "Status"])
        self.runs_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.runs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.runs_table.itemSelectionChanged.connect(self._on_run_row_selected)
        layout.addWidget(self.runs_table, 1)

        self.run_details_text = QPlainTextEdit()
        self.run_details_text.setReadOnly(True)
        layout.addWidget(self.run_details_text)

        self.runs_gallery_scroll = QScrollArea()
        self.runs_gallery_scroll.setWidgetResizable(True)
        gallery_widget = QWidget()
        self.runs_gallery_layout = QGridLayout(gallery_widget)
        self.runs_gallery_scroll.setWidget(gallery_widget)
        layout.addWidget(self.runs_gallery_scroll, 1)

        action_row = QHBoxLayout()
        self.open_folder_button = QPushButton("Open folder")
        self.open_folder_button.clicked.connect(self._open_selected_run_folder)
        action_row.addWidget(self.open_folder_button)

        self.rerun_button = QPushButton("Rerun")
        self.rerun_button.clicked.connect(self._rerun_selected)
        action_row.addWidget(self.rerun_button)

        self.copy_prompt_button = QPushButton("Copy prompt")
        self.copy_prompt_button.clicked.connect(self._copy_selected_prompt)
        action_row.addWidget(self.copy_prompt_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        return page

    def _handle_sidebar_index_change(self, index: int) -> None:
        if 0 <= index < self.page_stack.count():
            self.page_stack.setCurrentIndex(index)

    def _handle_workflow_selection_change(self, index: int) -> None:
        if not (0 <= index < len(self._workflow_items)):
            self.workflow_path_label.setText("Select a workflow")
            self._suspend_sync = True
            self.workflow_raw_text.clear()
            self.workflow_validation_text.clear()
            self._suspend_sync = False
            self.workflow_warnings_label.hide()
            self._current_workflow_path = None
            return

        workflow = self._workflow_items[index]
        self._current_workflow_path = workflow.path
        self.workflow_path_label.setText(f"{workflow.path.relative_to(self.imagechoom_root)}")

        if workflow.type == "legacy":
            normalized = normalize_workflow_for_run(workflow.path)
            source_text = normalized.normalized_text
            if normalized.warnings:
                warning_text = "Warnings:\n- " + "\n- ".join(normalized.warnings)
                self.workflow_warnings_label.setText(warning_text)
                self.workflow_warnings_label.show()
            else:
                self.workflow_warnings_label.hide()
        else:
            source_text = read_workflow_text(workflow.path)
            self.workflow_warnings_label.hide()

        self._set_editor_text(source_text)

    def _set_editor_text(self, text: str) -> None:
        self._suspend_sync = True
        self.workflow_raw_text.setPlainText(text)
        self.workflow_validation_text.clear()
        self._suspend_sync = False
        self._sync_form_with_raw(text)

    def _sync_form_with_raw(self, text: str) -> None:
        calls = parse_v1_toolcall_lines(text)
        self._workflow_editor_calls = calls
        call = calls[0] if calls else A1111Txt2ImgCall()

        self._suspend_sync = True
        self.workflow_prompt_input.setPlainText(call.prompt)
        self.workflow_negative_input.setPlainText(call.negative)
        self.workflow_width_input.setValue(call.width)
        self.workflow_height_input.setValue(call.height)
        self.workflow_steps_input.setValue(call.steps)
        self.workflow_cfg_input.setValue(call.cfg)
        self.workflow_sampler_input.setText(call.sampler)
        self.workflow_seed_input.setValue(call.seed)
        self.workflow_n_input.setValue(call.n)
        self.workflow_base_url_input.setText(call.base_url)
        self._suspend_sync = False

    def _sync_from_raw_editor(self) -> None:
        if self._suspend_sync:
            return
        self._sync_form_with_raw(self.workflow_raw_text.toPlainText())

    def _sync_from_form_editor(self) -> None:
        if self._suspend_sync:
            return
        call = A1111Txt2ImgCall(
            prompt=self.workflow_prompt_input.toPlainText(),
            negative=self.workflow_negative_input.toPlainText(),
            width=int(self.workflow_width_input.value()),
            height=int(self.workflow_height_input.value()),
            steps=int(self.workflow_steps_input.value()),
            cfg=float(self.workflow_cfg_input.value()),
            sampler=self.workflow_sampler_input.text().strip() or "Euler a",
            seed=int(self.workflow_seed_input.value()),
            n=int(self.workflow_n_input.value()),
            base_url=self.workflow_base_url_input.text().strip(),
        )
        existing = self._workflow_editor_calls[1:] if self._workflow_editor_calls else []
        text = render_v1_toolcall_lines([call, *existing])

        self._suspend_sync = True
        self.workflow_raw_text.setPlainText(text)
        self._suspend_sync = False
        self._workflow_editor_calls = [call, *existing]

    def _validate_workflow_lines(self) -> None:
        lines = self.workflow_raw_text.toPlainText().splitlines()
        if not lines:
            self.workflow_validation_text.setPlainText("No lines to validate.")
            return

        results: list[str] = []
        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                parse_dsl(stripped)
                results.append(f"line {idx}: ok")
            except Exception as exc:  # noqa: BLE001
                results.append(f"line {idx}: error: {exc}")

        self.workflow_validation_text.setPlainText("\n".join(results) if results else "No executable lines.")

    def _new_v1_workflow(self) -> None:
        self._current_workflow_path = None
        self.workflow_path_label.setText("New workflow (unsaved)")
        self._set_editor_text(render_v1_toolcall_lines([A1111Txt2ImgCall()]))

    def _create_from_promptlab_output(self) -> None:
        text = self.prompt_lab_widget.latest_workflow_text()
        if not text:
            QMessageBox.information(self, "Workflows", "No Prompt Lab output found yet. Generate a prompt first.")
            return
        self._current_workflow_path = None
        self.workflow_path_label.setText("From Prompt Lab (unsaved)")
        self._set_editor_text(text)

    def _save_workflow(self) -> None:
        if self._current_workflow_path is None:
            self._save_workflow_as()
            return
        self._current_workflow_path.write_text(self.workflow_raw_text.toPlainText().rstrip() + "\n", encoding="utf-8")
        self._reload_workflow_list(selected_path=self._current_workflow_path)

    def _save_workflow_as(self) -> None:
        workflows_dir = self.imagechoom_root / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save workflow",
            str(workflows_dir / "new_workflow.choom"),
            "Choom Workflows (*.choom)",
        )
        if not file_path:
            return

        target = Path(file_path)
        if target.suffix != ".choom":
            target = target.with_suffix(".choom")
        if workflows_dir not in target.resolve().parents and target.resolve() != workflows_dir.resolve():
            QMessageBox.warning(self, "Save workflow", "Please save workflows inside the workflows/ folder.")
            return

        target.write_text(self.workflow_raw_text.toPlainText().rstrip() + "\n", encoding="utf-8")
        self._current_workflow_path = target
        self._reload_workflow_list(selected_path=target)

    def _reload_workflow_list(self, *, selected_path: Path | None = None) -> None:
        self._workflow_items = discover_workflows(self.imagechoom_root)
        self.workflow_list.clear()
        selected_index = -1
        for idx, workflow in enumerate(self._workflow_items):
            self.workflow_list.addItem(f"{workflow.name} ({workflow.type})")
            if selected_path is not None and workflow.path == selected_path:
                selected_index = idx
        if selected_index >= 0:
            self.workflow_list.setCurrentRow(selected_index)

    def _save_settings_from_ui(self) -> None:
        self.settings = AppSettings(
            a1111_url=self.a1111_url_input.text().strip() or "http://127.0.0.1:7860",
            a1111_timeout=int(self.a1111_timeout_input.value()),
            cancel_on_timeout=self.cancel_on_timeout_input.isChecked(),
            outputs_root=self.settings.outputs_root,
        )
        path = save_settings(self.settings)
        self._queue_worker.settings = self.settings
        self.health_check_status.setText(f"Saved: {path}")

    def _run_health_check(self) -> None:
        self._save_settings_from_ui()
        ok, detail = check_a1111_health(self.settings.a1111_url, self.settings.a1111_timeout)
        self.health_check_status.setText(f"{'Success' if ok else 'Failed'}: {detail}")

    def _run_selected_workflow(self) -> None:
        index = self.workflow_list.currentRow()
        if not (0 <= index < len(self._workflow_items)):
            QMessageBox.warning(self, "Run", "Select a workflow first.")
            return

        self._save_settings_from_ui()
        workflow = self._workflow_items[index]
        normalized = normalize_workflow_for_run(workflow.path)

        self.run_logs_text.clear()
        self._clear_gallery(self.gallery_layout)
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
        self.queue_store.enqueue_runworkflow_text(run_name=run_name, normalized_text=normalized_text)
        self._refresh_queue_list()
        self._set_queue_status(f"Queued jobs: {len(self.queue_store.list_jobs())}")
        self.sidebar.setCurrentRow(3)

    def _enqueue_generate_jobs(self, run_name: str, config: PromptLabConfig, count: int) -> None:
        for index in range(count):
            suffix = f"-{index + 1:03d}" if count > 1 else ""
            self.queue_store.enqueue_generate_then_run(run_name=f"{run_name}{suffix}", config=config)
        self._refresh_queue_list()
        self._set_queue_status(f"Queued jobs: {len(self.queue_store.list_jobs())}")
        self.sidebar.setCurrentRow(3)

    def _start_continuous(self) -> None:
        self._save_settings_from_ui()
        self._queue_worker.enable_continuous()
        self._set_queue_status("Continuous mode running")

    def _stop_continuous(self) -> None:
        self._queue_worker.request_pause()
        self._set_queue_status("Stop requested. Finishing current step...")

    def _remove_selected_queue_item(self) -> None:
        index = self.runs_queue_list.currentRow()
        self.queue_store.remove_job(index)
        self._refresh_queue_list()
        self._set_queue_status(f"Queued jobs: {len(self.queue_store.list_jobs())}")

    def _append_run_log_line(self, line: str) -> None:
        self.run_logs_text.appendPlainText(line)

    def _on_run_finished(self, result: RunResult) -> None:
        self.run_button.setEnabled(True)
        self.run_logs_text.setPlainText("\n".join(result.log_lines))
        self.run_status_label.setText(f"Done ({len(result.image_paths)} images)" if result.success else "Failed")
        self._populate_gallery(self.gallery_layout, result.image_paths)

    def _on_run_recorded(self, record: RunRecord) -> None:
        self._run_records.insert(0, record)
        self._refresh_queue_list()
        self._refresh_runs_table()

    def _set_queue_status(self, text: str) -> None:
        self.run_queue_status.setText(text)

    def _refresh_queue_list(self) -> None:
        self.runs_queue_list.clear()
        for job in self.queue_store.list_jobs():
            self.runs_queue_list.addItem(f"{job.job_type}: {job.run_name}")

    def _refresh_runs_table(self) -> None:
        self._run_records = self.queue_store.list_runs()
        self.runs_table.setRowCount(len(self._run_records))
        for row, run in enumerate(self._run_records):
            values = [run.timestamp, run.job_type, run.run_name, run.theme, run.status]
            for col, value in enumerate(values):
                self.runs_table.setItem(row, col, QTableWidgetItem(value))
        if self._run_records:
            self.runs_table.selectRow(0)

    def _on_run_row_selected(self) -> None:
        row = self.runs_table.currentRow()
        if not (0 <= row < len(self._run_records)):
            self._selected_run = None
            self.run_details_text.clear()
            self._clear_gallery(self.runs_gallery_layout)
            return

        run = self._run_records[row]
        self._selected_run = run
        details = {
            "timestamp": run.timestamp,
            "job_type": run.job_type,
            "run_name": run.run_name,
            "theme": run.theme,
            "status": run.status,
            "artifacts_dir": run.artifacts_dir,
            "error": run.error,
            "prompt_json": run.prompt_json,
        }
        self.run_details_text.setPlainText(json.dumps(details, indent=2, ensure_ascii=False))
        self._populate_gallery(self.runs_gallery_layout, [Path(path) for path in run.image_paths])

    def _open_selected_run_folder(self) -> None:
        if self._selected_run is None or not self._selected_run.artifacts_dir:
            return
        QDesktopServices.openUrl(Path(self._selected_run.artifacts_dir).as_uri())

    def _rerun_selected(self) -> None:
        if self._selected_run is None:
            return
        self.queue_store.enqueue_runworkflow_text(
            run_name=f"rerun-{self._selected_run.run_name}",
            normalized_text=self._selected_run.normalized_text,
        )
        self._refresh_queue_list()
        self._set_queue_status("Rerun queued")

    def _copy_selected_prompt(self) -> None:
        if self._selected_run is None:
            return
        content = json.dumps(self._selected_run.prompt_json, ensure_ascii=False)
        if not content or content == "{}":
            content = self._selected_run.normalized_text
        QGuiApplication.clipboard().setText(content)

    def _clear_gallery(self, layout: QGridLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _populate_gallery(self, layout: QGridLayout, image_paths: list[Path]) -> None:
        self._clear_gallery(layout)
        if not image_paths:
            layout.addWidget(QLabel("No images yet."), 0, 0)
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

            layout.addWidget(tile, row, col)
