"""Pull a remote public app into a local app folder."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from caraer_cli.api import apps as apps_api
from caraer_cli.api.client import CaraerApiClient
from caraer_cli.local_app import load_local_app, resolve_app_file_path
from caraer_cli.project.app_manifest_template import (
    APP_MANIFEST_JSON,
    APP_MANIFEST_YAML,
    render_app_manifest,
)
from caraer_cli.project.paths import (
    app_manifest_path,
    find_project_root,
    has_workspace_file,
)
from caraer_cli.project.scaffold import scaffold_app_project
from caraer_cli.project.schema import load_workspace

# Fields useful for local editing / push. Drop nested runtime noise.
LOCAL_APP_KEYS = (
    "uuid",
    "label",
    "name",
    "runtime",
    "authMethod",
    "hideApiKeyField",
    "oauthRedirectUris",
    "brandmark",
    "details",
    "requiredScopes",
    "settingsSchema",
    "settingsSections",
    "appBars",
    "webhookRateLimitPerMinute",
    "jobRateLimitPerMinute",
    "installWebhook",
    "uninstallWebhook",
    "rotateWebhook",
    "updateWebhook",
    "externalOAuthProviders",
)


def _normalize_app_name(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized


def sanitize_remote_app_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Reduce a remote app DTO to a local editable app.caraer.yaml payload."""
    payload: dict[str, Any] = {}
    for key in LOCAL_APP_KEYS:
        if key in data and data[key] is not None:
            payload[key] = data[key]
    # Marketplace publish state and privateApp are server-managed; omit from local files.
    return payload


def _payload_uuid(payload: dict[str, Any]) -> str | None:
    value = str(payload.get("uuid") or "").strip()
    return value or None


def _local_uuid_from_app_file(app_file: Path) -> str | None:
    try:
        data = load_local_app(app_file)
    except (FileNotFoundError, ValueError, OSError):
        return None
    value = str(data.get("uuid") or "").strip()
    return value or None


def _local_uuid_from_project_root(root: Path) -> str | None:
    try:
        config = load_workspace(root)
        value = str(config.appUuid or "").strip()
        if value:
            return value
    except (FileNotFoundError, ValueError, OSError):
        pass
    try:
        return _local_uuid_from_app_file(app_manifest_path(root))
    except (FileNotFoundError, ValueError, OSError):
        return None


def _new_project_dir_for_payload(payload: dict[str, Any], *, base: Path) -> Path:
    name = _normalize_app_name(str(payload.get("name") or payload.get("label") or "app")) or "app"
    candidate = (base / name).resolve()
    if not candidate.exists():
        return candidate

    # Avoid clobbering an unrelated existing folder with the same name.
    existing_uuid = _local_uuid_from_project_root(candidate) if has_workspace_file(candidate) else None
    pulled_uuid = _payload_uuid(payload)
    if existing_uuid and pulled_uuid and existing_uuid == pulled_uuid:
        return candidate
    if has_workspace_file(candidate) or (candidate / "src" / "app").exists():
        suffix = (pulled_uuid or "app")[:8]
        return (base / f"{name}_{suffix}").resolve()
    return candidate


def resolve_pull_target_file(
    payload: dict[str, Any],
    *,
    file: str | Path | None = None,
    directory: str | Path | None = None,
    existing_app_file: str | None = None,
) -> Path:
    """Choose where to write the pulled app.caraer.yaml.

    Reuses the selected / current app folder only when it already belongs to the
    same remote app. Pulling a different app always scaffolds a new folder
    (sibling of the current project when cwd is inside one).
    """
    if file:
        return Path(file).expanduser().resolve()

    pulled_uuid = _payload_uuid(payload)

    if directory:
        root = Path(directory).expanduser().resolve()
        if has_workspace_file(root) or (root / "src" / "app").exists():
            return app_manifest_path(root).resolve()
        return (root / "src" / "app" / APP_MANIFEST_YAML).resolve()

    if existing_app_file:
        try:
            existing = resolve_app_file_path(existing_app_file)
            existing_uuid = _local_uuid_from_app_file(existing)
            if pulled_uuid and existing_uuid and existing_uuid == pulled_uuid:
                return existing
        except (FileNotFoundError, ValueError):
            pass

    base = Path.cwd().resolve()
    try:
        current_root = find_project_root(Path.cwd())
        current_uuid = _local_uuid_from_project_root(current_root)
        if pulled_uuid and current_uuid and pulled_uuid == current_uuid:
            return app_manifest_path(current_root).resolve()
        # Different (or unknown) app: create a sibling folder, not nest/overwrite.
        base = current_root.parent
    except FileNotFoundError:
        pass

    root = _new_project_dir_for_payload(payload, base=base)
    if has_workspace_file(root) or (root / "src" / "app").exists():
        return app_manifest_path(root).resolve()
    return (root / "src" / "app" / APP_MANIFEST_YAML).resolve()


