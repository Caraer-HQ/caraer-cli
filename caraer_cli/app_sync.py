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
from caraer_cli.project.first_save import defer_unlinked_functions
from caraer_cli.project.paths import (
    app_file_unless_in_workspace,
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
from caraer_cli.project.sync import pull_functions, track_functions, upload_functions
from caraer_cli.project.webhooks_sync import pull_webhooks, push_webhooks
from caraer_cli.project.schedules_sync import pull_schedules, push_schedules
from caraer_cli.project.inbound_sync import pull_inbound, push_inbound
from caraer_cli.project.oauth_providers_sync import (
    pull_external_oauth_providers,
    push_external_oauth_providers,
)
from caraer_cli.project.app_bars_sync import (
    persist_app_bar_identities,
    stamp_app_bar_identities,
)
from caraer_cli.project.marketplace_assemble import (
    assemble_local_manifest,
    split_marketplace_to_disk,
)
from caraer_cli.project.schema import (
    PLATFORM_VERSION,
    PLATFORM_VERSION_V1,
    PLATFORM_VERSION_V2,
)
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


def resolve_local_app_root(
    *,
    app_file: str | Path | None = None,
    profile_app_file: str | Path | None = None,
) -> Path:
    """Resolve the app root for local commands.

    Precedence: an explicit ``--file``, then the workspace containing the
    current directory, then the profile's pinned app. See
    :func:`app_file_unless_in_workspace` for why the directory outranks the pin.
    """
    if app_file:
        return resolve_app_root(app_file=app_file)

    return resolve_app_root(app_file=app_file_unless_in_workspace(profile_app_file))


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
            "Check that you can manage this app as the creator company, then retry."
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
            "Check that you can manage this app as the creator company, then retry."
        )
    return project_uuid


def _persist_visibility(root: Path, config: ProjectConfig, remote: dict[str, Any]) -> ProjectConfig:
    private = apps_api.is_private_remote(remote)
    if config.privateApp == private:
        return config
    config.privateApp = private
    save_project_config(workspace_file(root), config)
    return config


def _remote_app_data(
    client: CaraerApiClient,
    config: ProjectConfig,
    *,
    app_uuid: str | None = None,
) -> dict[str, Any]:
    uuid = (app_uuid or config.appUuid or "").strip()
    if not uuid:
        return {}
    response = apps_api.fetch_app(client, uuid, private=config.privateApp or None)
    data = response.get("data")
    if not isinstance(data, dict):
        return {}
    return data


def _private_create_payload(payload: dict[str, Any]) -> dict[str, Any]:
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    description = payload.get("description")
    if not description and isinstance(details, dict):
        description = details.get("description")
    body: dict[str, Any] = {
        "label": payload.get("label"),
        "description": description,
        "authMethod": payload.get("authMethod"),
        "oauthRedirectUris": payload.get("oauthRedirectUris"),
        "runtime": payload.get("runtime"),
        "platformVersion": payload.get("platformVersion"),
    }
    return {key: value for key, value in body.items() if value is not None}


def push_manifest(
    client: CaraerApiClient,
    root: Path,
    config: ProjectConfig,
    *,
    patch: dict[str, Any] | None = None,
    strict_function_refs: bool = True,
) -> dict[str, Any]:
    if not config.appUuid:
        raise ValueError("App is not linked.")
    manifest_path = app_manifest_path(root, config.srcDir)
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing app manifest: {manifest_path}")
    local = load_local_app(manifest_path)
    local = assemble_local_manifest(
        root,
        config,
        local,
        resolve_functions=True,
        strict_function_refs=strict_function_refs,
    )
    current = _remote_app_data(client, config)
    config = _persist_visibility(root, config, current)
    local_bars = local.get("appBars") if isinstance(local.get("appBars"), list) else []
    current_bars = current.get("appBars") if isinstance(current.get("appBars"), list) else []
    if local_bars:
        local["appBars"] = stamp_app_bar_identities(local_bars, current_bars)
    merged = deep_merge(dict(current), local)
    if patch:
        merged = deep_merge(merged, patch)
    if config.privateApp:
        response = apps_api.update_private_app(client, config.appUuid, merged)
    else:
        response = apps_api.update_public_app(client, config.appUuid, merged)
    data = response.get("data") or {}
    # Keep local app and app-bar UUIDs in sync with the remote nodes.
    remote_bars = data.get("appBars") if isinstance(data.get("appBars"), list) else []
    persist_app_bar_identities(root, config, remote_bars)
    if data.get("uuid") and local.get("uuid") != data.get("uuid"):
        raw = load_local_app(manifest_path)
        raw["uuid"] = data["uuid"]
        write_pulled_app(sanitize_remote_app_payload(raw), manifest_path, force=True)
    return data


