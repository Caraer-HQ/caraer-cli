"""Helpers for local app YAML/JSON selection and discovery."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from caraer_cli.project.app_manifest_template import APP_MANIFEST_NAMES
from caraer_cli.project.paths import (
    LEGACY_PROJECT_FILE,
    WORKSPACE_FILE,
    app_manifest_path,
)
from caraer_cli.utils import load_structured_file

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
APP_FILE_NAMES = APP_MANIFEST_NAMES


def looks_like_uuid(value: str) -> bool:
    return bool(UUID_RE.match(value.strip()))


def looks_like_local_app_ref(value: str) -> bool:
    """Heuristic: path-like refs should be treated as local app files/dirs."""
    text = value.strip()
    if not text:
        return False
    if looks_like_uuid(text):
        return False
    path = Path(text)
    if path.exists() or (Path.cwd() / text).exists():
        return True
    suffix = path.suffix.lower()
    if suffix in {".json", ".yaml", ".yml"}:
        return True
    if "/" in text or "\\" in text:
        return True
    return False


def _candidate_app_files_in_dir(directory: Path) -> list[Path]:
    candidates: list[Path] = []
    if (directory / WORKSPACE_FILE).is_file() or (directory / LEGACY_PROJECT_FILE).is_file():
        candidates.append(app_manifest_path(directory))
    for name in APP_FILE_NAMES:
        candidates.append(directory / name)
        candidates.append(directory / "src" / "app" / name)
    return candidates


def resolve_app_file_path(path: str | Path) -> Path:
    """Resolve a local app file, accepting an app directory or direct file path."""
    raw = Path(path).expanduser()
    resolved = raw.resolve() if raw.exists() else raw

    if resolved.is_file():
        return resolved.resolve()

    if resolved.is_dir() or not resolved.suffix:
        directory = resolved if resolved.is_dir() else raw
        # Prefer resolving relative to cwd when the directory does not exist yet.
        search_root = directory if directory.is_dir() else Path.cwd() / directory
        if search_root.is_dir():
            for candidate in _candidate_app_files_in_dir(search_root.resolve()):
                if candidate.is_file():
                    return candidate.resolve()
        raise FileNotFoundError(
            f"No app.caraer.yaml found under app directory: {search_root}"
        )

    if not resolved.exists():
        raise FileNotFoundError(f"Local app file not found: {resolved}")
    raise ValueError(f"Local app path is not a file: {resolved}")


def load_local_app(path: str | Path) -> dict[str, Any]:
    payload = load_structured_file(str(resolve_app_file_path(path)))
    if not isinstance(payload, dict):
        raise ValueError("Local app file must contain a YAML/JSON object.")
    return payload


def local_app_summary(path: Path, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = payload if payload is not None else load_local_app(path)
    return {
        "source": "local",
        "path": str(path),
        "name": data.get("name"),
        "label": data.get("label"),
        "uuid": data.get("uuid"),
        "privateApp": data.get("privateApp"),
    }


def discover_local_app_files(start: Path | None = None) -> list[Path]:
    """Find candidate local app definition files near the current directory."""
    root = (start or Path.cwd()).resolve()
    found: list[Path] = []
    seen: set[Path] = set()

    def _add(path: Path) -> None:
        if not path.is_file():
            return
        # Ignore function manifests.
        if path.name == "function.caraer.json":
            return
        resolved = path.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        found.append(resolved)

    for name in APP_FILE_NAMES:
        _add(root / name)

    for name in APP_FILE_NAMES:
        _add(root / "src" / "app" / name)

    # Child app folders: <dir>/caraer.json → src/app/app.caraer.yaml
    for marker in (WORKSPACE_FILE, LEGACY_PROJECT_FILE):
        for workspace in sorted(root.glob(f"*/{marker}")):
            _add(app_manifest_path(workspace.parent))

    # Also allow immediate child app manifests.
    for name in APP_FILE_NAMES:
        for path in sorted(root.glob(f"*/{name}")):
            _add(path)
        for path in sorted(root.glob(f"*/src/app/{name}")):
            _add(path)

    return found
