"""Discover app bars from function manifests, or from legacy app-bar files."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from caraer_cli.project.paths import app_bars_dir, app_bars_yaml_path
from caraer_cli.project.schema import ProjectConfig

LOCAL_APP_BAR_KEYS = (
    "uuid",
    "name",
    "location",
    "label",
    "tooltipLabel",
    "description",
    "actionLabel",
    "iframeUrl",
    "icon",
    "settingsSchema",
    "webhook",
)

ACTION_BASED_LOCATIONS = frozenset(
    {"RECORD_PREVIEW", "RECORD_OVERVIEW", "RECORD_TRAIT"}
)


def _slug(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "app-bar"


def app_bar_filename(item: dict[str, Any]) -> str:
    location = _slug(str(item.get("location") or "bar"))
    label = _slug(str(item.get("label") or "app-bar"))
    return f"{location}-{label}.json"


def app_bar_identity(item: dict[str, Any]) -> str:
    name = str(item.get("name") or "").strip().lower()
    if name:
        return name
    location = str(item.get("location") or "").strip().upper()
    label = str(item.get("label") or "").strip().lower()
    return f"{location}|{label}"


def _sanitize_webhook(webhook: Any) -> dict[str, Any] | None:
    if not isinstance(webhook, dict):
        return None
    cleaned: dict[str, Any] = {}
    for key in (
        "uuid",
        "topic",
        "deliveryMode",
        "url",
        "description",
        "enabled",
        "webhookFormat",
        "serverlessFunction",
    ):
        if key in webhook and webhook[key] is not None:
            cleaned[key] = webhook[key]
    sf = cleaned.get("serverlessFunction")
    if isinstance(sf, dict):
        sf_out: dict[str, Any] = {}
        if sf.get("uuid"):
            sf_out["uuid"] = sf["uuid"]
        if sf.get("name"):
            sf_out["name"] = sf["name"]
        if sf_out:
            cleaned["serverlessFunction"] = sf_out
        else:
            cleaned.pop("serverlessFunction", None)
    return cleaned or None


def sanitize_app_bar(item: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in LOCAL_APP_BAR_KEYS:
        if key not in item or item[key] is None:
            continue
        if key == "webhook":
            webhook = _sanitize_webhook(item[key])
            if webhook:
                payload["webhook"] = webhook
        else:
            payload[key] = item[key]
    return payload


def _yaml_app_bars(root: Path, config: ProjectConfig) -> list[tuple[Path, dict[str, Any]]]:
    path = app_bars_yaml_path(root, config.srcDir)
    if not path.is_file():
        return []
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = data.get("appBars") if isinstance(data, dict) else data
    found: list[tuple[Path, dict[str, Any]]] = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and item.get("label") and item.get("location"):
                found.append((path, sanitize_app_bar(item)))
    return found


def discover_local_app_bars(
    root: Path, config: ProjectConfig
) -> list[tuple[Path, dict[str, Any]]]:
    if config.is_layout_v21():
        from caraer_cli.project.function_files import (
            app_bar_items_from_files,
            discover_layout_v21_functions,
        )

        found = [
            (path, sanitize_app_bar(item))
            for path, item in app_bar_items_from_files(
                discover_layout_v21_functions(root, config)
            )
        ]
        seen = {app_bar_identity(item) for _path, item in found}
        for path, item in _yaml_app_bars(root, config):
            if app_bar_identity(item) in seen:
                continue
            found.append((path, item))
            seen.add(app_bar_identity(item))
        return found
    base = app_bars_dir(root, config.srcDir)
    if not base.is_dir():
        return []
    found = []
    for path in sorted(base.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("label") and data.get("location"):
            found.append((path, sanitize_app_bar(data)))
    return found


def _author_app_bar(item: dict[str, Any]) -> dict[str, Any]:
    """Fields a developer writes on the function. The function is the handler."""
    payload: dict[str, Any] = {}
    for key in (
        "name",
        "location",
        "label",
        "tooltipLabel",
        "description",
        "actionLabel",
        "iframeUrl",
        "icon",
        "settingsSchema",
    ):
        if key in item and item[key] is not None:
            payload[key] = item[key]
    return payload


def _function_name_for_bar(
    item: dict[str, Any], owners: dict[str, str]
) -> str:
    webhook = item.get("webhook")
    if isinstance(webhook, dict):
        sf = webhook.get("serverlessFunction")
        if isinstance(sf, dict) and sf.get("name"):
            return str(sf["name"])
    identity = app_bar_identity(item)
    if identity in owners:
        return owners[identity]
    name = str(item.get("name") or "app-bar").strip().replace("_", "-")
    return name or "app-bar"


def write_app_bars_to_function_manifests(
    root: Path, config: ProjectConfig, items: list[dict[str, Any]]
) -> int:
    """Store app bars on the function that runs them.

    Remote uuid and ``serverlessFunction`` stay off the source file. A later
    discover call attaches this function as the ``app.bar.triggered`` handler.
    """
    from caraer_cli.project.code_manifest import parse_code_manifest_file, write_code_manifest
    from caraer_cli.project.function_files import (
        discover_layout_v21_functions,
        function_file_by_name,
    )
    from caraer_cli.project.paths import functions_dir
    from caraer_cli.project.sync import _v21_function_source

    owners: dict[str, str] = {}
    for existing in discover_layout_v21_functions(root, config):
        declared: list[Any] = []
        raw_list = existing.manifest.get("appBars")
        if isinstance(raw_list, list):
            declared.extend(raw_list)
        single = existing.manifest.get("appBar")
        if isinstance(single, dict):
            declared.append(single)
        for raw in declared:
            if isinstance(raw, dict):
                owners[app_bar_identity(raw)] = existing.name

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        sanitized = sanitize_app_bar(item)
        if not app_bar_identity(sanitized).strip("|"):
            continue
        grouped.setdefault(_function_name_for_bar(sanitized, owners), []).append(
            _author_app_bar(sanitized)
        )

    for existing in discover_layout_v21_functions(root, config):
        if existing.name in grouped:
            continue
        if "appBars" not in existing.manifest and "appBar" not in existing.manifest:
            continue
        current = parse_code_manifest_file(existing.path)
        current.pop("appBars", None)
        current.pop("appBar", None)
        write_code_manifest(existing.path, current)

    count = 0
    runtime = config.resolved_runtime("nodejs22")
    for name, bars in grouped.items():
        existing = function_file_by_name(root, config, name)
        if existing is not None:
            path = existing.path
            current = parse_code_manifest_file(path)
        else:
            suffix = ".py" if runtime.startswith("python") else ".js"
            path = functions_dir(root, config.srcDir) / f"{name}{suffix}"
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.is_file():
                path.write_text(_v21_function_source(runtime), encoding="utf-8")
            current = parse_code_manifest_file(path) if path.is_file() else {}
        current.pop("appBar", None)
        current["appBars"] = bars
        write_code_manifest(path, current)
        count += len(bars)

    yaml_path = app_bars_yaml_path(root, config.srcDir)
    if yaml_path.is_file():
        yaml_path.unlink()
    return count


def write_app_bars_files(
    root: Path, config: ProjectConfig, items: list[dict[str, Any]]
) -> int:
    if config.is_layout_v21():
        return write_app_bars_to_function_manifests(root, config, items)
    base = app_bars_dir(root, config.srcDir)
    base.mkdir(parents=True, exist_ok=True)
    for existing in base.glob("*.json"):
        existing.unlink()
    count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        sanitized = sanitize_app_bar(item)
        if not app_bar_identity(sanitized).strip("|"):
            continue
        path = base / app_bar_filename(sanitized)
        path.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
        count += 1
    return count


def stamp_app_bar_identities(
    local_bars: list[Any],
    remote_bars: list[Any],
) -> list[dict[str, Any]]:
    """Copy remote bar and webhook UUIDs onto local bars matched by location|label."""
    remote_by_identity: dict[str, dict[str, Any]] = {}
    for item in remote_bars:
        if not isinstance(item, dict):
            continue
        key = app_bar_identity(item)
        if not key.strip("|"):
            continue
        remote_by_identity[key] = item
    stamped: list[dict[str, Any]] = []
    for item in local_bars:
        if not isinstance(item, dict):
            continue
        copied = dict(item)
        remote = remote_by_identity.get(app_bar_identity(copied))
        if remote:
            if remote.get("uuid"):
                copied["uuid"] = remote["uuid"]
            local_webhook = copied.get("webhook")
            remote_webhook = remote.get("webhook")
            if isinstance(local_webhook, dict) and isinstance(remote_webhook, dict):
                if remote_webhook.get("uuid"):
                    webhook = dict(local_webhook)
                    webhook["uuid"] = remote_webhook["uuid"]
                    copied["webhook"] = webhook
        stamped.append(copied)
    return stamped


def persist_app_bar_identities(
    root: Path,
    config: ProjectConfig,
    remote_bars: list[Any],
) -> None:
    """Write remote bar/webhook UUIDs back into legacy ``app-bars/*.json`` files.

    Function manifests and ``app-bars.yaml`` stay as authored. Push stamps
    UUIDs from the live app before update, matched by bar name.
    """
    if not remote_bars:
        return
    for path, item in discover_local_app_bars(root, config):
        if path.suffix != ".json":
            continue
        stamped_items = stamp_app_bar_identities([item], remote_bars)
        if not stamped_items:
            continue
        stamped = stamped_items[0]
        if stamped == item:
            continue
        path.write_text(json.dumps(stamped, indent=2) + "\n", encoding="utf-8")


def resolve_app_bar_functions(
    item: dict[str, Any],
    *,
    fn_by_name: dict[str, str],
    strict: bool = True,
) -> dict[str, Any] | None:
    out = dict(item)
    webhook = out.get("webhook")
    if not isinstance(webhook, dict):
        return out
    webhook = dict(webhook)
    sf = webhook.get("serverlessFunction")
    if isinstance(sf, dict):
        name = sf.get("name")
        uuid = sf.get("uuid")
        if uuid:
            if not name:
                for candidate_name, candidate_uuid in fn_by_name.items():
                    if candidate_uuid == uuid:
                        name = candidate_name
                        break
            ref: dict[str, str] = {"uuid": str(uuid)}
            if name:
                ref["name"] = name
            webhook["serverlessFunction"] = ref
        else:
            if name and name in fn_by_name:
                webhook["serverlessFunction"] = {
                    "uuid": fn_by_name[name],
                    "name": name,
                }
            elif name:
                if strict:
                    raise ValueError(
                        f"App bar references function '{name}' but no UUID is known. "
                        "Push functions first."
                    )
                return None
    out["webhook"] = webhook
    return out