def create_app_from_manifest(
    client: CaraerApiClient,
    root: Path,
    config: ProjectConfig,
) -> dict[str, Any]:
    manifest_path = app_manifest_path(root, config.srcDir)
    payload = load_local_app(manifest_path)
    payload = assemble_local_manifest(root, config, payload, resolve_functions=False)
    payload["platformVersion"] = config.api_platform_version()
    if config.is_app_platform_v2():
        runtime = _resolve_app_runtime(root, config)
        payload["runtime"] = runtime
        if config.runtime != runtime:
            config.runtime = runtime
            save_project_config(workspace_file(root), config)
    initial = defer_unlinked_functions(payload)
    if config.privateApp:
        created = apps_api.create_private_app(
            client, _private_create_payload(initial)
        )
        data = created.get("data") or {}
        created_uuid = data.get("uuid")
        if created_uuid:
            config.appUuid = str(created_uuid)
            save_project_config(workspace_file(root), config)
            response = apps_api.update_private_app(client, str(created_uuid), initial)
            data = response.get("data") or data
    else:
        response = apps_api.create_public_app(client, initial)
        data = response.get("data") or {}
    created_uuid = data.get("uuid")
    if created_uuid:
        config.appUuid = str(created_uuid)
        save_project_config(workspace_file(root), config)
        sanitized = sanitize_remote_app_payload(data if isinstance(data, dict) else payload)
        if not sanitized.get("uuid"):
            sanitized["uuid"] = created_uuid
        # Prefer keeping modular disk layout: split remote into files.
        split_payload = split_marketplace_to_disk(root, config, sanitized)
        write_pulled_app(split_payload, manifest_path, force=True)
    return data


def _resolve_app_runtime(root: Path, config: ProjectConfig) -> str:
    if config.runtime:
        return config.runtime
    from caraer_cli.project.sync import discover_local_functions

    local = discover_local_functions(root, config)
    if local:
        return local[0][0].runtime
    return "nodejs22"


def _parse_results_json(raw: Any) -> dict[str, Any]:
    """Parse deploy resultsJson (string or dict) into a dict."""
    import json

    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _print_deploy_results(deploy_data: dict[str, Any]) -> None:
    """Print per-item reconcile results from a deploy response."""
    from caraer_cli.formatters.output import print_error, print_success, print_warning

    status = str(deploy_data.get("status") or "").upper()
    results = _parse_results_json(deploy_data.get("resultsJson"))
    if not results and status not in {"PARTIAL", "FAILED"}:
        return

    if status:
        printer = print_error if status == "FAILED" else (
            print_warning if status == "PARTIAL" else print_success
        )
        printer(f"Deploy status: {status}")

    for section, payload in results.items():
        if section == "runtime":
            continue
        if isinstance(payload, list):
            for item in payload:
                if not isinstance(item, dict):
                    continue
                name = item.get("name") or item.get("uuid") or "?"
                if item.get("success") is True:
                    print_success(f"  {section}/{name}: ok")
                elif item.get("skipped"):
                    print_warning(
                        f"  {section}/{name}: skipped"
                        f" ({item.get('reason') or item.get('error') or 'n/a'})"
                    )
                else:
                    print_error(
                        f"  {section}/{name}: "
                        f"{item.get('error') or 'failed'}"
                    )
        elif isinstance(payload, dict):
            if payload.get("success") is True:
                print_success(f"  {section}: ok")
            elif payload.get("skipped"):
                print_warning(
                    f"  {section}: skipped"
                    f" ({payload.get('reason') or payload.get('error') or 'n/a'})"
                )
            elif payload.get("success") is False or payload.get("error"):
                print_error(f"  {section}: {payload.get('error') or 'failed'}")


