"""Release commands under `caraer apps release`."""

from __future__ import annotations

from typing import Any

import typer

from caraer_cli.commands.deprecation import (
    register_deprecated_group_alias,
    register_deprecated_leaf_alias,
)
from caraer_cli.context import AppContext
from caraer_cli.formatters.output import print_data, print_success

release_app = typer.Typer(help="Build, deploy, and release management.", no_args_is_help=True)
builds_app = typer.Typer(help="Developer-project builds.", no_args_is_help=True)
release_app.add_typer(builds_app, name="builds")

_RELEASE_ALIASES = (
    ("deploy", "deploy"),
    ("rollback", "rollback"),
    ("deploys", "deploys"),
    ("version", "version"),
)


def register_aliases(root: typer.Typer) -> None:
    """Register hidden flat aliases and `apps builds` → `release builds`."""
    for source_name, alias_name in _RELEASE_ALIASES:
        register_deprecated_leaf_alias(
            root,
            release_app,
            source_name=source_name,
            alias_name=alias_name,
            old_path=f"caraer apps {alias_name}",
            new_path=f"caraer apps release {source_name}",
        )
    register_deprecated_group_alias(
        root,
        builds_app,
        alias_name="builds",
        old_path="caraer apps builds",
        new_path="caraer apps release builds",
        help="Developer-project builds (deprecated alias).",
    )


@release_app.command("deploy")
def deploy_app(
    ctx: typer.Context,
    build_uuid: str | None = typer.Argument(None, help="Build UUID (defaults to last build)."),
    target: str = typer.Option("production", "--target", help="production|sandbox"),
    wait: bool = typer.Option(
        True,
        "--wait/--no-wait",
        help="For V2 apps, poll runtimeStatus until READY/FAILED (default: wait).",
    ),
) -> None:
    """Deploy a previously created build for this app."""
    from caraer_cli.api import projects as projects_api
    from caraer_cli.app_sync import (
        _poll_v2_runtime,
        _print_deploy_results,
        _refresh_deploy,
        require_project_uuid,
        resolve_app_root,
    )
    from caraer_cli.formatters.output import print_warning
    from caraer_cli.project.schema import load_workspace
    from caraer_cli.project.state import load_state, save_state

    app_ctx: AppContext = ctx.obj
    root = resolve_app_root(app_file=app_ctx.profile.app_file)
    config = load_workspace(root)
    client = app_ctx.api_client()
    project_uuid = require_project_uuid(client, root, config)
    state = load_state(root)
    resolved = build_uuid or state.get("lastBuildUuid")
    if not resolved:
        raise ValueError("No build UUID provided and no lastBuildUuid in local state.")
    if target == "sandbox":
        print_warning(
            "Sandbox deploys isolate Neo4j data via X-Caraer-Sandbox-Uuid, "
            "but the Cloud Function runtime is shared with production."
        )
    response = projects_api.deploy_build(
        client, project_uuid, str(resolved), target=target, prune=False
    )
    data = response.get("data") or {}
    state["lastDeployUuid"] = data.get("uuid")
    save_state(root, state)
    print_success(f"Deployed build {resolved}")
    if isinstance(data, dict):
        _print_deploy_results(data)
    if config.is_app_platform_v2() and wait:
        runtime = _poll_v2_runtime(client, config, progress=True)
        refreshed = _refresh_deploy(
            client, project_uuid, data.get("uuid") if isinstance(data, dict) else None
        )
        if refreshed:
            data = refreshed
            _print_deploy_results(refreshed)
        if isinstance(data, dict):
            data = {**data, "runtime": runtime}
    elif config.is_app_platform_v2() and not wait:
        print_success(
            "Skipping runtime wait. Check later with 'caraer apps status' "
            "(runtimeStatus) or re-run with --wait."
        )
    print_data(data, app_ctx.output)


