"""Workflow execution bridge from GUI to ChoomLang runner."""

from __future__ import annotations

import contextlib
import io
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .settings import AppSettings


@dataclass(slots=True)
class RunResult:
    """Execution result presented in the GUI."""

    run_dir: Path
    log_lines: list[str]
    image_paths: list[Path]
    success: bool
    error: str | None = None


def run_workflow(
    normalized_text: str,
    run_name: str,
    settings: AppSettings,
    *,
    on_log: Callable[[str], None] | None = None,
) -> RunResult:
    """Execute a normalized workflow using ChoomLang and return outputs."""
    run_dir = _make_run_dir(Path(settings.outputs_root), run_name)
    run_dir.mkdir(parents=True, exist_ok=True)

    logs: list[str] = [f"run_dir={run_dir}"]
    stdout_buffer = _LogCapture(on_log=on_log)

    try:
        from choomlang.runner import Runner, RunnerConfig  # type: ignore

        config = RunnerConfig(
            a1111_url=settings.a1111_url,
            timeout=settings.a1111_timeout,
            cancel_on_timeout=settings.cancel_on_timeout,
            artifacts_dir=str(run_dir),
        )
        runner = Runner(config=config)

        with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stdout_buffer):
            _invoke_runner(runner, normalized_text)

    except Exception as exc:  # noqa: BLE001 - shown in UI
        stdout_buffer.flush()
        logs.extend(_buffer_lines(stdout_buffer))
        logs.append(f"ERROR: {exc}")
        return RunResult(
            run_dir=run_dir,
            log_lines=logs,
            image_paths=sorted(run_dir.rglob("*.png")),
            success=False,
            error=str(exc),
        )

    stdout_buffer.flush()
    logs.extend(_buffer_lines(stdout_buffer))
    images = sorted(run_dir.rglob("*.png"))
    if not images:
        logs.append("No PNG artifacts generated.")
    return RunResult(run_dir=run_dir, log_lines=logs, image_paths=images, success=True)


def _invoke_runner(runner: Any, normalized_text: str) -> Any:
    for method_name in ("run", "run_script", "execute"):
        method = getattr(runner, method_name, None)
        if callable(method):
            return method(normalized_text)
    raise RuntimeError("Unable to find runnable method on choomlang.runner.Runner")


def _make_run_dir(outputs_root: Path, run_name: str) -> Path:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", run_name.strip().lower()).strip("-") or "workflow"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return outputs_root.expanduser() / f"run-{timestamp}-{slug}"


def _buffer_lines(buffer: io.StringIO) -> list[str]:
    text = buffer.getvalue().strip()
    return text.splitlines() if text else []


class _LogCapture(io.StringIO):
    def __init__(self, *, on_log: Callable[[str], None] | None = None) -> None:
        super().__init__()
        self._on_log = on_log
        self._pending = ""

    def write(self, text: str) -> int:
        written = super().write(text)
        if self._on_log is None or not text:
            return written

        self._pending += text
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", maxsplit=1)
            stripped = line.strip()
            if stripped:
                self._on_log(stripped)
        return written

    def flush(self) -> None:
        super().flush()
        if self._on_log is None:
            return
        tail = self._pending.strip()
        if tail:
            self._on_log(tail)
        self._pending = ""