def _print_runtime_outcome(runtime: dict[str, Any]) -> None:
    """Print a clear READY-at-URL or FAILED message after wait."""
    from caraer_cli.formatters.output import print_error, print_success, print_warning

    if not runtime:
        return
    status = str(runtime.get("runtimeStatus") or "").upper()
    base_url = runtime.get("runtimeBaseUrl")
    error = runtime.get("runtimeError")
    if status == "READY":
        if base_url:
            print_success(f"runtime READY at {base_url}")
        else:
            print_success("runtime READY")
    elif status == "FAILED":
        print_error(f"runtime FAILED: {error or 'unknown error'}")
    elif status == "TIMEOUT":
        print_warning(f"runtime wait timed out: {error or status}")
    elif status:
        print_warning(f"runtimeStatus={status}")


def _refresh_deploy(
    client: CaraerApiClient,
    project_uuid: str,
    deploy_uuid: str | None,
) -> dict[str, Any]:
    """Re-fetch a deploy by UUID (best-effort) to pick up final resultsJson."""
    if not deploy_uuid:
        return {}
    try:
        rows = projects_api.list_deploys(client, project_uuid).get("data") or []
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(rows, list):
        return {}
    for item in rows:
        if isinstance(item, dict) and str(item.get("uuid") or "") == str(deploy_uuid):
            return item
    return {}


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
            if progress:
                _print_runtime_outcome(last)
            return last
        time.sleep(interval_s)
    last["runtimeStatus"] = last.get("runtimeStatus") or "TIMEOUT"
    last["runtimeError"] = last.get("runtimeError") or "Timed out waiting for runtime READY"
    if progress:
        _print_runtime_outcome(last)
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
    from caraer_cli.formatters.output import print_conflict, print_success
    from caraer_cli.project.release import (
        latest_build_version,
        push_conflict_message,
        resolve_release_for_build,
    )
    from caraer_cli.wizard.prompts import WizardCancelled

    project_uuid = get_cached_project_uuid(root)
    if not legacy and not project_uuid:
        try:
            project_uuid = require_project_uuid(client, root, config)
        except (ApiError, ValueError):
            project_uuid = None
    if legacy or not project_uuid:
        from caraer_cli.formatters.output import print_warning
        from caraer_cli.project.paths import shared_dir

        shared = shared_dir(root, config.srcDir)
        if shared.is_dir() and any(path.is_file() for path in shared.rglob("*")):
            print_warning(
                "src/app/shared/ is only deployed by build pushes (platform "
                "2026.2 developer projects); the legacy function sync skips it."
            )
        print_success("Syncing functions (legacy)…")
        return {
            "mode": "legacy",
            **upload_functions(client, root, config, delete_missing=delete_missing),
        }

    conflict = push_conflict_message(
        str(load_state(root).get("lastBuildVersion") or "") or None,
        latest_build_version(client, project_uuid),
    )
    if conflict:
        print_conflict(conflict)

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
            client, project_uuid, str(build_uuid), target=target, prune=delete_missing
        )
        deploy_data = deploy_response.get("data") or {}
        state["lastDeployUuid"] = deploy_data.get("uuid")
        save_state(root, state)
        result["deploy"] = deploy_data
        print_success(f"Deploy started: {deploy_data.get('uuid') or 'ok'}")
        _print_deploy_results(deploy_data if isinstance(deploy_data, dict) else {})
        if config.is_app_platform_v2() and wait:
            result["runtime"] = _poll_v2_runtime(client, config, progress=True)
            refreshed = _refresh_deploy(
                client, project_uuid, deploy_data.get("uuid") if isinstance(deploy_data, dict) else None
            )
            if refreshed:
                result["deploy"] = refreshed
                _print_deploy_results(refreshed)
        elif config.is_app_platform_v2() and not wait:
            print_success(
                "Skipping runtime wait. Check later with 'caraer apps get' "
                "(runtimeStatus) or re-run with --wait."
            )

    # Refresh local function UUID tracking (read-only): V2 runtimes deploy
    # from the build archive, so no code is re-uploaded here.
    try:
        track_functions(client, root, config)
    except Exception:  # noqa: BLE001
        pass
    return result


