"""Persistent GUI settings and network helpers."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


@dataclass(slots=True)
class AppSettings:
    """Runtime settings for ChoomLang/A1111 execution."""

    a1111_url: str
    a1111_timeout: int
    cancel_on_timeout: bool
    outputs_root: str

    @classmethod
    def defaults(cls, repo_root: Path) -> "AppSettings":
        return cls(
            a1111_url="http://127.0.0.1:7860",
            a1111_timeout=180,
            cancel_on_timeout=False,
            outputs_root=str((repo_root / "outputs_gui").resolve()),
        )


def load_settings(repo_root: Path) -> AppSettings:
    """Load persisted settings or create defaults on first launch."""
    config_path = _config_file_path()
    defaults = AppSettings.defaults(repo_root)

    data: dict[str, object] = {}
    if config_path.exists():
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw
        except json.JSONDecodeError:
            data = {}

    settings = AppSettings(
        a1111_url=str(data.get("a1111_url", defaults.a1111_url)),
        a1111_timeout=max(1, int(data.get("a1111_timeout", defaults.a1111_timeout))),
        cancel_on_timeout=bool(data.get("cancel_on_timeout", defaults.cancel_on_timeout)),
        outputs_root=str(Path(data.get("outputs_root", defaults.outputs_root)).expanduser()),
    )
    save_settings(settings)
    return settings


def save_settings(settings: AppSettings) -> Path:
    """Persist settings to disk and ensure output folder exists."""
    config_path = _config_file_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    outputs_root = Path(settings.outputs_root).expanduser()
    outputs_root.mkdir(parents=True, exist_ok=True)
    payload = asdict(settings)
    payload["outputs_root"] = str(outputs_root.resolve())

    config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return config_path


def check_a1111_health(base_url: str, timeout_seconds: int) -> tuple[bool, str]:
    """Ping the A1111 samplers API and return status + detail."""
    root = base_url.rstrip("/")
    url = f"{root}/sdapi/v1/samplers"
    try:
        with urlopen(url, timeout=max(1, int(timeout_seconds))) as response:
            if response.status != 200:
                return False, f"HTTP {response.status}"
            body = response.read().decode("utf-8", errors="ignore")
    except URLError as exc:
        return False, str(exc.reason)
    except OSError as exc:
        return False, str(exc)

    snippet = body.strip().replace("\n", " ")
    if len(snippet) > 80:
        snippet = snippet[:77] + "..."
    return True, snippet or "OK"


def _config_file_path() -> Path:
    if sys.platform.startswith("win") and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "ImageChoom" / "config.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ImageChoom" / "config.json"
    return Path.home() / ".imagechoom" / "config.json"
