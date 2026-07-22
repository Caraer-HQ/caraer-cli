from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from caraer_cli.project.paths import STATE_DIR, state_path


def _default_state() -> dict[str, Any]:
    return {
        "projectUuid": None,
        "functions": {},
        "webhooks": {},
        "schedules": {},
        "inbound": {},
        "lastBuildUuid": None,
        "lastBuildVersion": None,
        "lastDeployUuid": None,
    }


def load_state(root: Path) -> dict[str, Any]:
    path = state_path(root)
    if not path.is_file():
        return _default_state()
    data = json.loads(path.read_text(encoding="utf-8"))
    merged = _default_state()
    merged.update(data)
    return merged


def save_state(root: Path, state: dict[str, Any]) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    gitignore = root / STATE_DIR / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n", encoding="utf-8")


def get_project_uuid(root: Path) -> str | None:
    value = load_state(root).get("projectUuid")
    return str(value) if value else None


def set_project_uuid(root: Path, project_uuid: str | None) -> None:
    state = load_state(root)
    state["projectUuid"] = project_uuid
    save_state(root, state)