def _deploy_has_full_reconcile(functions_result: dict[str, Any]) -> bool:
    """True when the backend deploy results include schedules/inbound/oauth."""
    deploy = functions_result.get("deploy") if isinstance(functions_result, dict) else None
    if not isinstance(deploy, dict):
        return False
    results = _parse_results_json(deploy.get("resultsJson"))
    return any(
        key in results
        for key in ("schedules", "inboundRoutes", "externalOAuthProviders")
    )


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
    from caraer_cli.formatters.output import print_success, print_warning

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
        # Soft resolve: settings always; lifecycle/app-bars wait for function UUIDs.
        manifest_result = push_manifest(
            client, root, config, patch=patch, strict_function_refs=False
        )

    config = ensure_linked(client, root, config)
    if target == "sandbox":
        print_warning(
            "Sandbox deploys isolate Neo4j data via X-Caraer-Sandbox-Uuid, "
            "but the Cloud Function runtime is shared with production."
        )
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
    print_success("Refreshing app manifest (lifecycle / app bars)…")
    try:
        manifest_result = push_manifest(
            client, root, config, patch=patch, strict_function_refs=True
        )
    except ValueError as exc:
        print_success(f"Manifest refresh deferred: {exc}")

    # Prefer server-side reconcile (build/deploy) when the backend reports it.
    # Fall back to per-resource CRUD for older backends or non-deploy pushes.
    server_reconciled = bool(deploy) and _deploy_has_full_reconcile(functions_result)
    if server_reconciled:
        print_success(
            "Server-side deploy reconciled functions/webhooks/schedules/"
            "inbound/OAuth (skipping client CRUD)."
        )
        webhooks_result: dict[str, Any] = {"mode": "server-reconcile"}
        schedules_result: dict[str, Any] = {"mode": "server-reconcile"}
        inbound_result: dict[str, Any] = {"mode": "server-reconcile"}
        oauth_result: dict[str, Any] = {"mode": "server-reconcile"}
    else:
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
        print_success("Syncing external OAuth providers…")
        oauth_result = push_external_oauth_providers(
            client,
            root,
            config,
            delete_missing=delete_missing,
        )

    modules_result = push_cms_modules(
        client,
        root,
        config,
        functions_result=functions_result,
        version=version,
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
        "externalOAuthProviders": oauth_result,
        "cmsModules": modules_result,
        "serverReconcile": server_reconciled,
    }