@builds_app.command("list")
def list_builds(ctx: typer.Context) -> None:
    """List builds for the selected app's developer project (newest first)."""
    from caraer_cli.api import projects as projects_api
    from caraer_cli.app_sync import require_project_uuid, resolve_app_root
    from caraer_cli.project.schema import load_workspace

    app_ctx: AppContext = ctx.obj
    root = resolve_app_root(app_file=app_ctx.profile.app_file)
    client = app_ctx.api_client()
    project_uuid = require_project_uuid(client, root, load_workspace(root))
    project = projects_api.get_project(client, project_uuid).get("data") or {}
    active_build = str(project.get("activeBuildUuid") or "")
    rows = projects_api.list_builds(client, project_uuid).get("data") or []
    if isinstance(rows, list):
        marked = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            row["live"] = bool(active_build and row.get("uuid") == active_build)
            # Prefer compact table columns over raw archive/manifest blobs.
            row.pop("manifestJson", None)
            row.pop("artifactGcsPath", None)
            marked.append(row)
        rows = marked
    print_data(rows, app_ctx.output)


@builds_app.command("get")
def get_build(
    ctx: typer.Context,
    build_uuid: str = typer.Argument(..., help="Build UUID."),
) -> None:
    """Fetch a single developer-project build by UUID."""
    from caraer_cli.api import projects as projects_api
    from caraer_cli.app_sync import require_project_uuid, resolve_app_root
    from caraer_cli.project.schema import load_workspace

    app_ctx: AppContext = ctx.obj
    root = resolve_app_root(app_file=app_ctx.profile.app_file)
    client = app_ctx.api_client()
    project_uuid = require_project_uuid(client, root, load_workspace(root))
    response = projects_api.get_build(client, project_uuid, build_uuid)
    data = response.get("data") or {}
    if isinstance(data, dict):
        data = dict(data)
        data.pop("manifestJson", None)
        data.pop("artifactGcsPath", None)
    print_data(data, app_ctx.output)


@release_app.command("rollback")
def rollback_app(
    ctx: typer.Context,
    version: str | None = typer.Option(
        None,
        "--version",
        help="Semver of a prior READY build to redeploy.",
    ),
    build: str | None = typer.Option(
        None,
        "--build",
        help="Build UUID to redeploy (overrides --version).",
    ),
    target: str = typer.Option("production", "--target", help="production|sandbox"),
    wait: bool = typer.Option(
        True,
        "--wait/--no-wait",
        help="For V2 apps, poll runtimeStatus until READY/FAILED (default: wait).",
    ),
) -> None:
    """Redeploy a prior READY build (rollback). Defaults to the build before active."""
    from caraer_cli.api import projects as projects_api
    from caraer_cli.app_sync import _poll_v2_runtime, require_project_uuid, resolve_app_root
    from caraer_cli.project.schema import load_workspace
    from caraer_cli.project.state import load_state, save_state

    app_ctx: AppContext = ctx.obj
    root = resolve_app_root(app_file=app_ctx.profile.app_file)
    config = load_workspace(root)
    client = app_ctx.api_client()
    project_uuid = require_project_uuid(client, root, config)
    project = projects_api.get_project(client, project_uuid).get("data") or {}
    active_build = str(project.get("activeBuildUuid") or "")
    builds = projects_api.list_builds(client, project_uuid).get("data") or []
    if not isinstance(builds, list):
        builds = []

    resolved: str | None = build
    if not resolved and version:
        for item in builds:
            if (
                isinstance(item, dict)
                and str(item.get("version") or "") == version
                and str(item.get("status") or "").upper() == "READY"
            ):
                resolved = str(item.get("uuid") or "")
                break
        if not resolved:
            raise ValueError(f"No READY build found with version '{version}'.")
    if not resolved:
        # Default: first READY build that is not the currently active one
        # (builds are newest-first).
        for item in builds:
            if not isinstance(item, dict):
                continue
            uuid = str(item.get("uuid") or "")
            if not uuid or uuid == active_build:
                continue
            if str(item.get("status") or "").upper() != "READY":
                continue
            resolved = uuid
            break
    if not resolved:
        raise ValueError(
            "No prior READY build to roll back to. "
            "Pass --build <uuid> or --version X.Y.Z."
        )

    print_success(f"Rolling back to build {resolved}…")
    response = projects_api.deploy_build(client, project_uuid, resolved, target=target)
    data = response.get("data") or {}
    state = load_state(root)
    state["lastDeployUuid"] = data.get("uuid") if isinstance(data, dict) else None
    state["lastBuildUuid"] = resolved
    save_state(root, state)
    if config.is_app_platform_v2() and wait:
        runtime = _poll_v2_runtime(client, config, progress=True)
        if isinstance(data, dict):
            data = {**data, "runtime": runtime, "rolledBackToBuild": resolved}
    print_success(f"Rollback deploy started for build {resolved}")
    print_data(data, app_ctx.output)


