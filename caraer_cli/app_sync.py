"""Unified apps push / pull: manifest + functions + webhooks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from caraer_cli.api import apps as apps_api
from caraer_cli.api import projects as projects_api
from caraer_cli.api.client import CaraerApiClient
from caraer_cli.apps_local import (
    pull_remote_app,
    sanitize_remote_app_payload,
    write_pulled_app,
)
from caraer_cli.errors import ApiError
from caraer_cli.local_app import load_local_app, resolve_app_file_path
from caraer_cli.project.paths import (
    app_manifest_path,
    find_project_root,
    workspace_file,
)
from caraer_cli.project.schema import (
    ProjectConfig,
    cache_project_uuid,
    get_cached_project_uuid,
    load_workspace,
    save_project_config,
)
from caraer_cli.project.state import load_state, save_state
from caraer_cli.project.sync import pull_functions, upload_functions
from caraer_cli.project.webhooks_sync import pull_webhooks, push_webhooks
from caraer_cli.project.schedules_sync import pull_schedules, push_schedules
from caraer_cli.project.inbound_sync import pull_inbound, push_inbound
from caraer_cli.utils import deep_merge


def resolve_app_root(
    *,
    start: Path | None = None,
    app_file: str | Path | None = None,
) -> Path:
    if app_file:
        path = resolve_app_file_path(app_file)
        # .../src/app/app.caraer.yaml|json → workspace root is parents[2]
        if path.parent.name == "app" and path.name.startswith("app.caraer."):
            return path.parents[2]
        try:
            return find_project_root(path.parent)
        except FileNotFoundError:
            return path.parent
    return find_project_root(start)


def _canonicalize_app_uuid(client: CaraerApiClient, app_ref: str) -> str:
    """Resolve an app name/slug/uuid to the canonical remote UUID."""
    ref = app_ref.strip()
    if not ref:
        return ref
    for fetcher in (apps_api.get_app, apps_api.get_public_app):
        try:
            data = fetcher(client, ref).get("data") or {}
        except ApiError:
            continue
        if isinstance(data, dict) and data.get("uuid"):
            return str(data["uuid"])
    return ref


def ensure_linked(
    client: CaraerApiClient,
    root: Path,
    config: ProjectConfig,
    *,
    app_uuid: str | None = None,
    require_project: bool = False,
) -> ProjectConfig:
    """Ensure appUuid is set and cache developer-project uuid in state."""
    resolved = (app_uuid or config.appUuid or "").strip() or None
    if not resolved:
        raise ValueError("App has no remote UUID. Run 'caraer apps select' or 'caraer apps push'.")
    resolved = _canonicalize_app_uuid(client, resolved)
    if config.appUuid != resolved:
        config.appUuid = resolved
        save_project_config(workspace_file(root), config)

    project_uuid = get_cached_project_uuid(root)
    try:
        response = projects_api.create_or_get_project(client, resolved, config.name)
        data = response.get("data") or {}
        project_uuid = data.get("uuid") or project_uuid
        if data.get("appUuid"):
            config.appUuid = str(data["appUuid"])
            save_project_config(workspace_file(root), config)
    except ApiError:
        if require_project and not project_uuid:
            raise
    if project_uuid:
        cache_project_uuid(root, str(project_uuid))
    elif require_project:
        raise ValueError(
            "Could not create or load a developer project for this app. "
            "Check that the app has marketplace details, then retry."
        )
    return config


def require_project_uuid(
    client: CaraerApiClient,
    root: Path,
    config: ProjectConfig,
    *,
    app_uuid: str | None = None,
) -> str:
    """Ensure a developer-project uuid is cached; create/fetch remotely if needed."""
    ensure_linked(client, root, config, app_uuid=app_uuid, require_project=True)
    project_uuid = get_cached_project_uuid(root)
    if not project_uuid:
        raise ValueError(
            "Could not create or load a developer project for this app. "
            "Check that the app has marketplace details, then retry."
        )
    return project_uuid


def push_manifest(
    client: CaraerApiClient,
    root: Path,
    config: ProjectConfig,
    *,
    patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not config.appUuid:
        raise ValueError("App is not linked.")
    manifest_path = app_manifest_path(root, config.srcDir)
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing app manifest: {manifest_path}")
    local = load_local_app(manifest_path)
    current = apps_api.get_public_app(client, config.appUuid).get("data", {})
    if not isinstance(current, dict):
        current = {}
    merged = deep_merge(dict(current), local)
    if patch:
        merged = deep_merge(merged, patch)
    response = apps_api.update_public_app(client, config.appUuid, merged)
    data = response.get("data") or {}
    # Keep local uuid in sync.
    if data.get("uuid") and local.get("uuid") != data.get("uuid"):
        local["uuid"] = data["uuid"]
        write_pulled_app(sanitize_remote_app_payload(local), manifest_path, force=True)
    return data


def create_app_from_manifest(
    client: CaraerApiClient,
    root: Path,
    config: ProjectConfig,
) -> dict[str, Any]:
    manifest_path = app_manifest_path(root, config.srcDir)
    payload = load_local_app(manifest_path)
    payload["platformVersion"] = config.api_platform_version()
    if config.is_app_platform_v2():
        runtime = _resolve_app_runtime(root, config)
        payload["runtime"] = runtime
        if config.runtime != runtime:
            config.runtime = runtime
            save_project_config(workspace_file(root), config)
    response = apps_api.create_public_app(client, payload)
    data = response.get("data") or {}
    created_uuid = data.get("uuid")
    if created_uuid:
        config.appUuid = str(created_uuid)
        save_project_config(workspace_file(root), config)
        sanitized = sanitize_remote_app_payload(data if isinstance(data, dict) else payload)
        if not sanitized.get("uuid"):
            sanitized["uuid"] = created_uuid
        write_pulled_app(sanitized, manifest_path, force=True)
    return data


def _resolve_app_runtime(root: Path, config: ProjectConfig) -> str:
    if config.runtime:
        return config.runtime
    from caraer_cli.project.sync import discover_local_functions

    local = discover_local_functions(root, config)
    if local:
        return local[0][0].runtime
    return "nodejs22"


def _poll_v2_runtime(
    client: CaraerApiClient,
    config: ProjectConfig,
    *,
    timeout_s: float = 300.0,
    interval_s: float = 3.0,
    progress: bool = False,
) -> dict[str, Any]:
    """Poll App.runtimeStatus until READY/FAILED or timeout."""
    import time

    from caraer_cli.formatters.output import print_success

    if not config.appUuid or not config.is_app_platform_v2():
        return {}
    started = time.monotonic()
    deadline = started + timeout_s
    last: dict[str, Any] = {}
    last_printed: str | None = None
    last_heartbeat = 0.0
    if progress:
        print_success(f"Waiting for runtime READY (timeout {int(timeout_s)}s)…")
    while time.monotonic() < deadline:
        response = apps_api.get_app(client, config.appUuid)
        data = response.get("data") if isinstance(response.get("data"), dict) else {}
        last = {
            "platformVersion": data.get("platformVersion"),
            "runtime": data.get("runtime"),
            "runtimeStatus": data.get("runtimeStatus"),
            "runtimeBaseUrl": data.get("runtimeBaseUrl"),
            "runtimeRevision": data.get("runtimeRevision"),
            "runtimeError": data.get("runtimeError"),
        }
        status = str(data.get("runtimeStatus") or "").upper() or "UNKNOWN"
        elapsed = time.monotonic() - started
        if progress and status != last_printed:
            print_success(f"runtimeStatus={status} ({int(elapsed)}s)")
            last_printed = status
            last_heartbeat = elapsed
        elif progress and elapsed - last_heartbeat >= 15:
            print_success(f"still waiting… runtimeStatus={status} ({int(elapsed)}s)")
            last_heartbeat = elapsed
        if status in {"READY", "FAILED"}:
            if progress and status == "FAILED":
                print_success(f"runtime FAILED: {last.get('runtimeError') or 'unknown error'}")
            return last
        time.sleep(interval_s)
    last["runtimeStatus"] = last.get("runtimeStatus") or "TIMEOUT"
    last["runtimeError"] = last.get("runtimeError") or "Timed out waiting for runtime READY"
    if progress:
        print_success(
            f"Timed out after {int(timeout_s)}s "
            f"(last runtimeStatus={last.get('runtimeStatus')})."
        )
    return last


def push_functions(
    client: CaraerApiClient,
    root: Path,
    config: ProjectConfig,
    *,
    deploy: bool = False,
    delete_missing: bool = False,
    legacy: bool = False,
    target: str = "production",
    wait: bool = True,
    version: str | None = None,
    release_notes: str | None = None,
    interactive: bool = True,
) -> dict[str, Any]:
    from caraer_cli.formatters.output import print_success
    from caraer_cli.project.release import resolve_release_for_build
    from caraer_cli.wizard.prompts import WizardCancelled

    project_uuid = get_cached_project_uuid(root)
    if not legacy and not project_uuid:
        try:
            project_uuid = require_project_uuid(client, root, config)
        except (ApiError, ValueError):
            project_uuid = None
    if legacy or not project_uuid:
        print_success("Syncing functions (legacy)…")
        return {
            "mode": "legacy",
            **upload_functions(client, root, config, delete_missing=delete_missing),
        }

    try:
        version, release_notes = resolve_release_for_build(
            client,
            project_uuid,
            version=version,
            release_notes=release_notes,
            interactive=interactive,
        )
    except WizardCancelled:
        raise
    print_success(f"Release v{version}")

    print_success("Packing project and creating build…")
    archive_path = projects_api.pack_project_archive(root, config)
    try:
        response = projects_api.create_build(
            client,
            project_uuid,
            archive_path,
            target=target,
            version=version,
            release_notes=release_notes,
        )
    finally:
        if archive_path.exists():
            archive_path.unlink(missing_ok=True)

    data = response.get("data") or {}
    build_uuid = data.get("uuid")
    build_version = data.get("version")
    state = load_state(root)
    state["lastBuildUuid"] = build_uuid
    if build_version:
        state["lastBuildVersion"] = build_version
    save_state(root, state)
    result: dict[str, Any] = {"mode": "build", "build": data}
    version_label = f" v{build_version}" if build_version else ""
    print_success(
        f"Build created{version_label}: {build_uuid} "
        f"(status={data.get('status') or 'unknown'})"
    )

    should_deploy = deploy or config.autoDeploy
    if should_deploy:
        print_success(f"Deploying build {build_uuid} to {target}…")
        deploy_response = projects_api.deploy_build(
            client, project_uuid, str(build_uuid), target=target
        )
        deploy_data = deploy_response.get("data") or {}
        state["lastDeployUuid"] = deploy_data.get("uuid")
        save_state(root, state)
        result["deploy"] = deploy_data
        print_success(f"Deploy started: {deploy_data.get('uuid') or 'ok'}")
        if config.is_app_platform_v2() and wait:
            result["runtime"] = _poll_v2_runtime(client, config, progress=True)
        elif config.is_app_platform_v2() and not wait:
            print_success(
                "Skipping runtime wait. Check later with 'caraer apps get' "
                "(runtimeStatus) or re-run with --wait."
            )

    # Also refresh local function UUID tracking via legacy list when possible.
    try:
        upload_functions(client, root, config, delete_missing=False)
    except Exception:  # noqa: BLE001
        pass
    return result


def push_app(
    client: CaraerApiClient,
    root: Path,
    *,
    app_uuid: str | None = None,
    patch: dict[str, Any] | None = None,
    deploy: bool = False,
    delete_missing: bool = False,
    legacy_functions: bool = False,
    target: str = "production",
    wait: bool = True,
    version: str | None = None,
    release_notes: str | None = None,
    interactive: bool = True,
) -> dict[str, Any]:
    from caraer_cli.formatters.output import print_success

    config = load_workspace(root)

    # Create remote app when unlinked but local manifest exists.
    if not (app_uuid or config.appUuid):
        print_success("Creating remote app from local manifest…")
        created = create_app_from_manifest(client, root, config)
        config = load_workspace(root)
        manifest_result = created
    else:
        config = ensure_linked(client, root, config, app_uuid=app_uuid)
        print_success("Pushing app manifest…")
        manifest_result = push_manifest(client, root, config, patch=patch)

    config = ensure_linked(client, root, config)
    functions_result = push_functions(
        client,
        root,
        config,
        deploy=deploy,
        delete_missing=delete_missing,
        legacy=legacy_functions,
        target=target,
        wait=wait,
        version=version,
        release_notes=release_notes,
        interactive=interactive,
    )
    print_success("Syncing webhooks…")
    webhooks_result = push_webhooks(
        client,
        root,
        config,
        delete_missing=delete_missing,
    )
    print_success("Syncing schedules…")
    schedules_result = push_schedules(
        client,
        root,
        config,
        delete_missing=delete_missing,
    )
    print_success("Syncing inbound routes…")
    inbound_result = push_inbound(
        client,
        root,
        config,
        delete_missing=delete_missing,
    )
    return {
        "appUuid": config.appUuid,
        "manifest": {
            "uuid": (manifest_result or {}).get("uuid") if isinstance(manifest_result, dict) else None,
            "name": (manifest_result or {}).get("name") if isinstance(manifest_result, dict) else None,
            "label": (manifest_result or {}).get("label") if isinstance(manifest_result, dict) else None,
        },
        "functions": functions_result,
        "webhooks": webhooks_result,
        "schedules": schedules_result,
        "inbound": inbound_result,
    }


def pull_app_full(
    client: CaraerApiClient,
    *,
    app_uuid: str,
    file: str | Path | None = None,
    directory: str | Path | None = None,
    existing_app_file: str | None = None,
    force: bool = True,
) -> dict[str, Any]:
    payload, app_file = pull_remote_app(
        client,
        app_uuid,
        file=file,
        directory=directory,
        existing_app_file=existing_app_file,
        force=force,
    )
    # Prefer the canonical UUID from the remote payload (name/slug args may resolve).
    linked_uuid = str(payload.get("uuid") or app_uuid).strip() or app_uuid
    root = resolve_app_root(app_file=app_file)
    config = load_workspace(root)
    if config.appUuid != linked_uuid:
        config.appUuid = linked_uuid
        save_project_config(workspace_file(root), config)
    ensure_linked(client, root, config, app_uuid=linked_uuid)

    functions_result: dict[str, Any] = {"functions": [], "error": None}
    webhooks_result: dict[str, Any] = {"webhooks": [], "error": None}
    schedules_result: dict[str, Any] = {"schedules": [], "error": None}
    inbound_result: dict[str, Any] = {"inbound": [], "error": None}
    try:
        functions_result = pull_functions(client, root, config)
    except Exception as exc:  # noqa: BLE001
        functions_result = {"functions": [], "error": str(exc)}
    try:
        webhooks_result = pull_webhooks(client, root, config)
    except Exception as exc:  # noqa: BLE001
        webhooks_result = {"webhooks": [], "error": str(exc)}
    try:
        schedules_result = {"count": pull_schedules(client, root, config)}
    except Exception as exc:  # noqa: BLE001
        schedules_result = {"schedules": [], "error": str(exc)}
    try:
        inbound_result = {"count": pull_inbound(client, root, config)}
    except Exception as exc:  # noqa: BLE001
        inbound_result = {"inbound": [], "error": str(exc)}
    return {
        "appUuid": linked_uuid,
        "app_file": str(app_file),
        "root": str(root),
        "manifest": {
            "uuid": payload.get("uuid"),
            "name": payload.get("name"),
            "label": payload.get("label"),
        },
        "functions": functions_result,
        "webhooks": webhooks_result,
        "schedules": schedules_result,
        "inbound": inbound_result,
    }
