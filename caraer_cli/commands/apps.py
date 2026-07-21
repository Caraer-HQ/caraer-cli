from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from caraer_cli.api import apps as apps_api
from caraer_cli.completion_callbacks import (
    complete_app_list_type,
    complete_app_ref,
    complete_auth_method,
    complete_local_function,
    complete_runtime,
)
from caraer_cli.context import AppContext
from caraer_cli.formatters.output import print_app_detail, print_data, print_success, project_rows
from caraer_cli.local_app import (
    discover_local_app_files,
    load_local_app,
    local_app_summary,
    looks_like_local_app_ref,
    resolve_app_file_path,
)
from caraer_cli.resolve import resolve_app_file, resolve_app_uuid
from caraer_cli.state.config import save_config
from caraer_cli.utils import parse_patch

app = typer.Typer(help="App lifecycle commands.", no_args_is_help=True)

DEFAULT_BRAND_COLOR = "#E74363"
DEFAULT_TEXT_COLOR = "#FFFFFF"


def normalize_app_name(value: str) -> str:
    import re

    normalized = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized


DEFAULT_OAUTH_CALLBACK = "http://localhost:3000/oauth/callback"
AUTH_METHODS = frozenset({"OAUTH2", "API_KEY"})


def build_public_app_placeholder(
    *,
    label: str,
    name: str | None = None,
    runtime: str = "nodejs22",
    auth_method: str = "OAUTH2",
    oauth_redirect_uris: list[str] | None = None,
) -> dict[str, Any]:
    """Build a placeholder public-app payload for local editing.

    Always includes runtime, authMethod, and oauthRedirectUris.
    """
    resolved_label = label.strip() or "My App"
    resolved_name = normalize_app_name(name or resolved_label) or "my_app"
    method = (auth_method or "OAUTH2").strip().upper()
    if method not in AUTH_METHODS:
        raise ValueError(f"authMethod must be one of: {', '.join(sorted(AUTH_METHODS))}")
    redirects = [
        uri.strip()
        for uri in (oauth_redirect_uris or [DEFAULT_OAUTH_CALLBACK])
        if uri and uri.strip()
    ]
    if method == "OAUTH2" and not redirects:
        raise ValueError("OAUTH2 apps require at least one oauth redirect / callback URL.")
    return {
        "label": resolved_label,
        "name": resolved_name,
        "runtime": runtime,
        "authMethod": method,
        "oauthRedirectUris": redirects,
        "details": {
            "title": resolved_label,
            "description": "TODO: short marketplace description",
            "category": "developer_tools",
            "subcategories": ["apis"],
            "url": "https://example.com",
            "image": "",
            "brandColor": DEFAULT_BRAND_COLOR,
            "textColor": DEFAULT_TEXT_COLOR,
        },
        "requiredScopes": [],
        "settingsSchema": [],
        "pricingPlans": [],
        "appBars": [],
        "webhookRateLimitPerMinute": 100,
        "billFailedWebhookRequests": False,
    }


def _save_selection(
    app_ctx: AppContext,
    *,
    app_uuid: str | None = None,
    app_file: str | None = None,
    clear_uuid: bool = False,
    clear_file: bool = False,
) -> None:
    profile = app_ctx.config.profiles[app_ctx.profile_name]
    if clear_uuid:
        profile.app_uuid = None
    elif app_uuid is not None:
        profile.app_uuid = app_uuid
    if clear_file:
        profile.app_file = None
    elif app_file is not None:
        profile.app_file = app_file
    save_config(app_ctx.config)


def _select_local_file(app_ctx: AppContext, path: str | Path) -> Path:
    from caraer_cli.app_sync import resolve_app_root
    from caraer_cli.project.schema import load_workspace

    resolved = resolve_app_file_path(path)
    payload = load_local_app(resolved)
    embedded_uuid = payload.get("uuid")
    uuid_value = str(embedded_uuid).strip() if embedded_uuid else None
    if not uuid_value:
        try:
            workspace_uuid = load_workspace(resolve_app_root(app_file=resolved)).appUuid
            if workspace_uuid:
                uuid_value = str(workspace_uuid).strip() or None
        except Exception:  # noqa: BLE001
            pass
    _save_selection(
        app_ctx,
        app_file=str(resolved),
        app_uuid=uuid_value,
        clear_uuid=not bool(uuid_value),
    )
    if uuid_value:
        print_success(
            f"Selected local app '{resolved}' (uuid {uuid_value}) "
            f"for profile '{app_ctx.profile_name}'."
        )
    else:
        print_success(
            f"Selected local app '{resolved}' for profile '{app_ctx.profile_name}' "
            "(no uuid yet — run 'caraer apps push' to create it)."
        )
    return resolved


