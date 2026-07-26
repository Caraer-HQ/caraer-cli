"""Compute a dry-run / confirmation plan for ``caraer apps push``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.table import Table

from caraer_cli.api import apps as apps_api
from caraer_cli.api import functions as functions_api
from caraer_cli.api import integration_runtime as runtime_api
from caraer_cli.api import webhooks as webhook_api
from caraer_cli.api.client import CaraerApiClient
from caraer_cli.formatters.output import console, print_success, print_warning
from caraer_cli.local_app import load_local_app
from caraer_cli.project.inbound_sync import discover_local_inbound
from caraer_cli.project.oauth_providers_sync import discover_local_providers
from caraer_cli.project.paths import app_manifest_path
from caraer_cli.project.schedules_sync import discover_local_schedules
from caraer_cli.project.schema import ProjectConfig
from caraer_cli.project.state import load_state
from caraer_cli.project.sync import discover_local_functions
from caraer_cli.project.webhooks_sync import discover_local_webhooks

ACTIONS = ("create", "update", "delete", "unchanged")


def build_push_plan(
    client: CaraerApiClient,
    root: Path,
    config: ProjectConfig,
    *,
    delete_missing: bool = False,
) -> dict[str, Any]:
    """Compare local app resources to remote and return a push plan.

    Each resource entry has an ``action`` of create / update / delete / unchanged.
    Deletes only appear when ``delete_missing`` is True.
    """
    remote_app = _fetch_remote_app(client, config.appUuid)
    linked = bool(config.appUuid and remote_app)

    plan: dict[str, Any] = {
        "appUuid": config.appUuid,
        "linked": linked,
        "deleteMissing": delete_missing,
        "manifest": _plan_manifest(root, config, remote_app),
        "functions": _plan_functions(client, root, config, delete_missing=delete_missing),
        "webhooks": _plan_webhooks(client, root, config, delete_missing=delete_missing),
        "schedules": _plan_schedules(client, root, config, delete_missing=delete_missing),
        "inbound": _plan_inbound(client, root, config, delete_missing=delete_missing),
        "externalOAuthProviders": _plan_oauth(
            client, root, config, delete_missing=delete_missing
        ),
    }
    plan["counts"] = _count_actions(plan)
    return plan


def print_push_plan(plan: dict[str, Any]) -> None:
    """Render a push plan with Rich tables and a short summary."""
    counts = plan.get("counts") or {}
    app_uuid = plan.get("appUuid") or "(unlinked — will create)"
    print_success(f"Push plan for app {app_uuid}")

    manifest = plan.get("manifest") or {}
    action = str(manifest.get("action") or "unchanged")
    label = manifest.get("label") or ""
    print_success(f"  Manifest: {action}" + (f" ({label})" if label else ""))
    for field, change in (manifest.get("changes") or {}).items():
        print_warning(f"    {field}: {change.get('remote')!r} → {change.get('local')!r}")

    for kind, title in (
        ("functions", "Functions"),
        ("webhooks", "Webhooks"),
        ("schedules", "Schedules"),
        ("inbound", "Inbound routes"),
        ("externalOAuthProviders", "External OAuth providers"),
    ):
        rows = plan.get(kind) or []
        if not rows:
            print_success(f"  {title}: (none)")
            continue
        table = Table(title=title, show_header=True, header_style="bold")
        table.add_column("Name")
        table.add_column("Action")
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or row.get("topic") or "?")
            act = str(row.get("action") or "")
            style = {
                "create": "green",
                "update": "yellow",
                "delete": "red",
                "unchanged": "dim",
            }.get(act)
            table.add_row(name, act, style=style)
        console.print(table)

    print_success(
        "Summary: "
        f"{counts.get('create', 0)} create, "
        f"{counts.get('update', 0)} update, "
        f"{counts.get('delete', 0)} delete, "
        f"{counts.get('unchanged', 0)} unchanged"
    )
    if plan.get("deleteMissing") is False and any(
        isinstance(r, dict) and r.get("action") == "remote-only"
        for kind in ("functions", "webhooks", "schedules", "inbound", "externalOAuthProviders")
        for r in (plan.get(kind) or [])
    ):
        print_warning(
            "Remote-only resources are listed but will not be deleted "
            "(pass --delete-missing to remove them)."
        )


def _fetch_remote_app(client: CaraerApiClient, app_uuid: str | None) -> dict[str, Any]:
    if not app_uuid:
        return {}
    try:
        response = apps_api.get_public_app(client, app_uuid)
        data = response.get("data")
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _manifest_description(payload: dict[str, Any]) -> str:
    details = payload.get("details")
    if isinstance(details, dict) and details.get("description") is not None:
        return str(details.get("description") or "")
    return str(payload.get("description") or "")


def _plan_manifest(
    root: Path,
    config: ProjectConfig,
    remote_app: dict[str, Any],
) -> dict[str, Any]:
    manifest_path = app_manifest_path(root, config.srcDir)
    local: dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            local = load_local_app(manifest_path)
        except Exception:  # noqa: BLE001
            local = {}
    local_label = str(local.get("label") or "")
    local_desc = _manifest_description(local)
    entry: dict[str, Any] = {
        "name": str(local.get("name") or config.name or ""),
        "label": local_label,
        "description": local_desc,
        "changes": {},
    }
    if not config.appUuid or not remote_app:
        entry["action"] = "create"
        return entry

    remote_label = str(remote_app.get("label") or "")
    remote_desc = _manifest_description(remote_app)
    changes: dict[str, Any] = {}
    if local_label != remote_label:
        changes["label"] = {"local": local_label, "remote": remote_label}
    if local_desc != remote_desc:
        changes["description"] = {"local": local_desc, "remote": remote_desc}
    entry["changes"] = changes
    entry["action"] = "update" if changes else "unchanged"
    return entry


def _hash_function(
    runtime: str,
    description: str,
    code: str,
    source_files: dict[str, str],
) -> str:
    import hashlib

    extras = json.dumps(source_files, sort_keys=True) if source_files else ""
    return hashlib.sha256(
        f"{runtime}\n{description}\n{code}\n{extras}".encode("utf-8")
    ).hexdigest()


def _plan_functions(
    client: CaraerApiClient,
    root: Path,
    config: ProjectConfig,
    *,
    delete_missing: bool,
) -> list[dict[str, Any]]:
    local = discover_local_functions(root, config)
    remote_items = _list_remote(
        lambda: functions_api.list_functions(client, config.appUuid, page=1, limit=200)
        if config.appUuid
        else {"data": []}
    )
    by_name = {
        str(item.get("name") or ""): item
        for item in remote_items
        if isinstance(item, dict) and item.get("name")
    }
    by_uuid = {
        str(item.get("uuid") or ""): item
        for item in remote_items
        if isinstance(item, dict) and item.get("uuid")
    }
    state = load_state(root)
    fn_state = state.get("functions") or {}
    rows: list[dict[str, Any]] = []
    local_names: set[str] = set()

    for manifest, _entry, code, source_files in local:
        local_names.add(manifest.name)
        existing_state = fn_state.get(manifest.name) or {}
        existing_uuid = existing_state.get("uuid") if isinstance(existing_state, dict) else None
        remote_item = (
            by_uuid.get(str(existing_uuid)) if existing_uuid else by_name.get(manifest.name)
        )
        content_hash = _hash_function(
            manifest.runtime, manifest.description or "", code, source_files
        )
        if not remote_item:
            rows.append({"name": manifest.name, "action": "create"})
            continue
        remote_code = remote_item.get("code")
        remote_files = remote_item.get("sourceFiles") or {}
        if not isinstance(remote_files, dict):
            remote_files = {}
        if (
            isinstance(existing_state, dict)
            and existing_state.get("hash") == content_hash
            and remote_code == code
            and remote_files == source_files
        ):
            rows.append({"name": manifest.name, "action": "unchanged"})
        elif (
            remote_code == code
            and remote_files == source_files
            and str(remote_item.get("runtime") or "") == manifest.runtime
            and str(remote_item.get("description") or "") == (manifest.description or "")
        ):
            rows.append({"name": manifest.name, "action": "unchanged"})
        else:
            rows.append({"name": manifest.name, "action": "update"})

    for name, item in by_name.items():
        if name in local_names:
            continue
        action = "delete" if delete_missing else "remote-only"
        rows.append(
            {
                "name": name,
                "action": action,
                "uuid": item.get("uuid"),
            }
        )
    return rows


def _webhook_match_key(item: dict[str, Any]) -> str:
    return f"{item.get('topic') or ''}|{item.get('deliveryMode') or ''}"


def _webhook_compare_payload(item: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in (
        "topic",
        "deliveryMode",
        "webhookFormat",
        "description",
        "url",
        "enabled",
    ):
        if key in item and item[key] is not None:
            payload[key] = item[key]
    sf = item.get("serverlessFunction")
    if isinstance(sf, dict):
        if sf.get("name"):
            payload["serverlessFunction"] = {"name": sf["name"]}
        elif sf.get("uuid"):
            payload["serverlessFunction"] = {"uuid": sf["uuid"]}
    return payload


def _plan_webhooks(
    client: CaraerApiClient,
    root: Path,
    config: ProjectConfig,
    *,
    delete_missing: bool,
) -> list[dict[str, Any]]:
    local = discover_local_webhooks(root, config)
    remote_items = _list_remote(
        lambda: webhook_api.list_webhooks(client, config.appUuid, page=1, limit=200)
        if config.appUuid
        else {"data": []}
    )
    by_uuid = {
        str(i.get("uuid")): i for i in remote_items if isinstance(i, dict) and i.get("uuid")
    }
    by_key = {
        _webhook_match_key(i): i for i in remote_items if isinstance(i, dict)
    }
    state = load_state(root)
    wh_state = state.get("webhooks") or {}
    rows: list[dict[str, Any]] = []
    local_uuids: set[str] = set()
    local_keys: set[str] = set()

    for path, raw in local:
        key = _webhook_match_key(raw)
        local_keys.add(key)
        tracked = wh_state.get(path.stem) if isinstance(wh_state, dict) else None
        existing_uuid = str(
            raw.get("uuid")
            or (tracked.get("uuid") if isinstance(tracked, dict) else "")
            or ""
        )
        remote_item = by_uuid.get(existing_uuid) if existing_uuid else by_key.get(key)
        name = str(raw.get("topic") or path.stem)
        if not remote_item:
            rows.append({"name": name, "action": "create", "file": path.name})
            continue
        uuid = str(remote_item.get("uuid") or "")
        if uuid:
            local_uuids.add(uuid)
        if _webhook_compare_payload(raw) == _webhook_compare_payload(remote_item):
            rows.append({"name": name, "action": "unchanged", "file": path.name, "uuid": uuid})
        else:
            rows.append({"name": name, "action": "update", "file": path.name, "uuid": uuid})

    for item in remote_items:
        if not isinstance(item, dict):
            continue
        uuid = str(item.get("uuid") or "")
        if not uuid or uuid in local_uuids:
            continue
        if _webhook_match_key(item) in local_keys:
            continue
        action = "delete" if delete_missing else "remote-only"
        rows.append(
            {
                "name": str(item.get("topic") or uuid),
                "action": action,
                "uuid": uuid,
            }
        )
    return rows


def _sf_name(item: dict[str, Any]) -> str | None:
    sf = item.get("serverlessFunction")
    if isinstance(sf, dict):
        if sf.get("name"):
            return str(sf["name"])
        if sf.get("uuid"):
            return str(sf["uuid"])
    return None


def _schedule_compare(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item.get("name"),
        "label": item.get("label"),
        "schedule": item.get("schedule"),
        "enabled": item.get("enabled"),
        "payloadTemplate": item.get("payloadTemplate"),
        "serverlessFunction": _sf_name(item),
    }


def _plan_schedules(
    client: CaraerApiClient,
    root: Path,
    config: ProjectConfig,
    *,
    delete_missing: bool,
) -> list[dict[str, Any]]:
    local = discover_local_schedules(root, config)
    remote_items = _list_remote(
        lambda: runtime_api.list_schedules(client, config.appUuid)
        if config.appUuid
        else {"data": []}
    )
    by_uuid = {
        str(i["uuid"]): i for i in remote_items if isinstance(i, dict) and i.get("uuid")
    }
    by_name = {
        str(i["name"]): i for i in remote_items if isinstance(i, dict) and i.get("name")
    }
    rows: list[dict[str, Any]] = []
    kept: set[str] = set()

    for path, raw in local:
        name = str(raw.get("name") or path.stem)
        uuid = str(raw.get("uuid") or "")
        existing = by_uuid.get(uuid) or by_name.get(name)
        if not existing:
            rows.append({"name": name, "action": "create", "file": path.name})
            continue
        remote_uuid = str(existing.get("uuid") or "")
        if remote_uuid:
            kept.add(remote_uuid)
        if _schedule_compare(raw) == _schedule_compare(existing):
            rows.append({"name": name, "action": "unchanged", "uuid": remote_uuid})
        else:
            rows.append({"name": name, "action": "update", "uuid": remote_uuid})

    for uuid, item in by_uuid.items():
        if uuid in kept:
            continue
        action = "delete" if delete_missing else "remote-only"
        rows.append(
            {
                "name": str(item.get("name") or uuid),
                "action": action,
                "uuid": uuid,
            }
        )
    return rows


def _inbound_compare(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item.get("name"),
        "label": item.get("label"),
        "authMode": item.get("authMode"),
        "enqueue": item.get("enqueue"),
        "serverlessFunction": _sf_name(item),
    }


def _plan_inbound(
    client: CaraerApiClient,
    root: Path,
    config: ProjectConfig,
    *,
    delete_missing: bool,
) -> list[dict[str, Any]]:
    local = discover_local_inbound(root, config)
    remote_items = _list_remote(
        lambda: runtime_api.list_inbound_routes(client, config.appUuid)
        if config.appUuid
        else {"data": []}
    )
    by_uuid = {
        str(i["uuid"]): i for i in remote_items if isinstance(i, dict) and i.get("uuid")
    }
    by_name = {
        str(i["name"]): i for i in remote_items if isinstance(i, dict) and i.get("name")
    }
    rows: list[dict[str, Any]] = []
    kept: set[str] = set()

    for path, raw in local:
        name = str(raw.get("name") or path.stem)
        uuid = str(raw.get("uuid") or "")
        existing = by_uuid.get(uuid) or by_name.get(name)
        if not existing:
            rows.append({"name": name, "action": "create", "file": path.name})
            continue
        remote_uuid = str(existing.get("uuid") or "")
        if remote_uuid:
            kept.add(remote_uuid)
        if _inbound_compare(raw) == _inbound_compare(existing):
            rows.append({"name": name, "action": "unchanged", "uuid": remote_uuid})
        else:
            rows.append({"name": name, "action": "update", "uuid": remote_uuid})

    for uuid, item in by_uuid.items():
        if uuid in kept:
            continue
        action = "delete" if delete_missing else "remote-only"
        rows.append(
            {
                "name": str(item.get("name") or uuid),
                "action": action,
                "uuid": uuid,
            }
        )
    return rows


def _oauth_compare(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item.get("name"),
        "logo": item.get("logo"),
        "authorizeUrl": item.get("authorizeUrl"),
        "tokenUrl": item.get("tokenUrl"),
        "clientId": item.get("clientId"),
        "scopes": item.get("scopes"),
        "pkce": item.get("pkce"),
    }


def _plan_oauth(
    client: CaraerApiClient,
    root: Path,
    config: ProjectConfig,
    *,
    delete_missing: bool,
) -> list[dict[str, Any]]:
    local = discover_local_providers(root, config)
    remote_items = _list_remote(
        lambda: runtime_api.list_external_oauth_providers(client, config.appUuid)
        if config.appUuid
        else {"data": []}
    )
    by_uuid = {
        str(i["uuid"]): i for i in remote_items if isinstance(i, dict) and i.get("uuid")
    }
    by_name = {
        str(i["name"]): i for i in remote_items if isinstance(i, dict) and i.get("name")
    }
    rows: list[dict[str, Any]] = []
    kept: set[str] = set()

    for provider in local:
        name = str(provider.get("name") or "")
        client_id = str(provider.get("clientId") or "").strip()
        if not client_id:
            # Placeholders are skipped on push.
            rows.append({"name": name or "?", "action": "unchanged", "skipped": True})
            continue
        uuid = str(provider.get("uuid") or "")
        existing = by_uuid.get(uuid) or by_name.get(name)
        if not existing:
            rows.append({"name": name, "action": "create"})
            continue
        remote_uuid = str(existing.get("uuid") or "")
        if remote_uuid:
            kept.add(remote_uuid)
        has_secret = bool(str(provider.get("clientSecret") or "").strip())
        if _oauth_compare(provider) == _oauth_compare(existing) and not has_secret:
            rows.append({"name": name, "action": "unchanged", "uuid": remote_uuid})
        else:
            rows.append({"name": name, "action": "update", "uuid": remote_uuid})

    for uuid, item in by_uuid.items():
        if uuid in kept:
            continue
        action = "delete" if delete_missing else "remote-only"
        rows.append(
            {
                "name": str(item.get("name") or uuid),
                "action": action,
                "uuid": uuid,
            }
        )
    return rows


def _list_remote(fetcher) -> list[dict[str, Any]]:
    try:
        response = fetcher()
    except Exception:  # noqa: BLE001
        return []
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, list):
        return []
    return [i for i in data if isinstance(i, dict)]


def _count_actions(plan: dict[str, Any]) -> dict[str, int]:
    counts = {action: 0 for action in ACTIONS}
    counts["remote-only"] = 0
    manifest = plan.get("manifest")
    if isinstance(manifest, dict):
        action = str(manifest.get("action") or "")
        if action in counts:
            counts[action] += 1
    for kind in (
        "functions",
        "webhooks",
        "schedules",
        "inbound",
        "externalOAuthProviders",
    ):
        for row in plan.get(kind) or []:
            if not isinstance(row, dict):
                continue
            action = str(row.get("action") or "")
            if action in counts:
                counts[action] += 1
    return counts
