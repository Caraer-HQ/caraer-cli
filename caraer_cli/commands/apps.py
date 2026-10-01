from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import typer

from caraer_cli.api import apps as apps_api
from caraer_cli.completion_callbacks import (
    complete_app_list_type,
    complete_app_ref,
    complete_auth_method,
    complete_runtime,
)
from caraer_cli.context import AppContext
from caraer_cli.formatters.output import (
    print_app_detail,
    print_data,
    print_success,
    print_warning,
    project_rows,
)
from caraer_cli.formatters.progress import progress_step
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

# Nested command groups.
from caraer_cli.commands import apps_add  # noqa: E402
from caraer_cli.commands import apps_local  # noqa: E402
from caraer_cli.commands import apps_release  # noqa: E402
from caraer_cli.commands import installation as installation_cmds  # noqa: E402
from caraer_cli.commands.deprecation import register_deprecated_leaf_alias  # noqa: E402

app.add_typer(apps_add.add_app, name="add")
app.add_typer(apps_local.local_app, name="local")
app.add_typer(apps_release.release_app, name="release")
app.add_typer(installation_cmds.state_app, name="state")
app.add_typer(installation_cmds.secrets_app, name="secrets")
app.add_typer(installation_cmds.jobs_app, name="jobs")
app.add_typer(installation_cmds.connections_app, name="connections")