def _select_remote_uuid(app_ctx: AppContext, app_uuid: str) -> Path:
    from caraer_cli.app_sync import pull_app_full

    # Validate + download full local editable copy, then select both uuid and file.
    result = pull_app_full(
        app_ctx.api_client(),
        app_uuid=app_uuid,
        existing_app_file=app_ctx.profile.app_file,
        force=True,
    )
    app_file = Path(result["app_file"])
    selected_uuid = str(result.get("appUuid") or app_uuid)
    _save_selection(app_ctx, app_uuid=selected_uuid, app_file=str(app_file))
    print_success(
        f"Selected app '{selected_uuid}' for profile '{app_ctx.profile_name}' "
        f"and pulled local folder '{result['root']}'."
    )
    return app_file


def _interactive_select(app_ctx: AppContext) -> None:
    from questionary import Choice

    from caraer_cli.wizard.prompts import WizardCancelled, ask_select

    choices: list[Choice] = []
    for path in discover_local_app_files():
        try:
            summary = local_app_summary(path)
        except Exception:
            summary = {"name": None, "label": path.name, "uuid": None}
        label = summary.get("label") or summary.get("name") or path.name
        uuid_hint = f", uuid {summary['uuid']}" if summary.get("uuid") else ", no uuid yet"
        choices.append(
            Choice(
                title=f"[local] {label} — {path.name}{uuid_hint}",
                value=f"local:{path}",
            )
        )

    try:
        response = apps_api.list_apps(
            app_ctx.api_client(),
            app_type="my",
            page=1,
            limit=50,
        )
        rows = response.get("data") if isinstance(response.get("data"), list) else []
    except Exception as exc:  # noqa: BLE001 - keep picker usable offline
        rows = []
        print_success(f"Could not load remote apps ({exc}); showing local files only.")

    for row in rows:
        if not isinstance(row, dict) or not row.get("uuid"):
            continue
        title = row.get("label") or row.get("name") or row["uuid"]
        choices.append(
            Choice(
                title=f"[remote] {title} — {row['uuid']}",
                value=f"remote:{row['uuid']}",
            )
        )

    if not choices:
        raise typer.BadParameter(
            "No local app files or remote apps found. "
            "Run 'caraer apps init' / 'caraer apps wizard', or create an app remotely."
        )

    try:
        selected = ask_select("Select an app", choices)
    except WizardCancelled:
        raise typer.Exit(code=1) from None

    if selected.startswith("local:"):
        _select_local_file(app_ctx, selected.removeprefix("local:"))
        return
    _select_remote_uuid(app_ctx, selected.removeprefix("remote:"))


@app.command("list")
def list_apps(
    ctx: typer.Context,
    type: str = typer.Option(
        "my",
        "--type",
        help="One of: my, private, public, native, local. Defaults to your created apps.",
        autocompletion=complete_app_list_type,
    ),
    page: int = typer.Option(1, "--page", help="Page number."),
    limit: int = typer.Option(25, "--limit", help="Page size."),
    query: str = typer.Option("", "--query", help="Optional search query."),
) -> None:
    """List apps for the selected company (or local app files with --type local)."""
    app_ctx: AppContext = ctx.obj
    if type == "local":
        rows = []
        for path in discover_local_app_files():
            try:
                rows.append(local_app_summary(path))
            except Exception as exc:  # noqa: BLE001
                rows.append({"source": "local", "path": str(path), "error": str(exc)})
        print_data(rows, app_ctx.output)
        return

    allowed_types = {"my", "private", "public", "native"}
    if type not in allowed_types:
        raise typer.BadParameter(
            "Invalid --type. Use one of: my, private, public, native, local."
        )
    response = apps_api.list_apps(
        app_ctx.api_client(),
        app_type=type,
        page=page,
        limit=limit,
        query=query or None,
    )
    rows = response.get("data")
    if app_ctx.output == "table" and isinstance(rows, list):
        rows = project_rows(
            rows,
            [
                "uuid",
                "name",
                "label",
                "platformVersion",
                "privateApp",
                "installed",
                "authMethod",
                "updatedAt",
            ],
        )
    print_data(rows, app_ctx.output)


@app.command("select")
def select_app(
    ctx: typer.Context,
    target: str | None = typer.Argument(
        None,
        help="App UUID or path to a local app file. Omit to pick interactively.",
        autocompletion=complete_app_ref,
    ),
) -> None:
    """Select a remote app UUID and/or a local app file for the active profile."""
    app_ctx: AppContext = ctx.obj
    if not target:
        _interactive_select(app_ctx)
        return
    if looks_like_local_app_ref(target):
        _select_local_file(app_ctx, target)
        return
    _select_remote_uuid(app_ctx, target)


@app.command("clear")
def clear_app(ctx: typer.Context) -> None:
    """Clear the selected app UUID and local app file from the active profile."""
    app_ctx: AppContext = ctx.obj
    _save_selection(app_ctx, clear_uuid=True, clear_file=True)
    print_success(f"Cleared selected app for profile '{app_ctx.profile_name}'.")


