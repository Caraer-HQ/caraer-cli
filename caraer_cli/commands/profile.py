from __future__ import annotations

from copy import deepcopy

import typer

from caraer_cli.completion_callbacks import complete_output_format, complete_profile
from caraer_cli.context import AppContext
from caraer_cli.formatters.output import print_data, print_success
from caraer_cli.state.config import ProfileConfig, profile_as_dict, save_config

app = typer.Typer(help="Manage CLI config profiles.", no_args_is_help=True)


def _require_profile(app_ctx: AppContext, name: str) -> ProfileConfig:
    if name not in app_ctx.config.profiles:
        raise typer.BadParameter(f"Unknown profile '{name}'.")
    return app_ctx.config.profiles[name]


def _resolve_target(app_ctx: AppContext, name: str | None) -> tuple[str, ProfileConfig]:
    target = (name or app_ctx.profile_name).strip()
    return target, _require_profile(app_ctx, target)


@app.command("list")
def list_profiles(ctx: typer.Context) -> None:
    """List all profiles (marks the active one)."""
    app_ctx: AppContext = ctx.obj
    rows = []
    for name, profile in app_ctx.config.profiles.items():
        row = profile_as_dict(profile)
        row["name"] = name
        row["active"] = name == app_ctx.config.active_profile
        rows.append(row)
    print_data(rows, app_ctx.output)


@app.command("show")
def show_profile(
    ctx: typer.Context,
    name: str | None = typer.Argument(
        None,
        help="Profile name (defaults to the active profile).",
        autocompletion=complete_profile,
    ),
) -> None:
    """Show one profile's settings."""
    app_ctx: AppContext = ctx.obj
    target, profile = _resolve_target(app_ctx, name)
    output = profile_as_dict(profile)
    output["name"] = target
    output["active"] = target == app_ctx.config.active_profile
    print_data(output, app_ctx.output)


@app.command("current")
def current_profile(ctx: typer.Context) -> None:
    """Show the active profile name and settings."""
    app_ctx: AppContext = ctx.obj
    output = profile_as_dict(app_ctx.profile)
    output["name"] = app_ctx.profile_name
    output["active"] = True
    print_data(output, app_ctx.output)


@app.command("use")
def use_profile(
    ctx: typer.Context,
    name: str = typer.Argument(
        ...,
        help="Profile name to activate.",
        autocompletion=complete_profile,
    ),
) -> None:
    """Switch the active profile."""
    app_ctx: AppContext = ctx.obj
    _require_profile(app_ctx, name)
    app_ctx.config.active_profile = name
    save_config(app_ctx.config)
    print_success(f"Set active profile to '{name}'.")


@app.command("create")
def create_profile(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="New profile name."),
    base_url: str = typer.Option(
        None,
        "--base-url",
        help="API base URL (required unless --from is set).",
    ),
    from_profile: str | None = typer.Option(
        None,
        "--from",
        help="Copy settings from an existing profile.",
        autocompletion=complete_profile,
    ),
    use: bool = typer.Option(False, "--use", help="Make this the active profile."),
) -> None:
    """Create a new profile, optionally copied from an existing one."""
    app_ctx: AppContext = ctx.obj
    name = name.strip()
    if not name:
        raise typer.BadParameter("Profile name cannot be empty.")
    if name in app_ctx.config.profiles:
        raise typer.BadParameter(f"Profile '{name}' already exists.")

    if from_profile:
        source = _require_profile(app_ctx, from_profile)
        profile = deepcopy(source)
        if base_url:
            profile.base_url = base_url
    else:
        if not base_url:
            raise typer.BadParameter("--base-url is required when not using --from.")
        profile = ProfileConfig(base_url=base_url)

    app_ctx.config.profiles[name] = profile
    if use:
        app_ctx.config.active_profile = name
    save_config(app_ctx.config)
    message = f"Created profile '{name}'."
    if use:
        message += " Set as active."
    print_success(message)


