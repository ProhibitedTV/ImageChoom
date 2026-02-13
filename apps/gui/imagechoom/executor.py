"""Workflow execution bridge from GUI to ChoomLang runner."""

from __future__ import annotations

import contextlib
import io
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .settings import AppSettings


@dataclass(slots=True)
class RunResult:
    """Execution result presented in the GUI."""

    run_dir: Path
    log_lines: list[str]
    image_paths: list[Path]
    success: bool
    error: str | None = None


def run_workflow(normalized_text: str, run_name: str, settings: AppSettings) -> RunResult:
    """Execute a normalized workflow using ChoomLang and return outputs."""
    run_dir = _make_run_dir(Path(settings.outputs_root), run_name)
    run_dir.mkdir(parents=True, exist_ok=True)

    logs: list[str] = [f"run_dir={run_dir}"]
    stdout_buffer = io.StringIO()

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
        logs.extend(_buffer_lines(stdout_buffer))
        logs.append(f"ERROR: {exc}")
        return RunResult(
            run_dir=run_dir,
            log_lines=logs,
            image_paths=sorted(run_dir.rglob("*.png")),
            success=False,
            error=str(exc),
        )

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
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return outputs_root.expanduser() / f"run-{timestamp}-{slug}"


def _buffer_lines(buffer: io.StringIO) -> list[str]:
    text = buffer.getvalue().strip()
    return text.splitlines() if text else []