@app.command("current")
def current_app(ctx: typer.Context) -> None:
    """Show the currently selected remote app and/or local app file."""
    app_ctx: AppContext = ctx.obj
    payload: dict[str, Any] = {
        "profile": app_ctx.profile_name,
        "app_uuid": app_ctx.profile.app_uuid,
        "app_file": app_ctx.profile.app_file,
        "company_uuid": app_ctx.profile.company_uuid,
    }
    if app_ctx.profile.app_file:
        try:
            summary = local_app_summary(Path(app_ctx.profile.app_file))
            payload["local"] = summary
        except Exception as exc:  # noqa: BLE001
            payload["local_error"] = str(exc)
    print_data(payload, app_ctx.output)


@app.command("get")
def get_app(
    ctx: typer.Context,
    app_uuid: str | None = typer.Argument(None, help="App UUID (defaults to selected app)."),
    public: bool = typer.Option(False, "--public"),
    full: bool = typer.Option(False, "--full", help="Show the full payload instead of a summary."),
    local: bool = typer.Option(False, "--local", help="Show the selected local app file instead."),
) -> None:
    """Show a summary of an app (use --full for the complete payload)."""
    app_ctx: AppContext = ctx.obj
    if local or (not app_uuid and not app_ctx.profile.app_uuid and app_ctx.profile.app_file):
        path = resolve_app_file(app_ctx, None)
        data = load_local_app(path)
        if app_ctx.output == "table" and isinstance(data, dict) and not full:
            print_data(local_app_summary(path, data), app_ctx.output)
            return
        print_data(data, app_ctx.output)
        return

    resolved = resolve_app_uuid(app_ctx, app_uuid)
    if public:
        response = apps_api.get_public_app(app_ctx.api_client(), resolved)
    else:
        response = apps_api.get_app(app_ctx.api_client(), resolved)
    data = response.get("data")
    if app_ctx.output == "table" and isinstance(data, dict):
        print_app_detail(data, full=full)
        return
    print_data(data, app_ctx.output)


