"""Discover / write modular settingsSchema files under src/app/settings/."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from caraer_cli.project.paths import settings_dir, settings_yaml_path
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
    "filterPropertyTypes",
    "filterPropertyFormats",
    "allowedPropertyTypes",
    "allowedPropertyFormats",
    "value",
    "hasValue",
    "mappingValue",
    "valueScope",
)

AUTHORING_SECTION_KEY = "section"
AUTHORING_SECTION_SUBTITLE_KEY = "sectionSubtitle"

AUTHORING_SETTING_KEYS = (
    "name",
    "type",
    "label",
    AUTHORING_SECTION_KEY,
    AUTHORING_SECTION_SUBTITLE_KEY,
) + tuple(
    key
    for key in LOCAL_SETTING_KEYS
    if key not in {"name", "type", "label"}
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


def sanitize_authoring_setting(item: dict[str, Any]) -> dict[str, Any]:
    """Keep schema keys plus optional installer-card ``section`` annotations."""
    payload: dict[str, Any] = {}
    for key in AUTHORING_SETTING_KEYS:
        if key in item and item[key] is not None:
            payload[key] = item[key]
    return payload


def _section_names(section: dict[str, Any]) -> list[str]:
    names = section.get("settings")
    if isinstance(names, list):
        out: list[str] = []
        for name in names:
            if isinstance(name, str) and name.strip():
                out.append(name)
            elif isinstance(name, dict) and name.get("name"):
                out.append(str(name["name"]))
        return out
    nested = section.get("fields")
    if isinstance(nested, list):
        return [
            str(field["name"])
            for field in nested
            if isinstance(field, dict) and field.get("name")
        ]
    return []


def _fields_from_yaml_list(items: list[Any]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        nested = item.get("fields")
        if isinstance(nested, list) and item.get("title"):
            title = item["title"]
            subtitle = item.get("subtitle")
            for field in nested:
                if not isinstance(field, dict) or not field.get("name"):
                    continue
                out = sanitize_authoring_setting(field)
                out[AUTHORING_SECTION_KEY] = title
                if subtitle is not None:
                    out[AUTHORING_SECTION_SUBTITLE_KEY] = subtitle
                fields.append(out)
            continue
        if item.get("name"):
            fields.append(sanitize_authoring_setting(item))
    return fields


def parse_settings_yaml(data: Any) -> list[dict[str, Any]]:
    """Normalize any accepted settings.yaml shape to a flat authoring field list.

    Accepts a bare field list, the legacy ``settingsSchema`` /
    ``settingsSections`` object, and a list of ``{title, subtitle, fields}``
    section objects. Never used as a write shape for the last two.
    """
    if data is None:
        return []
    if isinstance(data, list):
        return _fields_from_yaml_list(data)
    if isinstance(data, dict):
        schema = data.get("settingsSchema")
        if schema is None:
            schema = data.get("settings")
        fields = _fields_from_yaml_list(schema) if isinstance(schema, list) else []
        sections = data.get("settingsSections")
        if sections is None:
            sections = data.get("sections")
        if isinstance(sections, list) and sections:
            return join_settings_payload(fields, sections)
        return fields
    return []


def split_settings_payload(
    fields: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split authoring fields into backend ``settingsSchema`` + ``settingsSections``."""
    schema: list[dict[str, Any]] = []
    sections: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in fields:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        schema.append(sanitize_setting(item))
        title = item.get(AUTHORING_SECTION_KEY)
        if not title:
            continue
        title = str(title)
        if title not in sections:
            section: dict[str, Any] = {"title": title, "settings": []}
            subtitle = item.get(AUTHORING_SECTION_SUBTITLE_KEY)
            if subtitle is not None:
                section["subtitle"] = subtitle
            sections[title] = section
            order.append(title)
        sections[title]["settings"].append(str(item["name"]))
    return schema, [sections[title] for title in order]