def write_pulled_app(
    payload: dict[str, Any],
    target: Path,
    *,
    force: bool = True,
    platform_version: str | None = None,
    runtime: str | None = None,
) -> Path:
    """Write payload to target, scaffolding an app folder around it when needed."""
    from caraer_cli.project.schema import PLATFORM_VERSION, PLATFORM_VERSION_V1

    target = target.expanduser().resolve()
    resolved_platform = platform_version or PLATFORM_VERSION
    if resolved_platform not in {PLATFORM_VERSION, PLATFORM_VERSION_V1}:
        resolved_platform = PLATFORM_VERSION
    resolved_runtime = (runtime or payload.get("runtime") or "nodejs22")
    if isinstance(resolved_runtime, str):
        resolved_runtime = resolved_runtime.strip().lower() or "nodejs22"
    else:
        resolved_runtime = "nodejs22"

    # If writing into .../src/app/app.caraer.* without a workspace, scaffold.
    if target.parent.name == "app" and target.name in {APP_MANIFEST_YAML, APP_MANIFEST_JSON}:
        project_root = target.parents[2] if len(target.parents) >= 3 else target.parent
        if not has_workspace_file(project_root):
            scaffold_app_project(
                project_root,
                app_payload=payload,
                project_name=str(payload.get("name") or project_root.name),
                app_uuid=str(payload["uuid"]) if payload.get("uuid") else None,
                sample_function=None,
                runtime=resolved_runtime,
                platform_version=resolved_platform,
                force=force,
            )
            return app_manifest_path(project_root).resolve()

    # Prefer YAML on write; migrate away from legacy JSON targets.
    if target.name == APP_MANIFEST_JSON:
        target = target.with_name(APP_MANIFEST_YAML)

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not force:
        raise FileExistsError(f"{target} already exists. Use --force to overwrite.")
    # Pulled remote data is authoritative; skip scaffold example comments.
    include_examples = not any(
        isinstance(payload.get(key), list) and payload.get(key)
        for key in ("appBars", "settingsSchema", "requiredScopes")
    )
    target.write_text(
        render_app_manifest(payload, include_examples=include_examples),
        encoding="utf-8",
    )
    return target


def pull_remote_app(
    client: CaraerApiClient,
    app_uuid: str,
    *,
    file: str | Path | None = None,
    directory: str | Path | None = None,
    existing_app_file: str | None = None,
    force: bool = True,
) -> tuple[dict[str, Any], Path]:
    """Fetch a remote public app and write it to a local app.caraer.yaml."""
    from caraer_cli.project.schema import PLATFORM_VERSION, PLATFORM_VERSION_V1

    response = apps_api.get_public_app(client, app_uuid)
    data = response.get("data")
    if not isinstance(data, dict):
        raise ValueError("Remote app payload was not an object.")
    payload = sanitize_remote_app_payload(data)
    if not payload.get("uuid"):
        payload["uuid"] = app_uuid

    remote_platform = data.get("platformVersion")
    if remote_platform == 2 or remote_platform == "2":
        platform_version = PLATFORM_VERSION
    elif remote_platform == 1 or remote_platform == "1":
        platform_version = PLATFORM_VERSION_V1
    else:
        platform_version = PLATFORM_VERSION
    runtime = data.get("runtime") or payload.get("runtime") or "nodejs22"

    target = resolve_pull_target_file(
        payload,
        file=file,
        directory=directory,
        existing_app_file=existing_app_file,
    )
    # Prefer modular files on disk; keep empty arrays in YAML.
    from caraer_cli.project.marketplace_assemble import split_marketplace_to_disk
    from caraer_cli.project.schema import load_workspace

    project_root = (
        target.parents[2]
        if target.parent.name == "app" and len(target.parents) >= 3
        else target.parent
    )
    try:
        config = load_workspace(project_root)
        payload = split_marketplace_to_disk(project_root, config, payload)
    except (FileNotFoundError, ValueError, OSError):
        pass

    written = write_pulled_app(
        payload,
        target,
        force=force,
        platform_version=platform_version,
        runtime=str(runtime) if runtime else None,
    )
    return payload, written
