"""Workflow discovery and legacy-to-v1 normalization helpers."""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class WorkflowMetadata:
    """Information used to render workflow choices in the GUI."""

    name: str
    path: Path
    type: str


@dataclass(slots=True)
class NormalizedWorkflow:
    """Normalized, runner-ready workflow representation."""

    normalized_text: str
    warnings: list[str]


def discover_workflows(repo_root: Path) -> list[WorkflowMetadata]:
    """Return discovered workflow files under `<repo_root>/workflows`."""
    workflow_root = repo_root / "workflows"
    if not workflow_root.exists():
        return []

    discovered: list[WorkflowMetadata] = []
    for path in sorted(workflow_root.glob("*.choom")):
        text = read_workflow_text(path)
        detected_type = "v1" if _looks_like_v1_workflow(text) else "legacy"
        discovered.append(
            WorkflowMetadata(name=path.stem, path=path, type=detected_type)
        )
    return discovered


def read_workflow_text(path: Path) -> str:
    """Read workflow source text as UTF-8."""
    return path.read_text(encoding="utf-8")


def legacy_to_v1_toolcalls(text: str, *, base_dir: Path | None = None) -> str:
    """Convert currently-used legacy workflow patterns into one v1 toolcall line."""
    payload = _extract_payload_dict(text, base_dir=base_dir)

    prompt = payload.get("prompt", "")
    negative_prompt = payload.get("negative_prompt", "")
    width = payload.get("width", 1024)
    height = payload.get("height", 1024)
    steps = payload.get("steps", 30)
    cfg_scale = payload.get("cfg_scale", 7)
    seed = payload.get("seed", -1)
    batch_size = payload.get("batch_size", 1)
    sampler_name = payload.get("sampler_name", "Euler a")

    line = (
        "toolcall tool name=a1111_txt2img id=images "
        f'prompt={_quoted(prompt)} negative={_quoted(negative_prompt)} '
        f"width={width} height={height} steps={steps} cfg={cfg_scale} "
        f"seed={seed} n={batch_size} sampler={_quoted(sampler_name)}"
    )

    model_checkpoint = _extract_model_checkpoint(payload)
    if model_checkpoint:
        line = f"{line}\n# legacy sd_model_checkpoint={model_checkpoint}"

    return line


def normalize_workflow_for_run(path: Path) -> NormalizedWorkflow:
    """Normalize a workflow for execution by the ChoomLang v1 runner."""
    source = read_workflow_text(path)
    if _looks_like_v1_workflow(source):
        return NormalizedWorkflow(normalized_text=source, warnings=[])

    warnings: list[str] = []
    if "output_file" in source:
        warnings.append("legacy output_file ignored; using artifacts_dir outputs")

    payload = _extract_payload_dict(source, base_dir=path.parent.parent)
    model_checkpoint = _extract_model_checkpoint(payload)
    if model_checkpoint:
        warnings.append(
            "legacy override_settings.sd_model_checkpoint preserved as comment in preview"
        )

    return NormalizedWorkflow(
        normalized_text=legacy_to_v1_toolcalls(source, base_dir=path.parent.parent),
        warnings=warnings,
    )


def _looks_like_v1_workflow(text: str) -> bool:
    return any(line.strip().startswith("toolcall tool") for line in text.splitlines())


def _extract_payload_dict(text: str, *, base_dir: Path | None = None) -> dict[str, Any]:
    payload_expr = _extract_set_rhs(text, "payload")
    if payload_expr is None:
        return {}

    payload_expr = payload_expr.strip()
    if payload_expr.startswith("{"):
        return _parse_loose_json(payload_expr)

    if payload_expr.startswith("themes."):
        themes_name = payload_expr.split(".", maxsplit=1)[1]
        themes = _resolve_themes_config(text, base_dir=base_dir)
        if isinstance(themes, dict):
            payload = themes.get(themes_name)
            if isinstance(payload, dict):
                return payload

    return {}


def _resolve_themes_config(text: str, *, base_dir: Path | None = None) -> dict[str, Any] | None:
    input_config = _extract_set_rhs(text, "input_config")
    if input_config is None:
        return None

    config_path_value = _unquote(input_config.strip())
    if not config_path_value:
        return None

    candidate = Path(config_path_value)
    if base_dir is not None and not candidate.is_absolute():
        candidate = (base_dir / candidate).resolve()
    if not candidate.exists():
        return None

    try:
        parsed = json.loads(candidate.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_set_rhs(text: str, variable: str) -> str | None:
    pattern = re.compile(rf"^\s*set\s+{re.escape(variable)}\s*=\s*(.+)$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return None

    rhs = match.group(1).strip()
    if rhs.startswith("{"):
        start = match.start(1)
        return _extract_braced_block(text, start)
    return rhs


def _extract_braced_block(text: str, start_index: int) -> str:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start_index, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start_index : index + 1]

    return "{}"


def _parse_loose_json(value: str) -> dict[str, Any]:
    normalized = re.sub(r"\btrue\b", "True", value)
    normalized = re.sub(r"\bfalse\b", "False", normalized)
    normalized = re.sub(r"\bnull\b", "None", normalized)
    try:
        parsed = ast.literal_eval(normalized)
    except (ValueError, SyntaxError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_model_checkpoint(payload: dict[str, Any]) -> str | None:
    override_settings = payload.get("override_settings")
    if not isinstance(override_settings, dict):
        return None
    checkpoint = override_settings.get("sd_model_checkpoint")
    return str(checkpoint) if checkpoint else None


def _quoted(value: Any) -> str:
    escaped = str(value).replace('"', '\\"')
    return f'"{escaped}"'


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value