def join_settings_payload(
    settings: list[dict[str, Any]],
    sections: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Attach ``section`` / ``sectionSubtitle`` onto fields from section name lists."""
    by_name: dict[str, dict[str, Any]] = {}
    if sections:
        for section in sections:
            if not isinstance(section, dict):
                continue
            title = section.get("title")
            if not title:
                continue
            info: dict[str, Any] = {AUTHORING_SECTION_KEY: title}
            if section.get("subtitle") is not None:
                info[AUTHORING_SECTION_SUBTITLE_KEY] = section["subtitle"]
            for name in _section_names(section):
                if name not in by_name:
                    by_name[name] = info
    out: list[dict[str, Any]] = []
    for item in settings:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        field = sanitize_authoring_setting(item)
        annotation = by_name.get(str(field.get("name") or ""))
        if annotation:
            field = dict(field)
            field.update(annotation)
        elif sections is not None:
            field.pop(AUTHORING_SECTION_KEY, None)
            field.pop(AUTHORING_SECTION_SUBTITLE_KEY, None)
        out.append(field)
    return out


def _preserve_section_annotations(
    fields: list[dict[str, Any]],
    existing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not existing:
        return fields
    existing_by_name = {
        str(item.get("name")): item
        for item in existing
        if isinstance(item, dict) and item.get("name")
    }
    merged: list[dict[str, Any]] = []
    for field in fields:
        if field.get(AUTHORING_SECTION_KEY):
            merged.append(field)
            continue
        prev = existing_by_name.get(str(field.get("name") or ""))
        if prev and prev.get(AUTHORING_SECTION_KEY):
            field = dict(field)
            field[AUTHORING_SECTION_KEY] = prev[AUTHORING_SECTION_KEY]
            if prev.get(AUTHORING_SECTION_SUBTITLE_KEY) is not None:
                field[AUTHORING_SECTION_SUBTITLE_KEY] = prev[
                    AUTHORING_SECTION_SUBTITLE_KEY
                ]
        merged.append(field)
    return merged


def _load_settings_yaml(root: Path, config: ProjectConfig) -> list[dict[str, Any]]:
    """Load settings.yaml as a flat authoring field list."""
    path = settings_yaml_path(root, config.srcDir)
    if not path.is_file():
        return []
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return parse_settings_yaml(data)


def discover_local_settings(
    root: Path, config: ProjectConfig
) -> list[tuple[Path, dict[str, Any]]]:
    if config.is_layout_v21():
        path = settings_yaml_path(root, config.srcDir)
        found: list[tuple[Path, dict[str, Any]]] = []
        for item in _load_settings_yaml(root, config):
            if isinstance(item, dict) and item.get("name"):
                found.append((path, sanitize_setting(item)))
        return found
    base = settings_dir(root, config.srcDir)
    if not base.is_dir():
        return []
    found = []
    for path in sorted(base.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("name"):
            found.append((path, sanitize_setting(data)))
    return found


def write_settings_yaml(
    root: Path,
    config: ProjectConfig,
    settings: list[dict[str, Any]],
    sections: list[dict[str, Any]] | None = None,
) -> Path:
    import yaml

    path = settings_yaml_path(root, config.srcDir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        sanitize_authoring_setting(item)
        for item in settings
        if isinstance(item, dict) and item.get("name")
    ]
    if sections is not None:
        fields = join_settings_payload(fields, sections)
    else:
        fields = _preserve_section_annotations(fields, _load_settings_yaml(root, config))
    path.write_text(
        yaml.safe_dump(
            fields,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    return path


def append_settings_yaml_field(
    root: Path,
    config: ProjectConfig,
    field: dict[str, Any],
    *,
    force: bool = False,
) -> Path:
    """Append (or replace) one authoring field in ``settings.yaml``."""
    item = sanitize_authoring_setting(field)
    name = str(item.get("name") or "").strip().lower()
    if not name:
        raise ValueError("Cannot determine identity for setting field.")
    existing = _load_settings_yaml(root, config)
    existing_idx = None
    for idx, current in enumerate(existing):
        if str(current.get("name") or "").strip().lower() == name:
            existing_idx = idx
            break
    if existing_idx is not None and not force:
        raise FileExistsError(
            f"settings.yaml already has an item matching '{name}'. Use --force to replace."
        )
    next_fields = list(existing)
    if existing_idx is not None:
        prev = next_fields[existing_idx]
        if not item.get(AUTHORING_SECTION_KEY) and prev.get(AUTHORING_SECTION_KEY):
            item = dict(item)
            item[AUTHORING_SECTION_KEY] = prev[AUTHORING_SECTION_KEY]
            if prev.get(AUTHORING_SECTION_SUBTITLE_KEY) is not None:
                item[AUTHORING_SECTION_SUBTITLE_KEY] = prev[
                    AUTHORING_SECTION_SUBTITLE_KEY
                ]
        next_fields[existing_idx] = item
    else:
        next_fields.append(item)
    return write_settings_yaml(root, config, next_fields)


def write_settings_files(
    root: Path, config: ProjectConfig, items: list[dict[str, Any]]
) -> int:
    if config.is_layout_v21():
        write_settings_yaml(root, config, items)
        return len([item for item in items if isinstance(item, dict) and item.get("name")])
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
