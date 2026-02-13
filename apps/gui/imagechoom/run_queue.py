"""Persistent queue + run history for ImageChoom GUI."""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class PromptLabConfig:
    model: str
    preset_name: str
    preset: dict[str, Any]
    theme: str
    creativity: float
    timeout_s: int


@dataclass(slots=True)
class QueueJob:
    id: str
    job_type: str
    created_at: str
    run_name: str
    normalized_text: str | None = None
    promptlab: PromptLabConfig | None = None


@dataclass(slots=True)
class RunRecord:
    id: str
    timestamp: str
    job_type: str
    run_name: str
    theme: str
    status: str
    prompt_json: dict[str, Any]
    normalized_text: str
    artifacts_dir: str
    image_paths: list[str]
    error: str | None


class QueueStore:
    def __init__(self) -> None:
        self.root = Path.home() / ".imagechoom"
        self.queue_path = self.root / "queue.json"
        self.runs_path = self.root / "runs.jsonl"
        self._lock = threading.Lock()
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.queue_path.exists():
            self.queue_path.write_text("[]", encoding="utf-8")

    def enqueue_runworkflow_text(self, *, run_name: str, normalized_text: str) -> QueueJob:
        return self._append_job(
            QueueJob(
                id=str(uuid.uuid4()),
                job_type="RunWorkflowText",
                created_at=_now_iso(),
                run_name=run_name,
                normalized_text=normalized_text,
            )
        )

    def enqueue_generate_then_run(self, *, run_name: str, config: PromptLabConfig) -> QueueJob:
        return self._append_job(
            QueueJob(
                id=str(uuid.uuid4()),
                job_type="GenerateThenRun",
                created_at=_now_iso(),
                run_name=run_name,
                promptlab=config,
            )
        )

    def _append_job(self, job: QueueJob) -> QueueJob:
        with self._lock:
            queue = self._read_queue()
            queue.append(_job_to_dict(job))
            self._write_queue(queue)
        return job

    def remove_job(self, index: int) -> None:
        with self._lock:
            queue = self._read_queue()
            if 0 <= index < len(queue):
                del queue[index]
                self._write_queue(queue)

    def pop_next_job(self) -> QueueJob | None:
        with self._lock:
            queue = self._read_queue()
            if not queue:
                return None
            raw = queue.pop(0)
            self._write_queue(queue)
        return _job_from_dict(raw)

    def list_jobs(self) -> list[QueueJob]:
        with self._lock:
            queue = self._read_queue()
        return [_job_from_dict(item) for item in queue]

    def append_run(self, record: RunRecord) -> None:
        payload = json.dumps(asdict(record), ensure_ascii=False)
        with self._lock:
            with self.runs_path.open("a", encoding="utf-8") as handle:
                handle.write(payload + "\n")

    def list_runs(self) -> list[RunRecord]:
        if not self.runs_path.exists():
            return []
        records: list[RunRecord] = []
        with self._lock:
            lines = self.runs_path.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict):
                records.append(_run_from_dict(raw))
        return records

    def _read_queue(self) -> list[dict[str, Any]]:
        try:
            raw = json.loads(self.queue_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        return raw if isinstance(raw, list) else []

    def _write_queue(self, queue: list[dict[str, Any]]) -> None:
        self.queue_path.write_text(json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _job_to_dict(job: QueueJob) -> dict[str, Any]:
    payload = asdict(job)
    return payload


def _job_from_dict(payload: dict[str, Any]) -> QueueJob:
    promptlab = payload.get("promptlab")
    config = PromptLabConfig(**promptlab) if isinstance(promptlab, dict) else None
    return QueueJob(
        id=str(payload.get("id", uuid.uuid4())),
        job_type=str(payload.get("job_type", "RunWorkflowText")),
        created_at=str(payload.get("created_at", _now_iso())),
        run_name=str(payload.get("run_name", "queued-run")),
        normalized_text=payload.get("normalized_text") if isinstance(payload.get("normalized_text"), str) else None,
        promptlab=config,
    )


def _run_from_dict(payload: dict[str, Any]) -> RunRecord:
    return RunRecord(
        id=str(payload.get("id", uuid.uuid4())),
        timestamp=str(payload.get("timestamp", _now_iso())),
        job_type=str(payload.get("job_type", "RunWorkflowText")),
        run_name=str(payload.get("run_name", "unknown")),
        theme=str(payload.get("theme", "")),
        status=str(payload.get("status", "failed")),
        prompt_json=payload.get("prompt_json") if isinstance(payload.get("prompt_json"), dict) else {},
        normalized_text=str(payload.get("normalized_text", "")),
        artifacts_dir=str(payload.get("artifacts_dir", "")),
        image_paths=[str(path) for path in payload.get("image_paths", []) if isinstance(path, str)],
        error=str(payload.get("error")) if payload.get("error") else None,
    )
