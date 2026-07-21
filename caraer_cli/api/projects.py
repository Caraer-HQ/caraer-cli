from __future__ import annotations

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


def pack_project_archive(root: Path, config: ProjectConfig) -> Path:
    src = root / config.srcDir
    out = root / ".caraer" / "upload.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
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


def deploy_build(
    client: CaraerApiClient,
    project_uuid: str,
    build_uuid: str,
    *,
    target: str = "production",
) -> dict[str, Any]:
    return client.request(
        "POST",
        f"/api/v2/developer-projects/{project_uuid}/builds/{build_uuid}/deploy",
        json_body={"target": target},
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
