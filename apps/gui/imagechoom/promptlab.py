"""Prompt Lab page and Ollama-backed prompt generation helpers."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from .run_queue import PromptLabConfig


@dataclass(slots=True)
class PromptSpec:
    positive: str
    negative: str
    style_tags: list[str]
    sd_params: dict[str, Any]


@dataclass(slots=True)
class PromptLabResult:
    spec: PromptSpec
    raw_json: dict[str, Any]


class PromptLabWidget(QWidget):
    """Prompt Lab controls + output view."""

    def __init__(
        self,
        *,
        imagechoom_root: Path,
        on_enqueue_workflow: Callable[[str, str], None],
        on_enqueue_generate_jobs: Callable[[str, PromptLabConfig, int], None],
        on_start_continuous: Callable[[], None],
        on_stop_continuous: Callable[[], None],
    ) -> None:
        super().__init__()
        self.imagechoom_root = imagechoom_root
        self.on_enqueue_workflow = on_enqueue_workflow
        self.on_enqueue_generate_jobs = on_enqueue_generate_jobs
        self.on_start_continuous = on_start_continuous
        self.on_stop_continuous = on_stop_continuous
        self._last_generated: PromptLabResult | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)

        form = QFormLayout()

        self.model_input = QLineEdit("llama3.1:8b")
        form.addRow("Ollama model", self.model_input)

        self.preset_combo = QComboBox()
        self._preset_map = _load_presets(imagechoom_root)
        self.preset_combo.addItems(self._preset_map.keys())
        form.addRow("Preset", self.preset_combo)

        self.theme_input = QLineEdit()
        self.theme_input.setPlaceholderText("neon tokyo ramen shop interior")
        form.addRow("Theme", self.theme_input)

        creativity_row = QWidget()
        creativity_layout = QHBoxLayout(creativity_row)
        creativity_layout.setContentsMargins(0, 0, 0, 0)
        self.creativity_slider = QSlider(Qt.Orientation.Horizontal)
        self.creativity_slider.setRange(0, 100)
        self.creativity_slider.setValue(35)
        self.creativity_label = QLabel("0.35")
        self.creativity_slider.valueChanged.connect(self._sync_creativity_label)
        creativity_layout.addWidget(self.creativity_slider)
        creativity_layout.addWidget(self.creativity_label)
        form.addRow("Temperature / creativity", creativity_row)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setValue(60)
        form.addRow("Ollama timeout (s)", self.timeout_spin)

        root.addLayout(form)

        continuous_row = QHBoxLayout()
        self.continuous_toggle = QCheckBox("Continuous")
        continuous_row.addWidget(self.continuous_toggle)
        self.target_count_spin = QSpinBox()
        self.target_count_spin.setRange(1, 1000)
        self.target_count_spin.setValue(50)
        continuous_row.addWidget(QLabel("Target count"))
        continuous_row.addWidget(self.target_count_spin)
        continuous_row.addStretch(1)
        root.addLayout(continuous_row)

        actions = QHBoxLayout()
        self.generate_button = QPushButton("Generate")
        self.generate_button.clicked.connect(self._generate)
        actions.addWidget(self.generate_button)

        self.enqueue_button = QPushButton("Send to Run Queue")
        self.enqueue_button.setEnabled(False)
        self.enqueue_button.clicked.connect(self._enqueue)
        actions.addWidget(self.enqueue_button)

        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self._start_continuous)
        actions.addWidget(self.start_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self._stop_continuous)
        actions.addWidget(self.stop_button)
        actions.addStretch(1)
        root.addLayout(actions)

        self.positive_output = QPlainTextEdit()
        self.positive_output.setPlaceholderText("Positive prompt")
        root.addWidget(QLabel("Positive"))
        root.addWidget(self.positive_output)

        self.negative_output = QPlainTextEdit()
        self.negative_output.setPlaceholderText("Negative prompt")
        root.addWidget(QLabel("Negative"))
        root.addWidget(self.negative_output)

        self.tags_output = QLineEdit()
        self.tags_output.setReadOnly(True)
        root.addWidget(QLabel("Style tags"))
        root.addWidget(self.tags_output)

        self.params_output = QLineEdit()
        self.params_output.setReadOnly(True)
        root.addWidget(QLabel("SD params"))
        root.addWidget(self.params_output)

    def latest_workflow_text(self) -> str | None:
        if self._last_generated is None:
            return None
        spec = PromptSpec(
            positive=self.positive_output.toPlainText().strip() or self._last_generated.spec.positive,
            negative=self.negative_output.toPlainText().strip() or self._last_generated.spec.negative,
            style_tags=list(self._last_generated.spec.style_tags),
            sd_params=dict(self._last_generated.spec.sd_params),
        )
        return promptspec_to_v1_toolcall(spec)

    def _sync_creativity_label(self, value: int) -> None:
        self.creativity_label.setText(f"{value/100:.2f}")

    def _generate(self) -> None:
        theme = self.theme_input.text().strip()
        if not theme:
            QMessageBox.warning(self, "Prompt Lab", "Enter a theme first.")
            return

        model = self.model_input.text().strip()
        if not model:
            QMessageBox.warning(self, "Prompt Lab", "Enter an Ollama model.")
            return

        preset = self._preset_map.get(self.preset_combo.currentText(), {})
        creativity = self.creativity_slider.value() / 100

        try:
            result = generate_prompt_spec(
                model=model,
                theme=theme,
                preset=preset,
                creativity=creativity,
                timeout_s=int(self.timeout_spin.value()),
            )
        except Exception as exc:  # noqa: BLE001 - show directly to user
            QMessageBox.critical(self, "Prompt Lab", f"Failed to generate: {exc}")
            return

        self._last_generated = result
        self.enqueue_button.setEnabled(True)
        self.positive_output.setPlainText(result.spec.positive)
        self.negative_output.setPlainText(result.spec.negative)
        self.tags_output.setText(", ".join(result.spec.style_tags))
        self.params_output.setText(json.dumps(result.spec.sd_params, ensure_ascii=False))

    def _enqueue(self) -> None:
        if self._last_generated is None:
            QMessageBox.warning(self, "Prompt Lab", "Generate a prompt first.")
            return

        spec = self._last_generated.spec
        spec = PromptSpec(
            positive=self.positive_output.toPlainText().strip(),
            negative=self.negative_output.toPlainText().strip(),
            style_tags=list(spec.style_tags),
            sd_params=dict(spec.sd_params),
        )
        workflow_text = promptspec_to_v1_toolcall(spec)
        run_name = f"promptlab-{self.theme_input.text().strip() or 'untitled'}"
        self.on_enqueue_workflow(run_name, workflow_text)
        QMessageBox.information(self, "Prompt Lab", "Queued prompt for run execution.")

    def _start_continuous(self) -> None:
        theme = self.theme_input.text().strip()
        if not theme:
            QMessageBox.warning(self, "Prompt Lab", "Enter a theme first.")
            return
        config = self._build_promptlab_config(theme=theme)
        count = int(self.target_count_spin.value()) if self.continuous_toggle.isChecked() else 1
        self.on_enqueue_generate_jobs(f"promptlab-{theme}", config, count)
        self.on_start_continuous()
        QMessageBox.information(self, "Prompt Lab", f"Queued {count} prompt job(s).")

    def _stop_continuous(self) -> None:
        self.on_stop_continuous()

    def _build_promptlab_config(self, *, theme: str) -> PromptLabConfig:
        model = self.model_input.text().strip()
        if not model:
            raise ValueError("Ollama model is required")
        preset_name = self.preset_combo.currentText()
        return PromptLabConfig(
            model=model,
            preset_name=preset_name,
            preset=self._preset_map.get(preset_name, {}),
            theme=theme,
            creativity=self.creativity_slider.value() / 100,
            timeout_s=int(self.timeout_spin.value()),
        )


def generate_prompt_spec(
    *,
    model: str,
    theme: str,
    preset: dict[str, Any],
    creativity: float,
    timeout_s: int,
) -> PromptLabResult:
    system_prompt = _build_system_prompt(creativity=creativity)
    user_prompt = _build_user_prompt(theme=theme, preset=preset)

    payload = _call_ollama_generate(
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        creativity=creativity,
        timeout_s=timeout_s,
    )

    try:
        validated = _validate_prompt_spec(payload)
    except ValueError:
        repair_prompt = (
            "Repair this output to match the JSON schema exactly. "
            "Return JSON only.\n\n"
            f"Invalid output:\n{json.dumps(payload, ensure_ascii=False)}"
        )
        repaired = _call_ollama_generate(
            model=model,
            system_prompt=system_prompt,
            user_prompt=repair_prompt,
            creativity=creativity,
            timeout_s=timeout_s,
        )
        validated = _validate_prompt_spec(repaired)

    return PromptLabResult(spec=validated, raw_json=payload)


def promptspec_to_v1_toolcall(spec: PromptSpec) -> str:
    params = spec.sd_params
    tagged_positive = spec.positive
    if spec.style_tags:
        tagged_positive = f"{tagged_positive}, {', '.join(spec.style_tags)}"

    return (
        "toolcall tool name=a1111_txt2img id=images "
        f'prompt={_quoted(tagged_positive)} negative={_quoted(spec.negative)} '
        f"width={int(params['width'])} height={int(params['height'])} "
        f"steps={int(params['steps'])} cfg={float(params['cfg'])} "
        f"seed={int(params['seed'])} n={int(params['n'])} "
        f"sampler={_quoted(str(params['sampler']))}"
    )


def _build_system_prompt(*, creativity: float) -> str:
    return (
        "You are a Stable Diffusion prompt engineer. "
        "Output ONLY valid JSON and nothing else. "
        "Follow this schema exactly:\n"
        "{"
        '"positive":"string",'
        '"negative":"string",'
        '"style_tags":["string"],'
        '"sd_params":{"width":int,"height":int,"steps":int,"cfg":float,'
        '"sampler":"string","seed":int,"n":int}'
        "}\n"
        "Use concise cinematic phrasing. "
        "No markdown. No comments.\n"
        f"Creativity level: {creativity:.2f}. Lower means safer defaults; higher means richer details."
    )


def _build_user_prompt(*, theme: str, preset: dict[str, Any]) -> str:
    return (
        f"Theme: {theme}\n"
        f"Preset JSON: {json.dumps(preset, ensure_ascii=False)}\n"
        "Produce one prompt spec for SD txt2img suitable for A1111. "
        "Prefer practical defaults: width/height among [512,768,1024], steps 20-40, cfg 4.5-9. "
        "seed can be -1 for random."
    )


def _call_ollama_generate(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    creativity: float,
    timeout_s: int,
) -> dict[str, Any]:
    request_payload = {
        "model": model,
        "system": system_prompt,
        "prompt": user_prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": creativity},
    }
    data = json.dumps(request_payload).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Unable to reach Ollama at 127.0.0.1:11434 ({exc})") from exc

    decoded = json.loads(raw)
    response_text = decoded.get("response", "")
    if isinstance(response_text, dict):
        return response_text
    if not isinstance(response_text, str):
        raise ValueError("Ollama response missing `response` text")

    parsed = json.loads(response_text)
    if not isinstance(parsed, dict):
        raise ValueError("Model output was not a JSON object")
    return parsed


def _validate_prompt_spec(payload: dict[str, Any]) -> PromptSpec:
    positive = payload.get("positive")
    negative = payload.get("negative")
    style_tags = payload.get("style_tags")
    sd_params = payload.get("sd_params")

    if not isinstance(positive, str) or not positive.strip():
        raise ValueError("`positive` must be a non-empty string")
    if not isinstance(negative, str):
        raise ValueError("`negative` must be a string")
    if not isinstance(style_tags, list) or not all(isinstance(tag, str) for tag in style_tags):
        raise ValueError("`style_tags` must be a list of strings")
    if not isinstance(sd_params, dict):
        raise ValueError("`sd_params` must be an object")

    normalized = {
        "width": _as_int(sd_params.get("width"), "width"),
        "height": _as_int(sd_params.get("height"), "height"),
        "steps": _as_int(sd_params.get("steps"), "steps"),
        "cfg": _as_float(sd_params.get("cfg"), "cfg"),
        "sampler": str(sd_params.get("sampler", "Euler a")),
        "seed": _as_int(sd_params.get("seed"), "seed"),
        "n": _as_int(sd_params.get("n"), "n"),
    }

    return PromptSpec(
        positive=positive.strip(),
        negative=negative.strip(),
        style_tags=[tag.strip() for tag in style_tags if tag.strip()],
        sd_params=normalized,
    )


def _as_int(value: Any, name: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"`{name}` must be an int")
    return value


def _as_float(value: Any, name: str) -> float:
    if not isinstance(value, (int, float)):
        raise ValueError(f"`{name}` must be a float")
    return float(value)


def _load_presets(imagechoom_root: Path) -> dict[str, dict[str, Any]]:
    presets_dir = imagechoom_root / "presets"
    options: dict[str, dict[str, Any]] = {}
    for path in sorted(presets_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            options[path.stem] = data
    if not options:
        options["default"] = {}
    return options


def _quoted(value: str) -> str:
    return '"' + value.replace('"', '\\"') + '"'