apps_add.register_aliases(app)
apps_local.register_aliases(app)
apps_release.register_aliases(app)

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
    private: bool = False,
) -> dict[str, Any]:
    """Build a placeholder app payload for local editing.

    Always includes runtime, authMethod, hideApiKeyField, and oauthRedirectUris.
    Public apps also get marketplace listing placeholders.
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
    payload: dict[str, Any] = {
        "label": resolved_label,
        "name": resolved_name,
        "runtime": runtime,
        "authMethod": method,
        "hideApiKeyField": True,
        "oauthRedirectUris": redirects,
        "requiredScopes": [],
        "settingsSchema": [],
        "settingsSections": [],
        "appBars": [],
        "webhookRateLimitPerMinute": 100,
    }
    if not private:
        payload["brandmark"] = "https://example.com/brandmark.svg"
        payload["details"] = {
            "title": resolved_label,
            "description": "TODO: short marketplace description",
            "category": "developer_tools",
            "subcategories": ["apis"],
            "url": "https://example.com",
            "image": "https://example.com/logo.svg",
            "brandColor": DEFAULT_BRAND_COLOR,
            "textColor": DEFAULT_TEXT_COLOR,
        }
    return payload


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


@app.command("delete")
def delete_app(
    ctx: typer.Context,
    app_uuid: str | None = typer.Argument(None, help="Private app UUID (defaults to the selected app)."),
    yes: bool = typer.Option(False, "--yes", help="Delete without a confirmation prompt."),
) -> None:
    """Delete a private app owned by the active company."""
    from caraer_cli.wizard.prompts import WizardCancelled, ask_confirm

    app_ctx: AppContext = ctx.obj
    resolved = resolve_app_uuid(app_ctx, app_uuid)
    current = apps_api.get_app(app_ctx.api_client(), resolved)
    data = current.get("data") if isinstance(current, dict) else None
    if not isinstance(data, dict) or not data.get("privateApp"):
        raise typer.BadParameter("Only private apps can be deleted.")
    label = str(data.get("label") or data.get("name") or resolved)
    if not yes:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise typer.BadParameter("Pass --yes to delete a private app without a prompt.")
        try:
            if not ask_confirm(f'Delete private app "{label}"?', default=False):
                print_warning("Delete cancelled.")
                raise typer.Exit(code=1)
        except WizardCancelled:
            raise typer.Exit(code=1) from None
    apps_api.delete_private_app(app_ctx.api_client(), resolved)
    if app_ctx.profile.app_uuid == resolved:
        _save_selection(app_ctx, clear_uuid=True)
    print_success(f"Deleted private app {label}.")


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
        "2026.2.1",
        "--platform",
        help="Workspace platformVersion: 2026.2.1 (default), 2026.2, or 2026.1.",
    ),
    function: str = typer.Option(
        "hello-world",
        "--function",
        help="Sample function folder name (empty string to skip).",
    ),
    private: bool = typer.Option(
        False,
        "--private/--public",
        help="Create a company-private app (default is a public marketplace app).",
    ),
    template: str = typer.Option(
        "website",
        "--template",
        help=(
            "Starter layout: website (complete example page, sections, shared component) "
            "or default (minimal hello_world section)."
        ),
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing app files."),
    select: bool = typer.Option(True, "--select/--no-select", help="Select the new app file in the profile."),
) -> None:
    """Create a local app folder (manifest + functions + webhooks)."""
    from caraer_cli.api import projects as projects_api
    from caraer_cli.app_sync import ensure_linked
    from caraer_cli.errors import ApiError
    from caraer_cli.project.scaffold import (
        CMS_PACKAGES_INSTALLED,
        install_npm_dependencies,
        scaffold_app_project,
    )
    from caraer_cli.project.schema import (
        PLATFORM_VERSION,
        PLATFORM_VERSION_V1,
        PLATFORM_VERSION_V2,
        SUPPORTED_PLATFORM_VERSIONS,
        load_workspace,
    )

    app_ctx: AppContext = ctx.obj
    if runtime not in {"nodejs22", "python312"}:
        raise typer.BadParameter("--runtime must be nodejs22 or python312.")
    if platform not in SUPPORTED_PLATFORM_VERSIONS:
        raise typer.BadParameter(
            "--platform must be 2026.2.1, 2026.2, or 2026.1."
        )
    template_value = template.strip().lower()
    if template_value not in {"default", "website"}:
        raise typer.BadParameter("--template must be default or website.")
    try:
        payload = build_public_app_placeholder(
            label=label,
            name=name,
            runtime=runtime,
            auth_method=auth_method,
            oauth_redirect_uris=list(oauth_redirect_uri)
            if oauth_redirect_uri
            else [DEFAULT_OAUTH_CALLBACK],
            private=private,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    # Legacy V1 apps keep runtime on functions only.
    if platform == PLATFORM_VERSION_V1:
        payload.pop("runtime", None)
    project_name = payload["name"]
    project_dir = Path(dir) if dir else Path(project_name)
    # A new workspace must not inherit the previously selected app's identity.
    # Linking an existing app is an explicit choice via --app-uuid / --app.
    linked_app = app_uuid
    project_uuid = None
    private_app = private

    if linked_app:
        with progress_step("Fetching linked app"):
            remote = apps_api.get_app(app_ctx.api_client(), linked_app).get("data") or {}
        if isinstance(remote, dict) and remote.get("privateApp"):
            private_app = True
        try:
            with progress_step("Preparing remote project"):
                response = projects_api.create_or_get_project(
                    app_ctx.api_client(), linked_app, project_name
                )
            data = response.get("data") or {}
            project_uuid = data.get("uuid")
            linked_app = data.get("appUuid") or linked_app
        except ApiError:
            pass

    try:
        with progress_step(f"Creating app files in {project_dir}"):
            result = scaffold_app_project(
                project_dir,
                app_payload=payload,
                project_name=project_name,
                app_uuid=linked_app,
                project_uuid=project_uuid,
                sample_function=(function.strip() or None),
                runtime=runtime,
                platform_version=platform,
                private_app=private_app,
                template=template_value,
                force=force,
            )
    except FileExistsError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if result.get("sample_module"):
        try:
            if install_npm_dependencies(result["root"]):
                print_success(CMS_PACKAGES_INSTALLED)
        except RuntimeError as exc:
            print_warning(f"Could not install CMS module packages: {exc}")

    app_file: Path = result["app_file"]
    if linked_app:
        try:
            with progress_step("Linking app to remote project"):
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
            "modules_dir": str(result["modules_dir"]),
            "lifecycle_dir": str(result["lifecycle_dir"]),
            "lifecycle_hooks": [
                h["event"] for h in (result.get("lifecycle_hooks") or [])
            ],
            "sample_function": str(result["sample_function"]) if result["sample_function"] else None,
            "sample_module": str(result["sample_module"]) if result["sample_module"] else None,
            "sample_modules": [
                str(path) for path in (result.get("sample_modules") or []) if path
            ],
        },
        app_ctx.output,
    )
    if select:
        _select_local_file(app_ctx, app_file)
    if platform == "2026.2.1":
        modules_hint = (
            "Website starters are under src/app/modules/. Preview Home with npm run dev; see README.md."
            if template_value == "website"
            else "A starter CMS module is under src/app/modules/hello_world. "
            "CMS apps can use --template website."
        )
        print_success(
            "Lifecycle hooks are src/app/lifecycle/{install,uninstall,rotate,update}.js. "
            f"{modules_hint} "
            "Edit files under src/app/, then run: caraer apps push"
        )
    else:
        print_success(
            "Lifecycle hooks (install/uninstall/rotate/update) are under "
            "src/app/lifecycle/ + functions/on-*. A starter CMS module is under "
            "src/app/modules/hello_world. Edit files under src/app/, "
            "then run: caraer apps push"
        )


@app.command("wizard")
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


register_deprecated_leaf_alias(
    app,
    app,
    source_name="wizard",
    alias_name="create-public-wizard",
    old_path="caraer apps create-public-wizard",
    new_path="caraer apps wizard",
)


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
    project when you are inside one). After the manifest is written, the
    currently deployed build archive is downloaded and extracted so functions
    and CMS modules match that deploy.
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


def _require_app_root(selected_file: str | None) -> Path:
    from caraer_cli.app_sync import resolve_app_root

    try:
        return resolve_app_root(app_file=selected_file)
    except FileNotFoundError:
        if selected_file:
            raise typer.BadParameter(
                "Could not resolve an app folder. Run 'caraer apps init' or select a local app."
            ) from None
        raise typer.BadParameter(
            "No app folder found. Run 'caraer apps init' or 'cd' into an app directory."
        ) from None


def _maybe_upgrade_layout_on_push(
    root: Path,
    *,
    upgrade: bool | None,
    yes: bool,
    dry_run: bool,
) -> None:
    import sys

    from caraer_cli.project.layout_upgrade import offer_layout_upgrade_on_push
    from caraer_cli.wizard.prompts import WizardCancelled, ask_confirm

    interactive = sys.stdin.isatty() and sys.stdout.isatty() and not yes

    def _confirm(message: str) -> bool:
        print_warning(
            "2026.2 still works, but 2026.2.1 is the current source layout "
            "(flat functions, JS lifecycle/inbound/schedules, YAML settings)."
        )
        return ask_confirm(message, default=True)

    try:
        outcome = offer_layout_upgrade_on_push(
            root,
            upgrade=upgrade,
            yes=yes,
            dry_run=dry_run,
            interactive=interactive,
            confirm=_confirm if interactive else None,
        )
    except WizardCancelled:
        print_warning("Keeping 2026.2.")
        return
    action = str(outcome.get("action") or "")
    if action == "announce":
        print_warning(str(outcome.get("message") or ""))
        return
    if action == "declined":
        print_warning(str(outcome.get("message") or ""))
        return
    if action == "applied":
        print_success("Upgraded workspace to 2026.2.1.")


def _normalize_release_args(
    *,
    version: str | None,
    release_notes: str | None,
    yes: bool,
    dry_run: bool,
    require_release: bool,
) -> tuple[str | None, str | None]:
    from caraer_cli.project.release import is_semver

    if version is not None:
        version = version.strip()
        if not is_semver(version):
            raise typer.BadParameter("--version must be MAJOR.MINOR.PATCH (e.g. 1.2.3).")
    if require_release and yes and not dry_run and not version:
        raise typer.BadParameter("--yes requires --version.")
    return version, release_notes


def _confirm_push_plan(
    app_ctx: AppContext,
    client: Any,
    root: Path,
    *,
    app_uuid: str | None = None,
    delete_missing: bool,
    dry_run: bool,
    yes: bool,
    confirm_message: str,
    extra_dry_run: str | None = None,
) -> bool:
    """Print the push plan. Return True to continue, False after a dry-run."""
    import sys

    from caraer_cli.project.push_plan import build_push_plan, print_push_plan
    from caraer_cli.project.schema import load_workspace
    from caraer_cli.wizard.prompts import WizardCancelled, ask_confirm

    config = load_workspace(root)
    if app_uuid:
        config.appUuid = app_uuid
    interactive_tty = sys.stdin.isatty() and sys.stdout.isatty()
    show_plan = dry_run or (interactive_tty and not yes)
    if not show_plan:
        return True
    plan = build_push_plan(client, root, config, delete_missing=delete_missing)
    if app_ctx.output in {"json", "yaml"}:
        print_data(plan, app_ctx.output)
    else:
        print_push_plan(plan)
    if extra_dry_run:
        print_success(extra_dry_run)
    if dry_run:
        print_success("Dry run complete — no changes written.")
        return False
    try:
        if not ask_confirm(confirm_message, default=False):
            print_warning("Push cancelled.")
            raise typer.Exit(code=1)
    except WizardCancelled:
        raise typer.Exit(code=1) from None
    return True


def _run_push(
    app_ctx: AppContext,
    *,
    root: Path,
    selected_file: str | None,
    app_uuid: str | None,
    patch: str | None,
    deploy: bool,
    wait: bool,
    version: str | None,
    release_notes: str | None,
    yes: bool,
    delete_missing: bool,
    legacy_functions: bool,
    target: str,
) -> dict[str, Any]:
    from caraer_cli.app_sync import push_app
    from caraer_cli.wizard.prompts import WizardCancelled

    patch_data = parse_patch(patch) if patch else None
    try:
        result = push_app(
            app_ctx.api_client(),
            root,
            app_uuid=app_uuid,
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
    except ValueError as exc:
        print_warning(str(exc))
        raise typer.Exit(code=1) from None
    if result.get("appUuid"):
        manifest = resolve_app_file_path(selected_file or root)
        _save_selection(app_ctx, app_uuid=str(result["appUuid"]), app_file=str(manifest))
    return result


@app.command("push")
def push_public(
    ctx: typer.Context,
    app_uuid: str | None = typer.Argument(None, help="App UUID (defaults to this folder's app)."),
    file: str | None = typer.Option(
        None,
        "--file",
        "-f",
        help="App folder or app.caraer.yaml (defaults to selected local app file / cwd).",
    ),
    patch: str | None = typer.Option(None, "--patch", help="JSON patch merged onto the manifest."),
    deploy: bool = typer.Option(
        True,
        "--deploy/--no-deploy",
        help="Create a function build and deploy it (default). Use --no-deploy to sync only.",
    ),
    wait: bool = typer.Option(
        False,
        "--wait/--no-wait",
        help=(
            "Wait for function runtime provisioning (READY/FAILED) before "
            "publishing CMS modules. Default: skip wait and continue."
        ),
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
        help="Non-interactive: skip confirmation; require --version when deploying.",
    ),
    upgrade: bool | None = typer.Option(
        None,
        "--upgrade/--no-upgrade",
        help=(
            "Rewrite a 2026.2 workspace to 2026.2.1 before push. "
            "Interactive push asks first (default yes). --yes also upgrades."
        ),
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show the create/update/delete plan and exit without writing.",
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
    """Validate the local app, then push it to Caraer and deploy it.

    Same command for private and public apps. Creates the remote app on first
    run, deploys the function build, publishes CMS modules, and installs on
    the selected company. Use --no-deploy to sync without a build, and --wait
    to block until function runtime provisioning finishes.
    """
    from caraer_cli.app_install import install_app_on_company
    from caraer_cli.app_sync import validate_before_push
    from caraer_cli.formatters.output import print_error

    app_ctx: AppContext = ctx.obj
    version, release_notes = _normalize_release_args(
        version=version,
        release_notes=release_notes,
        yes=yes,
        dry_run=dry_run,
        require_release=deploy,
    )
    selected_file = file or app_ctx.pinned_app_file
    root = _require_app_root(selected_file)
    try:
        validate_before_push(root)
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None
    _maybe_upgrade_layout_on_push(
        root, upgrade=upgrade, yes=yes, dry_run=dry_run
    )
    if target == "sandbox":
        print_warning(
            "Sandbox target isolates Neo4j data via X-Caraer-Sandbox-Uuid, "
            "but function runtime code is shared with production."
        )
    company = app_ctx.profile.company_uuid
    extra = f"Would install on company {company}." if dry_run and company else None
    if not _confirm_push_plan(
        app_ctx,
        app_ctx.api_client(),
        root,
        app_uuid=app_uuid,
        delete_missing=delete_missing,
        dry_run=dry_run,
        yes=yes,
        confirm_message="Proceed with push?",
        extra_dry_run=extra,
    ):
        return
    result = _run_push(
        app_ctx,
        root=root,
        selected_file=selected_file,
        app_uuid=app_uuid,
        patch=patch,
        deploy=deploy,
        wait=wait,
        version=version,
        release_notes=release_notes,
        yes=yes,
        delete_missing=delete_missing,
        legacy_functions=legacy_functions,
        target=target,
    )
    from caraer_cli.formatters.output import PushProgress

    installed_uuid = str(result.get("appUuid") or "")
    progress = PushProgress()
    if company and installed_uuid:
        progress.start("Installing on company")
        result["install"] = install_app_on_company(app_ctx.api_client(), installed_uuid)
        progress.finish()
        print_success(f"Pushed and installed app '{installed_uuid}'.")
    else:
        print_success("Pushed app (manifest + functions + webhooks).")
        if not company:
            print_warning(
                "Skipped company install. Select a company with "
                "'caraer company select <uuid>'."
            )
    print_data(result, app_ctx.output)



@app.command("status")
def app_status(ctx: typer.Context) -> None:
    """Show local↔remote function drift for the current app folder."""
    from caraer_cli.app_sync import resolve_app_root
    from caraer_cli.project.schema import load_workspace
    from caraer_cli.project.sync import status_summary

    app_ctx: AppContext = ctx.obj
    root = resolve_app_root(app_file=app_ctx.pinned_app_file)
    config = load_workspace(root)
    print_data(status_summary(app_ctx.api_client(), root, config), app_ctx.output)


@app.command("upgrade")
def upgrade_app(ctx: typer.Context) -> None:
    """Rewrite a 2026.2 workspace into the 2026.2.1 file layout.

    `caraer apps push` also offers this rewrite (default yes). Use this
    command to upgrade without deploying.
    """
    from caraer_cli.app_sync import resolve_app_root
    from caraer_cli.project.layout_upgrade import upgrade_layout_to_v21

    app_ctx: AppContext = ctx.obj
    root = resolve_app_root(app_file=app_ctx.pinned_app_file)
    result = upgrade_layout_to_v21(root)
    if result.get("skipped"):
        print_warning(str(result.get("reason") or "Already on 2026.2.1."))
        return
    print_success("Upgraded workspace to 2026.2.1.")
    print_data(result, app_ctx.output)


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
    """Validate the local app (manifest, functions, marketplace modules, lifecycle)."""
    from caraer_cli.app_sync import resolve_app_root
    from caraer_cli.formatters.output import print_error
    from caraer_cli.project.validate_app import validate_local_app

    app_ctx: AppContext = ctx.obj
    selected = file or app_ctx.pinned_app_file
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
            f"{payload['functions']} function(s), {payload['settings']} setting(s), "
            f"{payload['appBars']} app bar(s), "
            f"{payload['lifecycleHooks']} lifecycle hook(s), "
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

