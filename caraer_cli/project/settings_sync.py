"""Discover / write modular settingsSchema files under src/app/settings/."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from caraer_cli.project.paths import settings_dir
from caraer_cli.project.schema import ProjectConfig

LOCAL_SETTING_KEYS = (
    "name",
    "label",
    "type",
    "required",
    "helpText",
    "options",
    "optionsSource",
    "actionSource",
    "visibleWhen",
    "defaultValue",
    "hidden",
    "advanced",
    "filterTraits",
    "value",
    "hasValue",
    "mappingValue",
    "valueScope",
)


def _slug(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "setting"


def setting_filename(item: dict[str, Any], index: int | None = None) -> str:
    name = str(item.get("name") or "setting")
    slug = _slug(name)
    if index is None:
        return f"{slug}.json"
    return f"{index:02d}-{slug}.json"


def resolve_setting_options_source(
    field: dict[str, Any],
    *,
    fn_by_name: dict[str, str],
    strict: bool = True,
) -> dict[str, Any]:
    """Resolve optionsSource.serverlessFunctionName to serverlessFunctionUuid."""
    return _resolve_setting_function_source(
        field,
        source_key="optionsSource",
        fn_by_name=fn_by_name,
        strict=strict,
    )


def resolve_setting_action_source(
    field: dict[str, Any],
    *,
    fn_by_name: dict[str, str],
    strict: bool = True,
) -> dict[str, Any]:
    """Resolve actionSource.serverlessFunctionName to serverlessFunctionUuid."""
    return _resolve_setting_function_source(
        field,
        source_key="actionSource",
        fn_by_name=fn_by_name,
        strict=strict,
    )


def _resolve_setting_function_source(
    field: dict[str, Any],
    *,
    source_key: str,
    fn_by_name: dict[str, str],
    strict: bool = True,
) -> dict[str, Any]:
    out = dict(field)
    source = out.get(source_key)
    if not isinstance(source, dict):
        return out
    resolved = dict(source)
    uuid = resolved.get("serverlessFunctionUuid")
    name = resolved.get("serverlessFunctionName")
    if uuid and not name:
        for candidate_name, candidate_uuid in fn_by_name.items():
            if candidate_uuid == uuid:
                name = candidate_name
                break
    if uuid:
        resolved["serverlessFunctionUuid"] = str(uuid)
        if name:
            resolved["serverlessFunctionName"] = name
        out[source_key] = resolved
        return out
    if name and name in fn_by_name:
        resolved["serverlessFunctionUuid"] = fn_by_name[name]
        resolved["serverlessFunctionName"] = name
        out[source_key] = resolved
        return out
    if name and strict:
        raise ValueError(
            f"Setting '{out.get('name')}' {source_key} references function "
            f"'{name}' but no UUID is known. Push functions first."
        )
    return out


def sanitize_setting(item: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in LOCAL_SETTING_KEYS:
        if key in item and item[key] is not None:
            payload[key] = item[key]
    return payload


def discover_local_settings(
    root: Path, config: ProjectConfig
) -> list[tuple[Path, dict[str, Any]]]:
    base = settings_dir(root, config.srcDir)
    if not base.is_dir():
        return []
    found: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(base.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("name"):
            found.append((path, sanitize_setting(data)))
    return found


def write_settings_files(
    root: Path, config: ProjectConfig, items: list[dict[str, Any]]
) -> int:
    base = settings_dir(root, config.srcDir)
    base.mkdir(parents=True, exist_ok=True)
    for existing in base.glob("*.json"):
        existing.unlink()
    count = 0
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict) or not item.get("name"):
            continue
        sanitized = sanitize_setting(item)
        path = base / setting_filename(sanitized, index)
        path.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
        count += 1
    return count
