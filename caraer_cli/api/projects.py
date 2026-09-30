from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from caraer_cli.api.client import CaraerApiClient
from caraer_cli.project.schema import ProjectConfig


def create_or_get_project(client: CaraerApiClient, app_uuid: str, name: str) -> dict[str, Any]:
    return client.request(
        "POST",
        "/api/v2/developer-projects",
        json_body={"appUuid": app_uuid, "name": name, "label": name},
    )


def get_project(client: CaraerApiClient, project_uuid: str) -> dict[str, Any]:
    return client.request("GET", f"/api/v2/developer-projects/{project_uuid}")


def _write_layout_v21_sidecar(root: Path, config: ProjectConfig) -> Path | None:
    if not config.is_layout_v21():
        return None
    from caraer_cli.project.function_files import discover_layout_v21_functions
    from caraer_cli.project.inbound_sync import discover_local_inbound
    from caraer_cli.project.lifecycle_sync import discover_local_lifecycle
    from caraer_cli.project.marketplace_assemble import assemble_local_manifest
    from caraer_cli.project.paths import app_manifest_path, build_manifest_path
    from caraer_cli.project.schedules_sync import discover_local_schedules
    from caraer_cli.project.webhooks_sync import discover_local_webhooks
    from caraer_cli.apps_local import load_local_app

    try:
        local = load_local_app(app_manifest_path(root, config.srcDir))
    except Exception:
        local = {}
    assembled = assemble_local_manifest(
        root, config, local, resolve_functions=False, strict_function_refs=False
    )
    functions = []
    for item in discover_layout_v21_functions(root, config):
        functions.append(
            {
                "name": item.name,
                "runtime": item.runtime,
                "entry": item.path.name,
                "folder": item.role,
                "path": str(item.path.relative_to(root)),
                "manifest": item.manifest,
            }
        )
    sidecar = {
        "platformVersion": config.platformVersion,
        "functions": functions,
        "webhooks": [item for _path, item in discover_local_webhooks(root, config)],
        "schedules": [item for _path, item in discover_local_schedules(root, config)],
        "inbound": [item for _path, item in discover_local_inbound(root, config)],
        "lifecycle": discover_local_lifecycle(root, config),
        "settingsSchema": assembled.get("settingsSchema") or [],
        "settingsSections": assembled.get("settingsSections") or [],
        "appBars": assembled.get("appBars") or [],
    }
    path = build_manifest_path(root, config.srcDir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    return path


def pack_project_archive(root: Path, config: ProjectConfig) -> Path:
    src = root / config.srcDir
    out = root / ".caraer" / "upload.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    _write_layout_v21_sidecar(root, config)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        workspace_json = root / "caraer.json"
        if workspace_json.is_file():
            zf.write(workspace_json, arcname="caraer.json")
        legacy = root / "caraer.project.json"
        if legacy.is_file() and not workspace_json.is_file():
            zf.write(legacy, arcname="caraer.json")
        if src.is_dir():
            for path in src.rglob("*"):
                if path.is_file():
                    zf.write(path, arcname=str(path.relative_to(root)))
        env_file = root / ".env"
        if env_file.is_file():
            zf.write(env_file, arcname=".env")
    return out


def create_build(
    client: CaraerApiClient,
    project_uuid: str,
    archive_path: Path,
    *,
    target: str = "production",
    version: str | None = None,
    release_notes: str | None = None,
) -> dict[str, Any]:
    # Prefer multipart when available; fall back to base64 JSON for simpler clients.
    import base64

    encoded = base64.b64encode(archive_path.read_bytes()).decode("ascii")
    body: dict[str, Any] = {
        "target": target,
        "archiveBase64": encoded,
        "filename": archive_path.name,
    }
    if version:
        body["version"] = version
    if release_notes is not None:
        body["releaseNotes"] = release_notes
    return client.request(
        "POST",
        f"/api/v2/developer-projects/{project_uuid}/builds",
        json_body=body,
        timeout_seconds=max(client.context.timeout_seconds, 300.0),
    )


def list_builds(client: CaraerApiClient, project_uuid: str) -> dict[str, Any]:
    return client.request("GET", f"/api/v2/developer-projects/{project_uuid}/builds")


def get_build(client: CaraerApiClient, project_uuid: str, build_uuid: str) -> dict[str, Any]:
    return client.request(
        "GET", f"/api/v2/developer-projects/{project_uuid}/builds/{build_uuid}"
    )


def download_deployed_source(client: CaraerApiClient, project_uuid: str) -> bytes:
    """Zip of the build currently deployed for this project."""
    payload = client.request(
        "GET",
        f"/api/v2/developer-projects/{project_uuid}/source",
        raw=True,
        timeout_seconds=max(client.context.timeout_seconds, 120.0),
    )
    if not isinstance(payload, (bytes, bytearray)) or not bytes(payload).startswith(b"PK"):
        raise ValueError("Deployed source was not a zip archive.")
    return bytes(payload)


def deploy_build(
    client: CaraerApiClient,
    project_uuid: str,
    build_uuid: str,
    *,
    target: str = "production",
    prune: bool = False,
) -> dict[str, Any]:
    body: dict[str, Any] = {"target": target}
    if prune:
        body["prune"] = True
    return client.request(
        "POST",
        f"/api/v2/developer-projects/{project_uuid}/builds/{build_uuid}/deploy",
        json_body=body,
    )


def list_deploys(client: CaraerApiClient, project_uuid: str) -> dict[str, Any]:
    return client.request("GET", f"/api/v2/developer-projects/{project_uuid}/deploys")


def get_function_logs(
    client: CaraerApiClient,
    app_uuid: str,
    function_uuid: str,
    *,
    since: str = "1h",
    limit: int = 100,
) -> dict[str, Any]:
    return client.request(
        "GET",
        f"/api/v2/apps/{app_uuid}/serverless-functions/{function_uuid}/logs",
        params={"since": since, "limit": limit},
    )


def get_runtime_logs(
    client: CaraerApiClient,
    app_uuid: str,
    *,
    since: str = "1h",
    limit: int = 100,
) -> dict[str, Any]:
    """Fetch app-level V2 container logs (no function UUID required)."""
    return client.request(
        "GET",
        f"/api/v2/apps/{app_uuid}/runtime/logs",
        params={"since": since, "limit": limit},
    )


def stream_runtime_logs(
    client: CaraerApiClient,
    app_uuid: str,
    *,
    since: str = "1h",
):
    """Yield SSE JSON payloads from the runtime log stream endpoint.

    Falls back by raising ApiError (caller should poll) when unavailable.
    """
    import json

    import httpx

    headers: dict[str, str] = {"Accept": "text/event-stream"}
    if client.context.token:
        headers["Authorization"] = f"Bearer {client.context.token}"
    if client.context.company_uuid:
        headers["X-Caraer-Company-Uuid"] = client.context.company_uuid
    if client.context.sandbox_uuid:
        headers["X-Caraer-Sandbox-Uuid"] = client.context.sandbox_uuid

    url = (
        client.context.base_url.rstrip("/")
        + f"/api/v2/apps/{app_uuid}/runtime/logs/stream"
    )
    params = {"since": since}
    with httpx.Client(
        timeout=httpx.Timeout(None, connect=30.0),
        verify=client.context.verify_ssl,
    ) as http:
        with http.stream("GET", url, headers=headers, params=params) as response:
            if response.status_code >= 400:
                from caraer_cli.errors import parse_api_error

                payload = None
                try:
                    payload = response.json()
                except Exception:  # noqa: BLE001
                    payload = None
                raise parse_api_error(response.status_code, payload)
            event_name = "message"
            data_lines: list[str] = []
            for line in response.iter_lines():
                if line is None:
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    event_name = line[len("event:") :].strip() or "message"
                    continue
                if line.startswith("data:"):
                    data_lines.append(line[len("data:") :].lstrip())
                    continue
                if line == "" and data_lines:
                    raw = "\n".join(data_lines)
                    data_lines = []
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        payload = {"message": raw, "event": event_name}
                    if isinstance(payload, dict):
                        payload.setdefault("event", event_name)
                    yield payload
                    event_name = "message"
                    if isinstance(payload, dict) and payload.get("event") == "done":
                        return


def sample_payload(
    client: CaraerApiClient,
    app_uuid: str,
    *,
    record_uuid: str,
    event_type: str,
) -> dict[str, Any]:
    return client.request(
        "POST",
        f"/api/v2/apps/{app_uuid}/serverless-functions/sample-payload",
        json_body={"recordUuid": record_uuid, "eventType": event_type},
    )