def push_cms_modules(
    client: CaraerApiClient,
    root: Path,
    config: ProjectConfig,
    *,
    functions_result: dict[str, Any] | None = None,
    version: str | None = None,
) -> dict[str, Any]:
    """Publish CMS modules to the registry and register the catalog.

    Modules travel outside the build archive: the archive feeds the app
    runtime, whereas modules are compiled into each installing company's
    website build, which resolves them with `pnpm install`.
    """
    from caraer_cli.api import modules as modules_api
    from caraer_cli.formatters.output import print_success, print_warning
    from caraer_cli.project.modules_publish import publish_modules
    from caraer_cli.project.modules_sync import discover_local_modules

    modules = [m for m in discover_local_modules(root, config) if m.config and m.entry.is_file()]
    if not modules:
        return {"modules": 0}

    app_name = (config.name or "").strip()
    if not app_name:
        return {"modules": len(modules), "published": False, "reason": "App has no name."}

    # Modules version in lockstep with the app build, so a company that pins an
    # app version gets exactly the modules that shipped with it.
    resolved_version = version or _resolved_build_version(functions_result, root)
    if not resolved_version:
        return {
            "modules": len(modules),
            "published": False,
            "reason": "No build version available to publish modules against.",
        }

    print_success(f"Publishing {len(modules)} CMS module(s) at v{resolved_version}…")
    summary = publish_modules(
        root,
        config,
        app_name=app_name,
        version=resolved_version,
        private=bool(config.privateApp),
        company=_selected_company_subdomain(client),
        client=client,
    )

    if not summary.get("published"):
        print_warning(f"Modules not published: {summary.get('reason') or summary.get('error')}")
        return summary

    if summary.get("via") == "api":
        print_success("Published CMS modules through Caraer.")
        return summary

    if config.appUuid:
        try:
            modules_api.publish_module_catalog(
                client,
                config.appUuid,
                {
                    "package": summary["package"],
                    "version": resolved_version,
                    "modules": summary["modules"],
                },
            )
            print_success("Registered CMS module catalog.")
            summary["catalog"] = True
        except Exception as exc:  # noqa: BLE001
            # A catalog failure must not fail the whole push: the package is
            # already published and re-registering is idempotent.
            print_warning(f"Could not register module catalog: {exc}")
            summary["catalog"] = False

    return summary


def _slug_company_subdomain(name: str | None) -> str | None:
    """Turn a company display name into the subdomain slug used in package names."""
    if not isinstance(name, str) or not name.strip():
        return None
    slug = "".join(
        ch if ch.isalnum() or ch == "-" else ""
        for ch in name.strip().lower().replace(" ", "-")
    )
    return slug or None


def _explicit_company_subdomain(company: dict[str, Any]) -> str | None:
    settings = company.get("websiteSettings")
    settings = settings if isinstance(settings, dict) else {}
    for value in (
        company.get("subdomain"),
        company.get("subdomainName"),
        settings.get("subdomain"),
    ):
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


def _selected_company_subdomain(client) -> str | None:
    """Subdomain of the company selected on the CLI profile, if any.

    ``/auth/companies`` often omits ``websiteSettings``. Fall back to
    ``GET /company`` and finally the company name (``FCG`` → ``fcg``) so
    private module packages still publish as ``@caraer/<subdomain>_<app>``.
    """
    from caraer_cli.api import auth as auth_api

    company_uuid = getattr(getattr(client, "context", None), "company_uuid", None)
    if not company_uuid:
        return None

    company: dict[str, Any] | None = None
    try:
        response = auth_api.companies(client)
    except Exception:  # noqa: BLE001
        response = {}
    companies = response.get("data")
    if isinstance(companies, list):
        for item in companies:
            if isinstance(item, dict) and item.get("uuid") == company_uuid:
                company = item
                break
    found = _explicit_company_subdomain(company) if company else None
    if found:
        return found

    for path in ("/api/v2/company/", f"/api/v2/company/{company_uuid}"):
        try:
            payload = client.request("GET", path).get("data")
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(payload, dict):
            continue
        if company is None:
            company = payload
        found = _explicit_company_subdomain(payload)
        if found:
            return found

    return _slug_company_subdomain(company.get("name") if company else None)