@app.command("delete")
def delete_profile(
    ctx: typer.Context,
    name: str = typer.Argument(
        ...,
        help="Profile name to delete.",
        autocompletion=complete_profile,
    ),
    force: bool = typer.Option(False, "--force", help="Allow deleting the active profile."),
) -> None:
    """Delete a profile."""
    app_ctx: AppContext = ctx.obj
    _require_profile(app_ctx, name)
    if len(app_ctx.config.profiles) <= 1:
        raise typer.BadParameter("Cannot delete the last remaining profile.")
    if name == app_ctx.config.active_profile and not force:
        raise typer.BadParameter(
            f"'{name}' is the active profile. Switch first, or pass --force."
        )

    del app_ctx.config.profiles[name]
    if app_ctx.config.active_profile == name:
        app_ctx.config.active_profile = next(iter(app_ctx.config.profiles.keys()))
    save_config(app_ctx.config)
    print_success(f"Deleted profile '{name}'.")


@app.command("set")
def set_profile(
    ctx: typer.Context,
    name: str | None = typer.Argument(
        None,
        help="Profile to update (defaults to the active profile).",
        autocompletion=complete_profile,
    ),
    base_url: str | None = typer.Option(None, "--base-url", help="API base URL."),
    company_uuid: str | None = typer.Option(None, "--company-uuid", help="Selected company UUID."),
    app_uuid: str | None = typer.Option(None, "--app-uuid", help="Selected remote app UUID."),
    app_file: str | None = typer.Option(None, "--app-file", help="Selected local app file path."),
    output: str | None = typer.Option(
        None,
        "--output",
        help="Default output format: table|json|yaml.",
        autocompletion=complete_output_format,
    ),
    timeout_seconds: float | None = typer.Option(
        None,
        "--timeout-seconds",
        help="HTTP timeout in seconds.",
    ),
    verify_ssl: bool | None = typer.Option(
        None,
        "--verify-ssl/--no-verify-ssl",
        help="Verify TLS certificates.",
    ),
    clear_company: bool = typer.Option(False, "--clear-company", help="Clear company_uuid."),
    clear_app: bool = typer.Option(False, "--clear-app", help="Clear app_uuid."),
    clear_app_file: bool = typer.Option(False, "--clear-app-file", help="Clear app_file."),
) -> None:
    """Update fields on a profile."""
    app_ctx: AppContext = ctx.obj
    target, profile = _resolve_target(app_ctx, name)

    updates: list[str] = []
    if base_url is not None:
        profile.base_url = base_url
        updates.append("base_url")
    if company_uuid is not None:
        profile.company_uuid = company_uuid.strip() or None
        updates.append("company_uuid")
    if app_uuid is not None:
        profile.app_uuid = app_uuid.strip() or None
        updates.append("app_uuid")
    if app_file is not None:
        profile.app_file = app_file.strip() or None
        updates.append("app_file")
    if output is not None:
        normalized = output.strip().lower()
        if normalized not in {"table", "json", "yaml"}:
            raise typer.BadParameter("output must be one of: table, json, yaml.")
        profile.output = normalized
        updates.append("output")
    if timeout_seconds is not None:
        if timeout_seconds <= 0:
            raise typer.BadParameter("timeout-seconds must be greater than 0.")
        profile.timeout_seconds = timeout_seconds
        updates.append("timeout_seconds")
    if verify_ssl is not None:
        profile.verify_ssl = verify_ssl
        updates.append("verify_ssl")
    if clear_company:
        profile.company_uuid = None
        updates.append("company_uuid")
    if clear_app:
        profile.app_uuid = None
        updates.append("app_uuid")
    if clear_app_file:
        profile.app_file = None
        updates.append("app_file")

    if not updates:
        raise typer.BadParameter("No fields to update. Pass at least one option.")

    save_config(app_ctx.config)
    unique = ", ".join(dict.fromkeys(updates))
    print_success(f"Updated {unique} on profile '{target}'.")