@app.command("init")
def init_app(
    ctx: typer.Context,
    dir: str | None = typer.Option(
        None,
        "--dir",
        "-d",
        help="App directory (defaults to normalized --name / --label).",
    ),
    label: str = typer.Option("My App", "--label", help="Display label for the placeholder."),
    name: str | None = typer.Option(None, "--name", help="App name (normalized). Defaults from --label."),
    app_uuid: str | None = typer.Option(
        None,
        "--app-uuid",
        "--app",
        help="Link to an existing remote app after scaffolding.",
    ),
    runtime: str = typer.Option(
        "nodejs22",
        "--runtime",
        help="App / function runtime: nodejs22 or python312 (always written to the manifest).",
        autocompletion=complete_runtime,
    ),
    auth_method: str = typer.Option(
        "OAUTH2",
        "--auth-method",
        help="App auth method: OAUTH2 or API_KEY (always written to the manifest).",
        autocompletion=complete_auth_method,
    ),
    oauth_redirect_uri: list[str] | None = typer.Option(
        None,
        "--oauth-redirect-uri",
        "--callback-url",
        help="OAuth callback / redirect URL (repeatable; required for OAUTH2).",
    ),
    platform: str = typer.Option(
        "2026.2",
        "--platform",
        help="Workspace platformVersion: 2026.2 (container/V2, default) or 2026.1 (legacy).",
    ),
    function: str = typer.Option(
        "hello-world",
        "--function",
        help="Sample function folder name (empty string to skip).",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing app files."),
    select: bool = typer.Option(True, "--select/--no-select", help="Select the new app file in the profile."),
) -> None:
    """Create a local app folder (manifest + functions + webhooks)."""
    from caraer_cli.api import projects as projects_api
    from caraer_cli.app_sync import ensure_linked
    from caraer_cli.errors import ApiError
    from caraer_cli.project.scaffold import scaffold_app_project
    from caraer_cli.project.schema import PLATFORM_VERSION, PLATFORM_VERSION_V1, load_workspace

    app_ctx: AppContext = ctx.obj
    if runtime not in {"nodejs22", "python312"}:
        raise typer.BadParameter("--runtime must be nodejs22 or python312.")
    if platform not in {PLATFORM_VERSION, PLATFORM_VERSION_V1}:
        raise typer.BadParameter("--platform must be 2026.2 or 2026.1.")
    try:
        payload = build_public_app_placeholder(
            label=label,
            name=name,
            runtime=runtime,
            auth_method=auth_method,
            oauth_redirect_uris=list(oauth_redirect_uri)
            if oauth_redirect_uri
            else [DEFAULT_OAUTH_CALLBACK],
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    # Legacy V1 apps keep runtime on functions only.
    if platform == PLATFORM_VERSION_V1:
        payload.pop("runtime", None)
    project_name = payload["name"]
    project_dir = Path(dir) if dir else Path(project_name)
    linked_app = app_uuid or app_ctx.profile.app_uuid
    project_uuid = None

    if linked_app:
        apps_api.get_app(app_ctx.api_client(), linked_app)
        try:
            response = projects_api.create_or_get_project(
                app_ctx.api_client(), linked_app, project_name
            )
            data = response.get("data") or {}
            project_uuid = data.get("uuid")
            linked_app = data.get("appUuid") or linked_app
        except ApiError:
            pass

    try:
        result = scaffold_app_project(
            project_dir,
            app_payload=payload,
            project_name=project_name,
            app_uuid=linked_app,
            project_uuid=project_uuid,
            sample_function=(function.strip() or None),
            runtime=runtime,
            platform_version=platform,
            force=force,
        )
    except FileExistsError as exc:
        raise typer.BadParameter(str(exc)) from exc

    app_file: Path = result["app_file"]
    if linked_app:
        try:
            ensure_linked(
                app_ctx.api_client(),
                result["root"],
                load_workspace(result["root"]),
                app_uuid=str(linked_app),
            )
        except Exception:  # noqa: BLE001
            pass

    print_success(f"Created app at {result['root']}")
    print_data(
        {
            "root": str(result["root"]),
            "app_file": str(app_file),
            "functions_dir": str(result["functions_dir"]),
            "webhooks_dir": str(result["webhooks_dir"]),
            "sample_function": str(result["sample_function"]) if result["sample_function"] else None,
        },
        app_ctx.output,
    )
    if select:
        _select_local_file(app_ctx, app_file)
    print_success("Edit files under src/app/, then run: caraer apps push")


@app.command("wizard")
@app.command("create-public-wizard", hidden=True)
def wizard_app(
    ctx: typer.Context,
    dir: str | None = typer.Option(
        None,
        "--dir",
        "-d",
        help="Default app directory (confirmable in the wizard).",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite without asking if files exist."),
    select: bool = typer.Option(True, "--select/--no-select", help="Select the generated app file in the profile."),
) -> None:
    """Interactively build a local app folder (manifest + functions + webhooks)."""
    app_ctx: AppContext = ctx.obj
    from caraer_cli.wizard.prompts import WizardCancelled
    from caraer_cli.wizard.public_app import run_public_app_wizard

    try:
        path = run_public_app_wizard(output_dir=dir, force=force)
    except WizardCancelled:
        raise typer.Exit(code=1) from None
    if select:
        _select_local_file(app_ctx, path)


@app.command("pull")
def pull_app(
    ctx: typer.Context,
    app_uuid: str | None = typer.Argument(None, help="App UUID (defaults to selected remote app)."),
    file: str | None = typer.Option(
        None,
        "--file",
        "-f",
        help="Explicit path for app.caraer.yaml.",
    ),
    dir: str | None = typer.Option(
        None,
        "--dir",
        "-d",
        help="Explicit app directory to write into (otherwise a new folder is created for a different app).",
    ),
    force: bool = typer.Option(True, "--force/--no-force", help="Overwrite local files."),
    select: bool = typer.Option(True, "--select/--no-select", help="Select the pulled file in the profile."),
) -> None:
    """Pull a remote app into a local folder.

    Refreshing the same selected app reuses that folder. Pulling a different
    app creates a new folder named after the app (sibling of the current
    project when you are inside one).
    """
    from caraer_cli.app_sync import pull_app_full

    app_ctx: AppContext = ctx.obj
    resolved = resolve_app_uuid(app_ctx, app_uuid)
    try:
        result = pull_app_full(
            app_ctx.api_client(),
            app_uuid=resolved,
            file=file,
            directory=dir,
            existing_app_file=None if file or dir else app_ctx.profile.app_file,
            force=force,
        )
    except FileExistsError as exc:
        raise typer.BadParameter(str(exc)) from exc

    selected_uuid = str(result.get("appUuid") or resolved)
    if select:
        _save_selection(app_ctx, app_uuid=selected_uuid, app_file=str(result["app_file"]))
    print_success(f"Pulled app '{selected_uuid}' to {result['app_file']}")
    print_data(result, app_ctx.output)


@app.command("push")
def push_public(
    ctx: typer.Context,
    app_uuid: str | None = typer.Argument(None, help="App UUID (defaults to selected app)."),
    file: str | None = typer.Option(
        None,
        "--file",
        "-f",
        help="App folder or app.caraer.yaml (defaults to selected local app file / cwd).",
    ),
    patch: str | None = typer.Option(None, "--patch", help="JSON patch merged onto the manifest."),
    deploy: bool = typer.Option(False, "--deploy", help="Deploy after creating a function build."),
    wait: bool = typer.Option(
        True,
        "--wait/--no-wait",
        help="After --deploy on V2 apps, wait for runtimeStatus READY/FAILED (default: wait).",
    ),
    version: str | None = typer.Option(
        None,
        "--version",
        "-V",
        help="Default release version shown in the prompt (must be > previous).",
    ),
    release_notes: str | None = typer.Option(
        None,
        "--notes",
        "--release-notes",
        help="Default release notes shown in the prompt.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Non-interactive: require --version and --notes (no prompts).",
    ),
    delete_missing: bool = typer.Option(
        False,
        "--delete-missing",
        help="Delete remote functions/webhooks missing locally.",
    ),
    legacy_functions: bool = typer.Option(
        False,
        "--legacy-functions",
        help="Sync functions via create/update APIs instead of a build.",
    ),
    target: str = typer.Option("production", "--target", help="production|sandbox"),
) -> None:
    """Push the full local app (manifest, functions, webhooks) to Caraer."""
    from caraer_cli.app_sync import push_app, resolve_app_root
    from caraer_cli.project.release import is_semver
    from caraer_cli.wizard.prompts import WizardCancelled

    app_ctx: AppContext = ctx.obj
    if version is not None:
        version = version.strip()
        if not is_semver(version):
            raise typer.BadParameter("--version must be MAJOR.MINOR.PATCH (e.g. 1.2.3).")
    if yes and (not version or not (release_notes or "").strip()):
        raise typer.BadParameter("--yes requires both --version and --notes.")
    selected_file = file or app_ctx.profile.app_file
    try:
        root = resolve_app_root(app_file=selected_file)
    except FileNotFoundError:
        if selected_file:
            raise typer.BadParameter(
                "Could not resolve an app folder. Run 'caraer apps init' or select a local app."
            ) from None
        raise typer.BadParameter(
            "No app folder found. Run 'caraer apps init' or 'cd' into an app directory."
        ) from None

    patch_data = parse_patch(patch) if patch else None
    try:
        result = push_app(
            app_ctx.api_client(),
            root,
            app_uuid=app_uuid or app_ctx.profile.app_uuid,
            patch=patch_data,
            deploy=deploy,
            delete_missing=delete_missing,
            legacy_functions=legacy_functions,
            target=target,
            wait=wait,
            version=version,
            release_notes=release_notes,
            interactive=not yes,
        )
    except WizardCancelled:
        raise typer.Exit(code=1) from None
    if result.get("appUuid"):
        manifest = resolve_app_file_path(selected_file or root)
        _save_selection(app_ctx, app_uuid=str(result["appUuid"]), app_file=str(manifest))
    print_success("Pushed app (manifest + functions + webhooks).")
    print_data(result, app_ctx.output)


def normalize_function_name(value: str) -> str:
    import re

    normalized = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized


@app.command("add-function")
def add_function(
    ctx: typer.Context,
    name: str | None = typer.Argument(
        None,
        help="Function name / folder (e.g. hello-world). Prompted if omitted.",
    ),
    runtime: str | None = typer.Option(
        None,
        "--runtime",
        help="nodejs22 or python312 (defaults to caraer.json runtime or nodejs22).",
        autocompletion=complete_runtime,
    ),
    description: str = typer.Option("", "--description", help="Function description."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing scaffold files."),
) -> None:
    """Scaffold a local function folder under src/app/functions/<name>/."""
    from caraer_cli.app_sync import resolve_app_root
    from caraer_cli.project.schema import load_workspace
    from caraer_cli.project.sync import scaffold_function
    from caraer_cli.wizard.prompts import require_text

    app_ctx: AppContext = ctx.obj
    name = require_text(name, "Function name", flag="name")
    root = resolve_app_root(app_file=app_ctx.profile.app_file)
    config = load_workspace(root)
    normalized = normalize_function_name(name)
    if not normalized:
        raise ValueError("Function name must contain letters or digits.")
    resolved_runtime = (runtime or config.resolved_runtime("nodejs22")).strip().lower()
    if resolved_runtime not in {"nodejs22", "python312"}:
        raise ValueError("runtime must be nodejs22 or python312")
    try:
        folder = scaffold_function(
            root,
            config,
            normalized,
            resolved_runtime,
            description=description or normalized,
            force=force,
        )
    except FileExistsError as exc:
        raise ValueError(str(exc)) from None
    print_success(f"Created function scaffold at {folder}")


@app.command("add-webhook")
def add_webhook(
    ctx: typer.Context,
    topic: str | None = typer.Option(
        None,
        "--topic",
        "-t",
        help="Webhook topic (e.g. record.created, app.bar.triggered). Prompted if omitted.",
    ),
    function: str | None = typer.Option(
        None,
        "--function",
        "-f",
        help="Local function name for SERVERLESS delivery.",
        autocompletion=complete_local_function,
    ),
    mode: str = typer.Option(
        "SERVERLESS",
        "--mode",
        help="SERVERLESS (default) or HTTP.",
    ),
    url: str | None = typer.Option(None, "--url", help="Destination URL when --mode HTTP."),
    webhook_format: str = typer.Option(
        "USER_FRIENDLY",
        "--format",
        help="Webhook payload format (e.g. USER_FRIENDLY, RAW).",
    ),
    description: str = typer.Option("", "--description", help="Webhook description."),
    filename: str | None = typer.Option(
        None,
        "--filename",
        help="Output file name under webhooks/ (default: <topic>-serverless.json).",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing webhook file."),
) -> None:
    """Scaffold a local webhook JSON under src/app/webhooks/."""
    from caraer_cli.app_sync import resolve_app_root
    from caraer_cli.project.scaffold import scaffold_webhook
    from caraer_cli.project.schema import load_workspace
    from caraer_cli.wizard.prompts import require_text

    app_ctx: AppContext = ctx.obj
    topic = require_text(topic, "Webhook topic", flag="--topic")
    root = resolve_app_root(app_file=app_ctx.profile.app_file)
    config = load_workspace(root)
    resolved_mode = mode.strip().upper()
    function_name = normalize_function_name(function) if function else None
    if resolved_mode == "SERVERLESS" and not function_name:
        function_name = normalize_function_name(
            require_text(None, "Function name", flag="--function")
        )
    if resolved_mode == "HTTP" and not (url and url.strip()):
        url = require_text(None, "Webhook URL", flag="--url")
    if resolved_mode == "SERVERLESS" and not function_name:
        raise ValueError("SERVERLESS webhooks require --function <name>.")
    if resolved_mode == "HTTP" and not (url and url.strip()):
        raise ValueError("HTTP webhooks require --url <https://...>.")
    try:
        path = scaffold_webhook(
            root,
            config,
            topic=topic.strip(),
            function_name=function_name,
            delivery_mode=resolved_mode,
            url=url,
            webhook_format=webhook_format.strip() or "USER_FRIENDLY",
            description=description or None,
            filename=filename,
            force=force,
        )
    except FileExistsError as exc:
        raise ValueError(str(exc)) from None
    print_success(f"Created webhook scaffold at {path}")


@app.command("status")
def app_status(ctx: typer.Context) -> None:
    """Show local↔remote function drift for the current app folder."""
    from caraer_cli.app_sync import resolve_app_root
    from caraer_cli.project.schema import load_workspace
    from caraer_cli.project.sync import status_summary

    app_ctx: AppContext = ctx.obj
    root = resolve_app_root(app_file=app_ctx.profile.app_file)
    config = load_workspace(root)
    print_data(status_summary(app_ctx.api_client(), root, config), app_ctx.output)


@app.command("validate")
def validate_app(
    ctx: typer.Context,
    file: str | None = typer.Option(
        None,
        "--file",
        "-f",
        help="App folder or app.caraer.yaml (defaults to selected local app / cwd).",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Treat warnings as failures (non-zero exit).",
    ),
) -> None:
    """Validate the local app manifest, functions, and webhooks (no API calls)."""
    from caraer_cli.app_sync import resolve_app_root
    from caraer_cli.formatters.output import print_error
    from caraer_cli.project.validate_app import validate_local_app

    app_ctx: AppContext = ctx.obj
    selected = file or app_ctx.profile.app_file
    try:
        root = resolve_app_root(app_file=selected)
    except FileNotFoundError:
        raise typer.BadParameter(
            "No app folder found. Pass --file, select a local app, or cd into an app directory."
        ) from None

    report = validate_local_app(root, strict=strict)
    payload = report.to_dict()
    if app_ctx.output == "table":
        if report.issues:
            print_data(
                [
                    {
                        "severity": issue.severity,
                        "path": issue.path,
                        "message": issue.message,
                    }
                    for issue in report.issues
                ],
                app_ctx.output,
            )
        summary = (
            f"Validated {report.root} — "
            f"{payload['functions']} function(s), {payload['webhooks']} webhook(s), "
            f"{payload['errors']} error(s), {payload['warnings']} warning(s)."
        )
        if report.ok:
            print_success(summary)
        else:
            print_error(summary)
    else:
        print_data(payload, app_ctx.output)

    if not report.ok:
        raise typer.Exit(code=1)


def _prompt_migrate_runtime(*, default: str = "nodejs22", reason: str | None = None) -> str:
    from caraer_cli.formatters.output import print_error

    if reason:
        print_error(reason.rstrip(".") + ".")

    resolved_default = default if default in {"nodejs22", "python312"} else "nodejs22"
    try:
        from questionary import Choice

        from caraer_cli.wizard.prompts import WizardCancelled, ask_select

        try:
            return ask_select(
                "Choose the App runtime for V2",
                [
                    Choice(title="nodejs22 (Node.js 22)", value="nodejs22"),
                    Choice(title="python312 (Python 3.12)", value="python312"),
                ],
                default=resolved_default,
            )
        except WizardCancelled:
            raise typer.Exit(code=1) from None
    except ModuleNotFoundError:
        # questionary is a declared dependency; fall back if the install is incomplete.
        value = typer.prompt(
            "Choose the App runtime for V2 [nodejs22/python312]",
            default=resolved_default,
        ).strip().lower()
        if value not in {"nodejs22", "python312"}:
            raise typer.BadParameter("runtime must be nodejs22 or python312") from None
        return value


@app.command("migrate-v2")
def migrate_v2(
    ctx: typer.Context,
    app_uuid: str | None = typer.Option(
        None,
        "--app",
        "--app-uuid",
        help="Remote app UUID (defaults to selected / linked app).",
    ),
    runtime: str | None = typer.Option(
        None,
        "--runtime",
        help="nodejs22 or python312 (prompted interactively when missing/ambiguous).",
        autocompletion=complete_runtime,
    ),
) -> None:
    """Migrate a V1 app to the V2 shared-container runtime (one-way).

    Keeps webhook delivery on legacy per-function URLs until the new runtime is
    READY, then cut over. Updates local caraer.json to platformVersion 2026.2.
    """
    from caraer_cli.api import apps as apps_api
    from caraer_cli.app_sync import _poll_v2_runtime, resolve_app_root
    from caraer_cli.errors import ApiError
    from caraer_cli.project.paths import workspace_file
    from caraer_cli.project.schema import PLATFORM_VERSION, load_workspace, save_project_config

    app_ctx: AppContext = ctx.obj
    if runtime is not None and runtime not in {"nodejs22", "python312"}:
        raise typer.BadParameter("--runtime must be nodejs22 or python312.")

    resolved = resolve_app_uuid(app_ctx, app_uuid)
    client = app_ctx.api_client()

    local_default = "nodejs22"
    try:
        root = resolve_app_root(app_file=app_ctx.profile.app_file)
        local_default = load_workspace(root).resolved_runtime("nodejs22")
    except (FileNotFoundError, ValueError):
        pass

    try:
        response = apps_api.migrate_app_to_v2(client, resolved, runtime=runtime)
    except ApiError as exc:
        message = str(exc.message or exc)
        needs_runtime = exc.status == 400 and (
            "runtime" in message.lower()
            and (
                "pass runtime=" in message.lower()
                or "mixed runtimes" in message.lower()
                or "cannot infer" in message.lower()
            )
        )
        if runtime is not None or not needs_runtime:
            raise
        runtime = _prompt_migrate_runtime(default=local_default, reason=message)
        response = apps_api.migrate_app_to_v2(client, resolved, runtime=runtime)

    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    migration = data.get("migration") if isinstance(data.get("migration"), dict) else {}
    app_payload = data.get("app") if isinstance(data.get("app"), dict) else {}
    linked_uuid = str(app_payload.get("uuid") or resolved)

    already = bool(migration.get("alreadyMigratingOrMigrated"))
    print_success(
        ("Migration already in progress for " if already else "Migration started for ")
        + f"{linked_uuid} "
        f"(from v{migration.get('fromVersion')} → v{migration.get('toVersion')}, "
        f"runtime={migration.get('runtime')}, functions={migration.get('functionCount')}, "
        f"status={migration.get('runtimeStatus')})."
    )

    # Poll using a temporary V2 workspace config for the public app GET.
    from caraer_cli.project.schema import ProjectConfig

    poll_config = ProjectConfig(
        platformVersion=PLATFORM_VERSION,
        name=str(app_payload.get("name") or "app"),
        appUuid=linked_uuid,
        runtime=str(migration.get("runtime") or runtime or "nodejs22"),
    )
    initial_status = str(migration.get("runtimeStatus") or "").upper()
    if initial_status == "READY":
        runtime_status = {
            "platformVersion": app_payload.get("platformVersion"),
            "runtime": app_payload.get("runtime") or migration.get("runtime"),
            "runtimeStatus": "READY",
            "runtimeBaseUrl": app_payload.get("runtimeBaseUrl"),
            "runtimeRevision": app_payload.get("runtimeRevision"),
            "runtimeError": app_payload.get("runtimeError"),
        }
    else:
        runtime_status = _poll_v2_runtime(client, poll_config, progress=True)
    status = str(runtime_status.get("runtimeStatus") or "").upper()
    if status == "FAILED":
        raise ValueError(
            "V2 runtime deploy failed: "
            + str(runtime_status.get("runtimeError") or "unknown error")
        )
    if status != "READY":
        raise ValueError(
            f"Timed out waiting for runtime READY (last status={status or 'unknown'}). "
            "Ensure the backend AppRuntimeWorker is running, then retry "
            "'caraer apps migrate-v2'."
        )

    # Bump local workspace when we are inside / have selected an app folder.
    try:
        root = resolve_app_root(app_file=app_ctx.profile.app_file)
        config = load_workspace(root)
        if config.appUuid and config.appUuid not in {linked_uuid, resolved}:
            print_success(
                f"Remote app {linked_uuid} is READY; local folder is linked to "
                f"{config.appUuid} — not updating caraer.json."
            )
        else:
            config.platformVersion = PLATFORM_VERSION
            config.appUuid = linked_uuid
            config.runtime = str(
                runtime_status.get("runtime") or migration.get("runtime") or config.runtime or "nodejs22"
            )
            save_project_config(workspace_file(root), config)
            print_success(f"Updated {workspace_file(root)} to platformVersion {PLATFORM_VERSION}.")
    except (FileNotFoundError, ValueError):
        print_success("Remote migration READY. Link/select a local app folder to sync caraer.json.")

    print_data(
        {
            "appUuid": linked_uuid,
            "migration": migration,
            "runtime": runtime_status,
        },
        app_ctx.output,
    )


@app.command("deploy")
def deploy_app(
    ctx: typer.Context,
    build_uuid: str | None = typer.Argument(None, help="Build UUID (defaults to last build)."),
    target: str = typer.Option("production", "--target", help="production|sandbox"),
) -> None:
    """Deploy a previously created build for this app."""
    from caraer_cli.api import projects as projects_api
    from caraer_cli.app_sync import require_project_uuid, resolve_app_root
    from caraer_cli.project.schema import load_workspace
    from caraer_cli.project.state import load_state, save_state

    app_ctx: AppContext = ctx.obj
    root = resolve_app_root(app_file=app_ctx.profile.app_file)
    config = load_workspace(root)
    project_uuid = require_project_uuid(app_ctx.api_client(), root, config)
    state = load_state(root)
    resolved = build_uuid or state.get("lastBuildUuid")
    if not resolved:
        raise ValueError("No build UUID provided and no lastBuildUuid in local state.")
    response = projects_api.deploy_build(
        app_ctx.api_client(), project_uuid, str(resolved), target=target
    )
    data = response.get("data") or {}
    state["lastDeployUuid"] = data.get("uuid")
    save_state(root, state)
    print_success(f"Deployed build {resolved}")
    print_data(data, app_ctx.output)


@app.command("builds")
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


@app.command("deploys")
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


@app.command("version")
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


@app.command("logs")
def app_logs(
    ctx: typer.Context,
    function: str | None = typer.Option(
        None,
        "--function",
        "-f",
        help="Local function name (defaults to the only local function, or prompts).",
        autocompletion=complete_local_function,
    ),
    since: str = typer.Option("1h", "--since", help="Lookback window, e.g. 15m, 1h, 24h."),
    follow: bool = typer.Option(False, "--follow", help="Poll for new log lines."),
    limit: int = typer.Option(100, "--limit", help="Maximum log lines to return."),
) -> None:
    """Fetch remote logs for a local function (defaults to the only function, or prompts)."""
    import time

    from caraer_cli.api import functions as functions_api
    from caraer_cli.api import projects as projects_api
    from caraer_cli.app_sync import resolve_app_root
    from caraer_cli.project.schema import load_workspace
    from caraer_cli.project.state import load_state
    from caraer_cli.project.sync import resolve_local_function_name

    app_ctx: AppContext = ctx.obj
    root = resolve_app_root(app_file=app_ctx.profile.app_file)
    config = load_workspace(root)
    if not config.appUuid:
        raise ValueError("App has no remote UUID. Run 'caraer apps select' or 'caraer apps push'.")
    function_name = resolve_local_function_name(root, config, function)
    state = load_state(root)
    fn_meta = (state.get("functions") or {}).get(function_name) or {}
    function_uuid = fn_meta.get("uuid")
    if not function_uuid:
        remote = functions_api.list_functions(app_ctx.api_client(), config.appUuid, page=1, limit=200)
        for item in remote.get("data") or []:
            if isinstance(item, dict) and item.get("name") == function_name and item.get("uuid"):
                function_uuid = item["uuid"]
                break
    if not function_uuid:
        raise ValueError(
            f"Function '{function_name}' is not tracked locally. Run 'caraer apps push' first."
        )

    client = app_ctx.api_client()
    print_success(f"Fetching logs for '{function_name}'…")
    while True:
        response = projects_api.get_function_logs(
            client,
            config.appUuid,
            str(function_uuid),
            since=since,
            limit=limit,
        )
        print_data(response.get("data"), app_ctx.output)
        if not follow:
            break
        time.sleep(3)


@app.command("dev")
def app_dev(
    ctx: typer.Context,
    function: str | None = typer.Option(
        None,
        "--function",
        "-f",
        help="Optional: serve only this local function (default: all local functions).",
        autocompletion=complete_local_function,
    ),
    port: int = typer.Option(8787, "--port"),
    host: str = typer.Option("127.0.0.1", "--host"),
) -> None:
    """Run a local HTTP server for all functions at http://host:port/<function_name>."""
    from caraer_cli.app_sync import resolve_app_root
    from caraer_cli.project.local_dev import serve_functions
    from caraer_cli.project.schema import load_workspace
    from caraer_cli.project.sync import list_local_function_names, resolve_local_function_name

    root = resolve_app_root(app_file=ctx.obj.profile.app_file)
    config = load_workspace(root)
    if function:
        names = [resolve_local_function_name(root, config, function, interactive=False)]
    else:
        names = list_local_function_names(root, config)
        if not names:
            raise ValueError(
                "No local functions found under src/app/functions/. "
                "Add a function folder first."
            )
    base = f"http://{host}:{port}"
    print_success(f"Starting local dev server on {base}")
    for name in names:
        print_success(f"  POST {base}/{name}")
    serve_functions(
        root,
        config,
        host=host,
        port=port,
        function_names=names,
    )
