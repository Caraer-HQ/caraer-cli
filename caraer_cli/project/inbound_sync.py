"""Sync inbound routes between src/app/inbound/*.json and the remote API."""

from __future__ import annotations

import json
import re
import secrets
from pathlib import Path
from typing import Any

from caraer_cli.api import integration_runtime as api
from caraer_cli.api.client import CaraerApiClient
from caraer_cli.project.paths import inbound_dir
from caraer_cli.project.schema import ProjectConfig
from caraer_cli.project.state import load_state, save_state

LOCAL_INBOUND_KEYS = (
    "uuid",
    "name",
    "label",
    "authMode",
    "enqueue",
    "sharedSecret",
    "serverlessFunction",
)


def _slug(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "inbound"


def inbound_filename(item: dict[str, Any]) -> str:
    name = str(item.get("name") or "inbound")
    uuid = str(item.get("uuid") or "")[:8]
    parts = [_slug(name)]
    if uuid:
        parts.append(uuid)
    return "-".join(parts) + ".json"


def discover_local_inbound(root: Path, config: ProjectConfig) -> list[tuple[Path, dict[str, Any]]]:
    base = inbound_dir(root, config.srcDir)
    if not base.is_dir():
        return []
    found: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(base.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            found.append((path, data))
    return found


def _sanitize_local(item: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in LOCAL_INBOUND_KEYS:
        if key in item and item[key] is not None:
            payload[key] = item[key]
    # Never persist sharedSecret after push in pulled files — keep local-only until push.
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


def _sanitize_remote(item: dict[str, Any]) -> dict[str, Any]:
    payload = _sanitize_local(item)
    payload.pop("sharedSecret", None)
    if item.get("hasSharedSecret"):
        payload["hasSharedSecret"] = True
    return payload


def _resolve_sf(payload: dict[str, Any], *, fn_by_name: dict[str, str]) -> dict[str, Any]:
    out = dict(payload)
    out.pop("uuid", None)
    out.pop("hasSharedSecret", None)
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
            f"Inbound route references function '{name}' but no UUID is known. Push functions first."
        )
    return out


def pull_inbound(client: CaraerApiClient, root: Path, config: ProjectConfig) -> int:
    if not config.appUuid:
        raise ValueError("App is not linked.")
    response = api.list_inbound_routes(client, config.appUuid)
    items = response.get("data") or []
    if not isinstance(items, list):
        items = []
    base = inbound_dir(root, config.srcDir)
    base.mkdir(parents=True, exist_ok=True)
    for existing in base.glob("*.json"):
        existing.unlink()
    state = load_state(root)
    inbound_map: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        sanitized = _sanitize_remote(item)
        path = base / inbound_filename(sanitized)
        path.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
        if sanitized.get("uuid") and sanitized.get("name"):
            inbound_map[str(sanitized["name"])] = str(sanitized["uuid"])
    state["inbound"] = inbound_map
    save_state(root, state)
    return len(inbound_map)


def push_inbound(
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
    remote = api.list_inbound_routes(client, config.appUuid).get("data") or []
    remote_by_uuid = {
        str(i["uuid"]): i for i in remote if isinstance(i, dict) and i.get("uuid")
    }
    remote_by_name = {
        str(i["name"]): i for i in remote if isinstance(i, dict) and i.get("name")
    }
    local = discover_local_inbound(root, config)
    pushed: dict[str, str] = {}
    kept_uuids: set[str] = set()
    for path, raw in local:
        sanitized = _sanitize_local(raw)
        payload = _resolve_sf(sanitized, fn_by_name=fn_by_name)
        name = str(sanitized.get("name") or "")
        uuid = str(sanitized.get("uuid") or "")
        existing = remote_by_uuid.get(uuid) or remote_by_name.get(name)
        auth_mode = str(payload.get("authMode") or "SHARED_SECRET").upper()
        if (
            not existing
            and auth_mode == "SHARED_SECRET"
            and not str(payload.get("sharedSecret") or "").strip()
        ):
            generated = secrets.token_urlsafe(24)
            payload["sharedSecret"] = generated
            # Keep locally so Pub/Sub can be configured; not written back after create.
            sanitized["sharedSecret"] = generated
            path.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
        if existing and existing.get("uuid"):
            resp = api.update_inbound_route(client, config.appUuid, str(existing["uuid"]), payload)
            data = resp.get("data") or existing
        else:
            resp = api.create_inbound_route(client, config.appUuid, payload)
            data = resp.get("data") or {}
        if isinstance(data, dict) and data.get("uuid"):
            kept_uuids.add(str(data["uuid"]))
            if data.get("name"):
                pushed[str(data["name"])] = str(data["uuid"])
            write_back = _sanitize_remote({**sanitized, **data})
            write_back.pop("sharedSecret", None)
            path.write_text(json.dumps(write_back, indent=2) + "\n", encoding="utf-8")
    if delete_missing:
        for uuid in remote_by_uuid:
            if uuid not in kept_uuids:
                api.delete_inbound_route(client, config.appUuid, uuid)
    state["inbound"] = pushed
    save_state(root, state)
    return {"pushed": len(pushed), "deletedMissing": delete_missing}