def _resolved_build_version(
    functions_result: dict[str, Any] | None,
    root: Path,
) -> str | None:
    if isinstance(functions_result, dict):
        build = functions_result.get("build")
        if isinstance(build, dict) and build.get("version"):
            return str(build["version"])
    state = load_state(root)
    value = state.get("lastBuildVersion")
    return str(value) if value else None


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
    dirty = False
    if config.appUuid != linked_uuid:
        config.appUuid = linked_uuid
        dirty = True

    # Align local platformVersion / runtime / visibility with the remote AppDTO.
    remote_full = _remote_app_data(client, config, app_uuid=linked_uuid)
    remote_platform = remote_full.get("platformVersion")
    if remote_platform == 2 or remote_platform == "2":
        if not config.is_app_platform_v2():
            config.platformVersion = PLATFORM_VERSION_V2
            dirty = True
    elif remote_platform == 1 or remote_platform == "1":
        if config.platformVersion != PLATFORM_VERSION_V1:
            config.platformVersion = PLATFORM_VERSION_V1
            dirty = True
    remote_runtime = remote_full.get("runtime") or payload.get("runtime")
    if isinstance(remote_runtime, str) and remote_runtime.strip():
        normalized = remote_runtime.strip().lower()
        if normalized in {"nodejs22", "python312"} and config.runtime != normalized:
            config.runtime = normalized
            dirty = True
    remote_private = apps_api.is_private_remote(remote_full)
    if config.privateApp != remote_private:
        config.privateApp = remote_private
        dirty = True
    if dirty:
        save_project_config(workspace_file(root), config)
    ensure_linked(client, root, config, app_uuid=linked_uuid)

    functions_result: dict[str, Any] = {"functions": [], "error": None}
    webhooks_result: dict[str, Any] = {"webhooks": [], "error": None}
    schedules_result: dict[str, Any] = {"schedules": [], "error": None}
    inbound_result: dict[str, Any] = {"inbound": [], "error": None}
    oauth_result: dict[str, Any] = {"providers": [], "error": None}
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
    try:
        oauth_result = {"count": pull_external_oauth_providers(client, root, config)}
    except Exception as exc:  # noqa: BLE001
        oauth_result = {"providers": [], "error": str(exc)}
    source_result = restore_deployed_source(client, root)
    return {
        "appUuid": linked_uuid,
        "app_file": str(app_file),
        "root": str(root),
        "manifest": {
            "uuid": payload.get("uuid"),
            "name": payload.get("name"),
            "label": payload.get("label"),
        },
        "platformVersion": config.platformVersion,
        "runtime": config.runtime,
        "functions": functions_result,
        "webhooks": webhooks_result,
        "schedules": schedules_result,
        "inbound": inbound_result,
        "externalOAuthProviders": oauth_result,
        "source": source_result,
    }


def restore_deployed_source(client: CaraerApiClient, root: Path) -> dict[str, Any]:
    """Replace the pull scaffold with the zip of the currently deployed build."""
    from caraer_cli.formatters.output import print_success, print_warning
    from caraer_cli.project.source_archive import extract_deployed_archive

    project_uuid = get_cached_project_uuid(root)
    if not project_uuid:
        return {"restored": False, "reason": "No developer project."}
    try:
        payload = projects_api.download_deployed_source(client, project_uuid)
    except ApiError as exc:
        if exc.status == 404 and "No deployed source archive" in exc.message:
            print_warning("This app has no deployed source archive yet.")
        else:
            print_warning(f"Could not download the deployed source: {exc.message}")
        return {"restored": False, "reason": exc.message}
    except ValueError as exc:
        print_warning(str(exc))
        return {"restored": False, "reason": str(exc)}
    count = extract_deployed_archive(root, payload)
    version = _remember_deployed_version(client, root, project_uuid)
    label = f" (v{version})" if version else ""
    print_success(f"Restored {count} files from the deployed source{label}.")
    return {"restored": True, "files": count, "version": version}


def _remember_deployed_version(
    client: CaraerApiClient, root: Path, project_uuid: str
) -> str | None:
    """Record the live version so a later push can see if the remote moved ahead."""
    from caraer_cli.project.release import latest_build_version

    version: str | None = None
    build_uuid: str | None = None
    try:
        project = projects_api.get_project(client, project_uuid).get("data") or {}
        if isinstance(project, dict):
            raw = project.get("activeVersion")
            version = str(raw).strip() if raw else None
            raw_build = project.get("activeBuildUuid")
            build_uuid = str(raw_build).strip() if raw_build else None
    except ApiError:
        version = None
    if not version:
        try:
            version = latest_build_version(client, project_uuid)
        except ApiError:
            version = None
    if not version:
        return None
    state = load_state(root)
    state["lastBuildVersion"] = version
    if build_uuid:
        state["lastBuildUuid"] = build_uuid
    save_state(root, state)
    return version
