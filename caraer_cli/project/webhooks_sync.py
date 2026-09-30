"""Sync webhooks between local files / function manifests and the remote API."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from caraer_cli.api import webhooks as webhook_api
from caraer_cli.api.client import CaraerApiClient
from caraer_cli.project.paths import webhooks_dir
from caraer_cli.project.schema import ProjectConfig
from caraer_cli.project.state import load_state, save_state

LOCAL_WEBHOOK_KEYS = (
    "uuid",
    "topic",
    "label",
    "deliveryMode",
    "webhookFormat",
    "description",
    "url",
    "secret",
    "serverlessFunction",
    "enabled",
    "triggerOffsetSeconds",
    "scheduleDirection",
    "includeRelations",
)

WEBHOOK_FILE_SUFFIXES = {".json", ".yaml", ".yml"}


def _slug(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "webhook"


def webhook_filename(item: dict[str, Any], *, suffix: str = ".json") -> str:
    topic = str(item.get("topic") or "webhook")
    mode = str(item.get("deliveryMode") or "").lower()
    uuid = str(item.get("uuid") or "")[:8]
    parts = [_slug(topic)]
    if mode:
        parts.append(_slug(mode))
    if uuid:
        parts.append(uuid)
    return "-".join(parts) + suffix


def webhook_yaml_filename(item: dict[str, Any] | str) -> str:
    if isinstance(item, str):
        return f"{_slug(item)}.yaml"
    return f"{_slug(str(item.get('topic') or 'webhook'))}.yaml"


def write_webhook_yaml(path: Path, item: dict[str, Any]) -> None:
    import yaml

    from caraer_cli.project.json_schemas import WEBHOOK_SCHEMA_URL

    payload = _sanitize_local_webhook(item)
    payload.pop("uuid", None)
    payload.pop("serverlessFunction", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# yaml-language-server: $schema={WEBHOOK_SCHEMA_URL}\n"
        + yaml.safe_dump(
            payload,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )


def _load_webhook_file(path: Path) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        import yaml

        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    return data if isinstance(data, dict) else None


def discover_webhook_files(
    root: Path, config: ProjectConfig
) -> list[tuple[Path, dict[str, Any]]]:
    base = webhooks_dir(root, config.srcDir)
    if not base.is_dir():
        return []
    found: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(base.iterdir()):
        if not path.is_file() or path.suffix.lower() not in WEBHOOK_FILE_SUFFIXES:
            continue
        data = _load_webhook_file(path)
        if data is not None:
            if not str(data.get("name") or "").strip():
                data = dict(data)
                data["name"] = path.stem
            found.append((path, data))
    return found


def discover_local_webhooks(root: Path, config: ProjectConfig) -> list[tuple[Path, dict[str, Any]]]:
    files = discover_webhook_files(root, config)
    if not config.is_layout_v21():
        return files
    from caraer_cli.project.function_files import (
        discover_layout_v21_functions,
        webhook_items_from_files,
    )

    return webhook_items_from_files(discover_layout_v21_functions(root, config)) + files


def _sanitize_local_webhook(item: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in LOCAL_WEBHOOK_KEYS:
        if key in item and item[key] is not None:
            payload[key] = item[key]
    # Prefer portable function name over uuid in local files.
    sf = payload.get("serverlessFunction")
    if isinstance(sf, dict):
        name = sf.get("name")
        uuid = sf.get("uuid")
        cleaned: dict[str, Any] = {}
        if name:
            cleaned["name"] = name
        elif uuid:
            cleaned["uuid"] = uuid
        if cleaned:
            payload["serverlessFunction"] = cleaned
        else:
            payload.pop("serverlessFunction", None)
    return payload


def _resolve_serverless_for_api(
    payload: dict[str, Any],
    *,
    fn_by_name: dict[str, str],
) -> dict[str, Any]:
    out = dict(payload)
    out.pop("uuid", None)  # never send local uuid as create identity unless updating
    sf = out.get("serverlessFunction")
    if not isinstance(sf, dict):
        return out
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
        out["serverlessFunction"] = ref
        return out
    if name and name in fn_by_name:
        out["serverlessFunction"] = {"uuid": fn_by_name[name], "name": name}
        return out
    if name:
        raise ValueError(
            f"Webhook references function '{name}' but no UUID is known. "
            "Push functions first or set serverlessFunction.uuid."
        )
    return out


def _match_key(item: dict[str, Any]) -> str:
    topic = str(item.get("topic") or "")
    mode = str(item.get("deliveryMode") or "")
    return f"{topic}|{mode}"


def push_webhooks(
    client: CaraerApiClient,
    root: Path,
    config: ProjectConfig,
    *,
    delete_missing: bool = False,
) -> dict[str, Any]:
    if not config.appUuid:
        raise ValueError("App has no remote UUID. Run 'caraer apps select' or 'caraer apps push'.")

    remote = webhook_api.list_webhooks(client, config.appUuid, page=1, limit=200)
    remote_items = [i for i in (remote.get("data") or []) if isinstance(i, dict)]
    by_uuid = {str(i.get("uuid")): i for i in remote_items if i.get("uuid")}
    by_key = {_match_key(i): i for i in remote_items}

    state = load_state(root)
    fn_state = state.get("functions") or {}
    fn_by_name = {
        name: str(meta["uuid"])
        for name, meta in fn_state.items()
        if isinstance(meta, dict) and meta.get("uuid")
    }
    wh_state: dict[str, Any] = state.setdefault("webhooks", {})

    results: list[dict[str, Any]] = []
    local_uuids: set[str] = set()
    local_keys: set[str] = set()

    for path, raw in discover_local_webhooks(root, config):
        local = _sanitize_local_webhook(raw)
        key = _match_key(local)
        local_keys.add(key)
        tracked = wh_state.get(path.stem) or {}
        existing_uuid = str(local.get("uuid") or tracked.get("uuid") or "")
        remote_item = by_uuid.get(existing_uuid) if existing_uuid else by_key.get(key)

        api_payload = _resolve_serverless_for_api(local, fn_by_name=fn_by_name)

        if remote_item and remote_item.get("uuid"):
            uuid = str(remote_item["uuid"])
            local_uuids.add(uuid)
            response = webhook_api.update_webhook(client, config.appUuid, uuid, api_payload)
            data = response.get("data") or {}
            results.append({"file": path.name, "uuid": data.get("uuid", uuid), "action": "updated"})
            wh_state[path.stem] = {"uuid": data.get("uuid", uuid), "topic": local.get("topic")}
        else:
            create_payload = {k: v for k, v in api_payload.items() if k != "uuid"}
            response = webhook_api.create_webhook(client, config.appUuid, create_payload)
            data = response.get("data") or {}
            uuid = data.get("uuid")
            if uuid:
                local_uuids.add(str(uuid))
            results.append({"file": path.name, "uuid": uuid, "action": "created"})
            if uuid:
                wh_state[path.stem] = {"uuid": uuid, "topic": local.get("topic")}
            # Legacy webhook JSON files keep the remote uuid for the next push.
            # Function manifests declare the topic only; do not rewrite them as JSON.
            if uuid and not raw.get("uuid") and path.suffix == ".json":
                raw["uuid"] = uuid
                path.write_text(json.dumps(_sanitize_local_webhook(raw), indent=2) + "\n", encoding="utf-8")

    deleted: list[dict[str, Any]] = []
    if delete_missing:
        for item in remote_items:
            uuid = str(item.get("uuid") or "")
            if not uuid or uuid in local_uuids:
                continue
            if _match_key(item) in local_keys:
                continue
            webhook_api.delete_webhook(client, config.appUuid, uuid)
            deleted.append({"uuid": uuid, "topic": item.get("topic"), "action": "deleted"})
            for stem, meta in list(wh_state.items()):
                if isinstance(meta, dict) and meta.get("uuid") == uuid:
                    wh_state.pop(stem, None)

    save_state(root, state)
    return {"webhooks": results, "deleted": deleted}


def pull_webhooks(
    client: CaraerApiClient,
    root: Path,
    config: ProjectConfig,
) -> dict[str, Any]:
    if not config.appUuid:
        raise ValueError("App has no remote UUID. Run 'caraer apps select' or 'caraer apps push'.")

    remote = webhook_api.list_webhooks(client, config.appUuid, page=1, limit=200)
    remote_items = [i for i in (remote.get("data") or []) if isinstance(i, dict)]
    if config.is_layout_v21():
        return _pull_webhooks_v21(root, config, remote_items)
    base = webhooks_dir(root, config.srcDir)
    base.mkdir(parents=True, exist_ok=True)

    # Clear previous webhook files for a clean export.
    for existing in base.glob("*.json"):
        existing.unlink()

    state = load_state(root)
    fn_state = state.get("functions") or {}
    uuid_to_name = {
        str(meta["uuid"]): name
        for name, meta in fn_state.items()
        if isinstance(meta, dict) and meta.get("uuid")
    }
    wh_state: dict[str, Any] = {}
    pulled: list[dict[str, Any]] = []

    for item in remote_items:
        local = _sanitize_local_webhook(item)
        sf = local.get("serverlessFunction")
        if isinstance(sf, dict) and sf.get("uuid"):
            name = uuid_to_name.get(str(sf["uuid"]))
            if name:
                local["serverlessFunction"] = {"name": name}
        filename = webhook_filename(item)
        path = base / filename
        path.write_text(json.dumps(local, indent=2) + "\n", encoding="utf-8")
        stem = path.stem
        if item.get("uuid"):
            wh_state[stem] = {"uuid": item["uuid"], "topic": item.get("topic")}
        pulled.append({"file": filename, "uuid": item.get("uuid"), "topic": item.get("topic")})

    state["webhooks"] = wh_state
    save_state(root, state)
    return {"webhooks": pulled}


def _pull_webhooks_v21(
    root: Path, config: ProjectConfig, remote_items: list[dict[str, Any]]
) -> dict[str, Any]:
    from caraer_cli.project.code_manifest import parse_code_manifest_file, write_code_manifest
    from caraer_cli.project.function_files import discover_layout_v21_functions
    from caraer_cli.project.lifecycle_sync import LIFECYCLE_HOOKS

    lifecycle_topics = {topic for _key, topic in LIFECYCLE_HOOKS.values()}
    files = {item.name: item for item in discover_layout_v21_functions(root, config)}
    state = load_state(root)
    fn_state = state.get("functions") or {}
    uuid_to_name = {
        str(meta["uuid"]): name
        for name, meta in fn_state.items()
        if isinstance(meta, dict) and meta.get("uuid")
    }
    by_function: dict[str, list[dict[str, Any]]] = {}
    pulled: list[dict[str, Any]] = []
    http_items: list[dict[str, Any]] = []
    wh_state: dict[str, Any] = dict(state.get("webhooks") or {})
    for item in remote_items:
        local = _sanitize_local_webhook(item)
        topic = str(local.get("topic") or "")
        if topic in lifecycle_topics:
            continue
        if str(local.get("deliveryMode") or "").strip().upper() == "HTTP":
            http_items.append(local)
            pulled.append({"file": webhook_yaml_filename(local), "uuid": item.get("uuid"), "topic": topic})
            if item.get("uuid"):
                wh_state[Path(webhook_yaml_filename(local)).stem] = {
                    "uuid": item["uuid"],
                    "topic": topic,
                }
            continue
        sf = local.get("serverlessFunction")
        name = None
        if isinstance(sf, dict):
            name = sf.get("name") or uuid_to_name.get(str(sf.get("uuid") or ""))
        if not name or name not in files:
            continue
        hook: dict[str, Any] = {
            "topic": topic,
            "deliveryMode": local.get("deliveryMode") or "SERVERLESS",
            "enabled": local.get("enabled", True),
            "webhookFormat": local.get("webhookFormat") or "USER_FRIENDLY",
        }
        if local.get("label"):
            hook["label"] = local["label"]
        by_function.setdefault(str(name), []).append(hook)
        pulled.append({"function": name, "uuid": item.get("uuid"), "topic": topic})
    for name, webhooks in by_function.items():
        item = files[name]
        current = parse_code_manifest_file(item.path)
        current["webhooks"] = webhooks
        write_code_manifest(item.path, current)
    base = webhooks_dir(root, config.srcDir)
    if http_items:
        base.mkdir(parents=True, exist_ok=True)
        for existing in (*base.glob("*.yaml"), *base.glob("*.yml")):
            existing.unlink()
        for local in http_items:
            write_webhook_yaml(base / webhook_yaml_filename(local), local)
    elif base.is_dir():
        for existing in (*base.glob("*.yaml"), *base.glob("*.yml")):
            existing.unlink()
        leftover = [path for path in base.iterdir() if path.name != ".gitkeep"]
        if not leftover:
            for keep in base.glob(".gitkeep"):
                keep.unlink()
            if not any(base.iterdir()):
                base.rmdir()
    state["webhooks"] = wh_state
    save_state(root, state)
    return {"webhooks": pulled}
