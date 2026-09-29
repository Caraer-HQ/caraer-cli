"""Sync schedules between src/app/schedules/*.json and the remote API."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from caraer_cli.api import integration_runtime as api
from caraer_cli.api.client import CaraerApiClient
from caraer_cli.project.paths import schedules_dir
from caraer_cli.project.schema import ProjectConfig
from caraer_cli.project.state import load_state, save_state

LOCAL_SCHEDULE_KEYS = (
    "uuid",
    "name",
    "label",
    "schedule",
    "enabled",
    "payloadTemplate",
    "serverlessFunction",
)


def _slug(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "schedule"


def schedule_filename(item: dict[str, Any]) -> str:
    name = str(item.get("name") or "schedule")
    uuid = str(item.get("uuid") or "")[:8]
    parts = [_slug(name)]
    if uuid:
        parts.append(uuid)
    return "-".join(parts) + ".json"


def discover_local_schedules(root: Path, config: ProjectConfig) -> list[tuple[Path, dict[str, Any]]]:
    if config.is_layout_v21():
        from caraer_cli.project.function_files import (
            discover_layout_v21_functions,
            schedule_items_from_files,
        )

        return schedule_items_from_files(discover_layout_v21_functions(root, config))
    base = schedules_dir(root, config.srcDir)
    if not base.is_dir():
        return []
    found: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(base.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            found.append((path, data))
    return found


def _sanitize(item: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in LOCAL_SCHEDULE_KEYS:
        if key in item and item[key] is not None:
            payload[key] = item[key]
    sf = payload.get("serverlessFunction")
    if isinstance(sf, dict):
        cleaned: dict[str, Any] = {}
        if sf.get("name"):
            cleaned["name"] = sf["name"]
        elif sf.get("uuid"):
            cleaned["uuid"] = sf["uuid"]
        if cleaned:
            payload["serverlessFunction"] = cleaned
        else:
            payload.pop("serverlessFunction", None)
    return payload


def _resolve_sf(payload: dict[str, Any], *, fn_by_name: dict[str, str]) -> dict[str, Any]:
    out = dict(payload)
    out.pop("uuid", None)
    sf = out.get("serverlessFunction")
    if not isinstance(sf, dict):
        return out
    if sf.get("uuid"):
        out["serverlessFunction"] = {"uuid": sf["uuid"]}
        return out
    name = sf.get("name")
    if name and name in fn_by_name:
        out["serverlessFunction"] = {"uuid": fn_by_name[name]}
        return out
    if name:
        raise ValueError(
            f"Schedule references function '{name}' but no UUID is known. Push functions first."
        )
    return out


def pull_schedules(client: CaraerApiClient, root: Path, config: ProjectConfig) -> int:
    if not config.appUuid:
        raise ValueError("App is not linked.")
    if config.is_layout_v21():
        return _pull_schedules_v21(client, root, config)
    response = api.list_schedules(client, config.appUuid)
    items = response.get("data") or []
    if not isinstance(items, list):
        items = []
    base = schedules_dir(root, config.srcDir)
    base.mkdir(parents=True, exist_ok=True)
    for existing in base.glob("*.json"):
        existing.unlink()
    state = load_state(root)
    schedules_map: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        sanitized = _sanitize(item)
        path = base / schedule_filename(sanitized)
        path.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
        if sanitized.get("uuid") and sanitized.get("name"):
            schedules_map[str(sanitized["name"])] = str(sanitized["uuid"])
    state["schedules"] = schedules_map
    save_state(root, state)
    return len(schedules_map)


def push_schedules(
    client: CaraerApiClient,
    root: Path,
    config: ProjectConfig,
    *,
    delete_missing: bool = False,
) -> dict[str, Any]:
    if not config.appUuid:
        raise ValueError("App is not linked.")
    state = load_state(root)
    fn_state = state.get("functions") or {}
    fn_by_name = {
        name: str(meta["uuid"])
        for name, meta in fn_state.items()
        if isinstance(meta, dict) and meta.get("uuid")
    }
    remote = api.list_schedules(client, config.appUuid).get("data") or []
    remote_by_uuid = {
        str(i["uuid"]): i for i in remote if isinstance(i, dict) and i.get("uuid")
    }
    remote_by_name = {
        str(i["name"]): i for i in remote if isinstance(i, dict) and i.get("name")
    }
    local = discover_local_schedules(root, config)
    pushed: dict[str, str] = {}
    kept_uuids: set[str] = set()
    for path, raw in local:
        sanitized = _sanitize(raw)
        payload = _resolve_sf(sanitized, fn_by_name=fn_by_name)
        name = str(sanitized.get("name") or "")
        uuid = str(sanitized.get("uuid") or "")
        existing = remote_by_uuid.get(uuid) or remote_by_name.get(name)
        if existing and existing.get("uuid"):
            resp = api.update_schedule(client, config.appUuid, str(existing["uuid"]), payload)
            data = resp.get("data") or existing
        else:
            resp = api.create_schedule(client, config.appUuid, payload)
            data = resp.get("data") or {}
        if isinstance(data, dict) and data.get("uuid"):
            kept_uuids.add(str(data["uuid"]))
            if data.get("name"):
                pushed[str(data["name"])] = str(data["uuid"])
            # write uuid back
            sanitized["uuid"] = data["uuid"]
            if not config.is_layout_v21():
                path.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
    if delete_missing:
        for uuid, item in remote_by_uuid.items():
            if uuid not in kept_uuids:
                api.delete_schedule(client, config.appUuid, uuid)
    state["schedules"] = pushed
    save_state(root, state)
    return {"pushed": len(pushed), "deletedMissing": delete_missing}


def _pull_schedules_v21(client: CaraerApiClient, root: Path, config: ProjectConfig) -> int:
    from caraer_cli.project.code_manifest import parse_code_manifest_file, write_code_manifest
    from caraer_cli.project.function_files import function_file_by_name
    from caraer_cli.project.sync import _v21_function_source

    response = api.list_schedules(client, config.appUuid)
    items = response.get("data") or []
    if not isinstance(items, list):
        items = []
    base = schedules_dir(root, config.srcDir)
    base.mkdir(parents=True, exist_ok=True)
    state = load_state(root)
    schedules_map: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        sanitized = _sanitize(item)
        name = str(sanitized.get("name") or "schedule").replace("_", "-")
        existing = function_file_by_name(root, config, name)
        runtime = config.resolved_runtime("nodejs22")
        suffix = existing.path.suffix if existing else (".py" if runtime.startswith("python") else ".js")
        path = existing.path if existing else base / f"{name}{suffix}"
        if not path.is_file():
            path.write_text(_v21_function_source(runtime), encoding="utf-8")
        current = parse_code_manifest_file(path) if path.is_file() else {}
        current["schedule"] = sanitized.get("schedule")
        current["enabled"] = sanitized.get("enabled", True)
        write_code_manifest(path, current)
        if sanitized.get("uuid"):
            schedules_map[name] = str(sanitized["uuid"])
    state["schedules"] = schedules_map
    save_state(root, state)
    return len(schedules_map)
