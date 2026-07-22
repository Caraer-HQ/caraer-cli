"""Sync external OAuth providers from app.caraer.yaml to the remote API."""

from __future__ import annotations

import os
from typing import Any

from caraer_cli.api import integration_runtime as api
from caraer_cli.api.client import CaraerApiClient
from caraer_cli.local_app import load_local_app
from caraer_cli.project.paths import app_manifest_path
from caraer_cli.project.schema import ProjectConfig
from caraer_cli.project.state import load_state, save_state


def _env_expand(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.startswith("${") and text.endswith("}") and len(text) > 3:
        return os.environ.get(text[2:-1], "")
    return value


def _sanitize_provider(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in (
        "uuid",
        "name",
        "preset",
        "authorizeUrl",
        "tokenUrl",
        "clientId",
        "clientSecret",
        "scopes",
        "pkce",
    ):
        if key in raw and raw[key] is not None:
            out[key] = _env_expand(raw[key])
    if isinstance(out.get("scopes"), list):
        out["scopes"] = [_env_expand(s) for s in out["scopes"]]
    return out


def discover_local_providers(root, config: ProjectConfig) -> list[dict[str, Any]]:
    manifest = load_local_app(app_manifest_path(root, config.srcDir))
    providers = manifest.get("externalOAuthProviders") or []
    if not isinstance(providers, list):
        return []
    return [_sanitize_provider(p) for p in providers if isinstance(p, dict) and p.get("name")]


def push_external_oauth_providers(
    client: CaraerApiClient,
    root,
    config: ProjectConfig,
    *,
    delete_missing: bool = False,
) -> dict[str, Any]:
    if not config.appUuid:
        raise ValueError("App is not linked.")
    local = discover_local_providers(root, config)
    if not local:
        return {"pushed": 0, "skipped": True}

    remote = api.list_external_oauth_providers(client, config.appUuid).get("data") or []
    remote_by_name = {
        str(i["name"]): i for i in remote if isinstance(i, dict) and i.get("name")
    }
    remote_by_uuid = {
        str(i["uuid"]): i for i in remote if isinstance(i, dict) and i.get("uuid")
    }

    pushed: dict[str, str] = {}
    kept_uuids: set[str] = set()
    for provider in local:
        name = str(provider.get("name") or "")
        client_id = str(provider.get("clientId") or "").strip()
        if not client_id:
            # Placeholder providers are kept locally until Google credentials are set.
            continue
        uuid = str(provider.get("uuid") or "")
        existing = remote_by_uuid.get(uuid) or remote_by_name.get(name)
        payload = {k: v for k, v in provider.items() if k != "uuid"}
        # Don't blank an existing secret when local secret omitted.
        if existing and not payload.get("clientSecret"):
            payload.pop("clientSecret", None)
        if existing and existing.get("uuid"):
            resp = api.update_external_oauth_provider(
                client, config.appUuid, str(existing["uuid"]), payload
            )
            data = resp.get("data") or existing
        else:
            if not payload.get("clientSecret"):
                raise ValueError(
                    f"externalOAuthProviders.{name} requires clientSecret on first push "
                    "(set it in app.caraer.yaml or ${GMAIL_OAUTH_CLIENT_SECRET})."
                )
            resp = api.create_external_oauth_provider(client, config.appUuid, payload)
            data = resp.get("data") or {}
        if isinstance(data, dict) and data.get("uuid"):
            kept_uuids.add(str(data["uuid"]))
            if data.get("name"):
                pushed[str(data["name"])] = str(data["uuid"])

    if delete_missing:
        for uuid in remote_by_uuid:
            if uuid not in kept_uuids:
                api.delete_external_oauth_provider(client, config.appUuid, uuid)

    state = load_state(root)
    state["externalOAuthProviders"] = pushed
    save_state(root, state)
    return {"pushed": len(pushed), "deletedMissing": delete_missing}