@release_app.command("deploys")
def list_deploys(ctx: typer.Context) -> None:
    """List deploys for the selected app's developer project (newest first)."""
    from caraer_cli.api import projects as projects_api
    from caraer_cli.app_sync import require_project_uuid, resolve_app_root
    from caraer_cli.project.schema import load_workspace

    app_ctx: AppContext = ctx.obj
    root = resolve_app_root(app_file=app_ctx.profile.app_file)
    project_uuid = require_project_uuid(
        app_ctx.api_client(), root, load_workspace(root)
    )
    rows = projects_api.list_deploys(app_ctx.api_client(), project_uuid).get("data") or []
    if isinstance(rows, list):
        cleaned = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            row.pop("resultsJson", None)
            cleaned.append(row)
        rows = cleaned
    print_data(rows, app_ctx.output)


@release_app.command("version")
def app_version(ctx: typer.Context) -> None:
    """Show the live (active) build version and recent releases."""
    from caraer_cli.api import projects as projects_api
    from caraer_cli.app_sync import require_project_uuid, resolve_app_root
    from caraer_cli.project.schema import load_workspace

    app_ctx: AppContext = ctx.obj
    root = resolve_app_root(app_file=app_ctx.profile.app_file)
    client = app_ctx.api_client()
    config = load_workspace(root)
    project_uuid = require_project_uuid(client, root, config)
    project = projects_api.get_project(client, project_uuid).get("data") or {}
    builds = projects_api.list_builds(client, project_uuid).get("data") or []
    active_build_uuid = str(project.get("activeBuildUuid") or "")
    active_version = project.get("activeVersion")
    active_build: dict[str, Any] | None = None
    recent: list[dict[str, Any]] = []
    if isinstance(builds, list):
        for item in builds:
            if not isinstance(item, dict):
                continue
            if active_build_uuid and item.get("uuid") == active_build_uuid:
                active_build = item
                if not active_version:
                    active_version = item.get("version")
            recent.append(
                {
                    "version": item.get("version"),
                    "uuid": item.get("uuid"),
                    "status": item.get("status"),
                    "live": bool(active_build_uuid and item.get("uuid") == active_build_uuid),
                    "releaseNotes": item.get("releaseNotes"),
                    "createdAt": item.get("createdAt"),
                }
            )
        recent = recent[:10]

    payload = {
        "appUuid": config.appUuid,
        "projectUuid": project_uuid,
        "liveVersion": active_version,
        "activeBuildUuid": active_build_uuid or None,
        "activeDeployUuid": project.get("activeDeployUuid"),
        "activeBuild": (
            {
                "uuid": active_build.get("uuid"),
                "version": active_build.get("version"),
                "status": active_build.get("status"),
                "releaseNotes": active_build.get("releaseNotes"),
                "createdAt": active_build.get("createdAt"),
            }
            if active_build
            else None
        ),
        "recentBuilds": recent,
    }
    if active_version:
        print_success(f"Live version: v{active_version}")
    else:
        print_success("No live version yet (deploy a build first).")
    print_data(payload, app_ctx.output)
