"""Discover / write modular settingsSections files under src/app/settings-sections/."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from caraer_cli.project.paths import settings_sections_dir, settings_yaml_path
from caraer_cli.project.schema import ProjectConfig

LOCAL_SECTION_KEYS = (
    "title",
    "subtitle",
    "settings",
)


def _slug(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "section"


def settings_section_filename(item: dict[str, Any], index: int | None = None) -> str:
    title = str(item.get("title") or "section")
    slug = _slug(title)
    if index is None:
        return f"{slug}.json"
    return f"{index:02d}-{slug}.json"


def settings_section_identity(item: dict[str, Any]) -> str:
    return _slug(str(item.get("title") or ""))


def sanitize_settings_section(item: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in LOCAL_SECTION_KEYS:
        if key in item and item[key] is not None:
            payload[key] = item[key]
    return payload


def discover_local_settings_sections(
    root: Path, config: ProjectConfig
) -> list[tuple[Path, dict[str, Any]]]:
    if config.is_layout_v21():
        from caraer_cli.project.settings_sync import _load_settings_yaml

        path = settings_yaml_path(root, config.srcDir)
        data = _load_settings_yaml(root, config)
        items = data.get("settingsSections") or data.get("sections") or []
        found: list[tuple[Path, dict[str, Any]]] = []
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("title") and item.get("settings"):
                    found.append((path, sanitize_settings_section(item)))
        return found
    base = settings_sections_dir(root, config.srcDir)
    if not base.is_dir():
        return []
    found = []
    for path in sorted(base.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("title") and data.get("settings"):
            found.append((path, sanitize_settings_section(data)))
    return found


def write_settings_sections_files(
    root: Path, config: ProjectConfig, items: list[dict[str, Any]]
) -> int:
    if config.is_layout_v21():
        from caraer_cli.project.settings_sync import _load_settings_yaml, write_settings_yaml

        existing = _load_settings_yaml(root, config)
        settings = existing.get("settingsSchema") or existing.get("settings") or []
        sanitized = [
            sanitize_settings_section(item)
            for item in items
            if isinstance(item, dict) and settings_section_identity(sanitize_settings_section(item))
        ]
        write_settings_yaml(root, config, settings if isinstance(settings, list) else [], sanitized)
        return len(sanitized)
    base = settings_sections_dir(root, config.srcDir)
    base.mkdir(parents=True, exist_ok=True)
    for existing in base.glob("*.json"):
        existing.unlink()
    count = 0
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        sanitized = sanitize_settings_section(item)
        if not settings_section_identity(sanitized):
            continue
        path = base / settings_section_filename(sanitized, index)
        path.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
        count += 1
    return count
