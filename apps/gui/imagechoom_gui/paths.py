"""Path resolution utilities for locating the ImageChoom repository root."""

from __future__ import annotations

import os
from pathlib import Path

IMAGECHOOM_ROOT_ENV_VAR = "IMAGECHOOM_ROOT"
_REQUIRED_MARKERS = (
    ("workflows", "dir"),
    ("presets", "dir"),
    ("README.md", "file"),
)


class ImageChoomRootNotFoundError(RuntimeError):
    """Raised when the ImageChoom repository root cannot be resolved."""


def resolve_imagechoom_root(start_path: Path | None = None) -> Path:
    """Resolve the ImageChoom root directory.

    Resolution order:
    1. Use ``IMAGECHOOM_ROOT`` when set.
    2. Walk upward from this module (or ``start_path`` when provided) until
       all expected repository markers are found.

    Returns:
        A validated absolute path to the repository root.

    Raises:
        ImageChoomRootNotFoundError: If no valid repository root is discovered.
    """
    env_override = os.environ.get(IMAGECHOOM_ROOT_ENV_VAR)
    if env_override:
        return _validate_root_candidate(Path(env_override).expanduser(), source="environment variable")

    if start_path is None:
        start_path = Path(__file__)

    search_from = start_path.resolve()
    if search_from.is_file():
        search_from = search_from.parent

    for candidate in (search_from, *search_from.parents):
        if _has_required_markers(candidate):
            return candidate

    required = ", ".join(marker for marker, _ in _REQUIRED_MARKERS)
    raise ImageChoomRootNotFoundError(
        f"Unable to locate ImageChoom root from '{search_from}'. Expected markers: {required}. "
        f"Set {IMAGECHOOM_ROOT_ENV_VAR} to override discovery."
    )


def _validate_root_candidate(candidate: Path, *, source: str) -> Path:
    resolved = candidate.resolve()
    if not resolved.exists():
        raise ImageChoomRootNotFoundError(
            f"Invalid ImageChoom root from {source}: '{resolved}' does not exist."
        )
    if not resolved.is_dir():
        raise ImageChoomRootNotFoundError(
            f"Invalid ImageChoom root from {source}: '{resolved}' is not a directory."
        )
    if not _has_required_markers(resolved):
        required = ", ".join(marker for marker, _ in _REQUIRED_MARKERS)
        raise ImageChoomRootNotFoundError(
            f"Invalid ImageChoom root from {source}: '{resolved}' is missing required markers ({required})."
        )
    return resolved


def _has_required_markers(path: Path) -> bool:
    for marker, marker_type in _REQUIRED_MARKERS:
        marker_path = path / marker
        if marker_type == "dir" and not marker_path.is_dir():
            return False
        if marker_type == "file" and not marker_path.is_file():
            return False
    return True
