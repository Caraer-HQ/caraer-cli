"""Installation runtime commands: state, secrets, jobs, connections."""

from __future__ import annotations

import json
from typing import Any

import typer

from caraer_cli.context import AppContext
from caraer_cli.formatters.output import print_data, print_success

state_app = typer.Typer(help="Installation state (key/value store).", no_args_is_help=True)
secrets_app = typer.Typer(help="Installation secrets.", no_args_is_help=True)
jobs_app = typer.Typer(help="Installation background jobs.", no_args_is_help=True)
connections_app = typer.Typer(help="External OAuth connections.", no_args_is_help=True)


def _require_app_uuid(ctx: typer.Context) -> tuple[AppContext, str]:
    from caraer_cli.app_sync import resolve_app_root
    from caraer_cli.project.schema import load_workspace

    app_ctx: AppContext = ctx.obj
    root = resolve_app_root(app_file=app_ctx.profile.app_file)
    config = load_workspace(root)
    if not config.appUuid:
        raise ValueError("App has no remote UUID. Run 'caraer apps select' or 'caraer apps push'.")
    return app_ctx, config.appUuid


@state_app.command("get")
def state_get(
    ctx: typer.Context,
    key: str | None = typer.Argument(None, help="Optional state key (omit for full map)."),
) -> None:
    """Get installation state (all keys, or one key)."""
    from caraer_cli.api import installation as installation_api

    app_ctx, app_uuid = _require_app_uuid(ctx)
    client = app_ctx.api_client()
    if key:
        response = installation_api.get_state_key(client, app_uuid, key)
    else:
        response = installation_api.get_state(client, app_uuid)
    print_data(response.get("data"), app_ctx.output)


@state_app.command("set")
def state_set(
    ctx: typer.Context,
    key: str = typer.Argument(..., help="State key."),
    value: str = typer.Argument(..., help="JSON or plain string value."),
) -> None:
    """Set an installation state key."""
    from caraer_cli.api import installation as installation_api

    app_ctx, app_uuid = _require_app_uuid(ctx)
    try:
        parsed: Any = json.loads(value)
    except json.JSONDecodeError:
        parsed = value
    response = installation_api.put_state_key(app_ctx.api_client(), app_uuid, key, parsed)
    print_success(f"Set state key '{key}'")
    print_data(response.get("data"), app_ctx.output)


@state_app.command("delete")
def state_delete(
    ctx: typer.Context,
    key: str = typer.Argument(..., help="State key to delete."),
) -> None:
    """Delete an installation state key."""
    from caraer_cli.api import installation as installation_api

    app_ctx, app_uuid = _require_app_uuid(ctx)
    response = installation_api.delete_state_key(app_ctx.api_client(), app_uuid, key)
    print_success(f"Deleted state key '{key}'")
    print_data(response.get("data"), app_ctx.output)


@secrets_app.command("list")
def secrets_list(ctx: typer.Context) -> None:
    """List installation secret names (values are never returned)."""
    from caraer_cli.api import installation as installation_api

    app_ctx, app_uuid = _require_app_uuid(ctx)
    response = installation_api.list_secrets(app_ctx.api_client(), app_uuid)
    print_data(response.get("data"), app_ctx.output)


@secrets_app.command("set")
def secrets_set(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Secret name."),
    value: str = typer.Argument(..., help="Secret value."),
) -> None:
    """Create or update an installation secret."""
    from caraer_cli.api import installation as installation_api

    app_ctx, app_uuid = _require_app_uuid(ctx)
    response = installation_api.put_secret(app_ctx.api_client(), app_uuid, name, value)
    print_success(f"Set secret '{name}'")
    print_data(response.get("data"), app_ctx.output)


@secrets_app.command("delete")
def secrets_delete(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Secret name to delete."),
) -> None:
    """Delete an installation secret."""
    from caraer_cli.api import installation as installation_api

    app_ctx, app_uuid = _require_app_uuid(ctx)
    response = installation_api.delete_secret(app_ctx.api_client(), app_uuid, name)
    print_success(f"Deleted secret '{name}'")
    print_data(response.get("data"), app_ctx.output)


@jobs_app.command("enqueue")
def jobs_enqueue(
    ctx: typer.Context,
    function_name: str = typer.Argument(..., help="Function name to invoke."),
    payload: str = typer.Option("{}", "--payload", help="JSON payload object."),
    delay_seconds: float = typer.Option(0, "--delay", help="Delay before invoke (seconds)."),
) -> None:
    """Enqueue a background job for a function."""
    from caraer_cli.api import installation as installation_api

    app_ctx, app_uuid = _require_app_uuid(ctx)
    try:
        body = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid --payload JSON: {exc}") from exc
    if not isinstance(body, dict):
        raise ValueError("--payload must be a JSON object")
    response = installation_api.enqueue_job(
        app_ctx.api_client(),
        app_uuid,
        function_name=function_name,
        payload=body,
        delay_seconds=delay_seconds,
    )
    print_success("Job enqueued")
    print_data(response.get("data"), app_ctx.output)


@jobs_app.command("status")
def jobs_status(
    ctx: typer.Context,
    job_id: str = typer.Argument(..., help="Job id from enqueue."),
) -> None:
    """Get status for an installation job."""
    from caraer_cli.api import installation as installation_api

    app_ctx, app_uuid = _require_app_uuid(ctx)
    response = installation_api.get_job(app_ctx.api_client(), app_uuid, job_id)
    print_data(response.get("data"), app_ctx.output)


@connections_app.command("list")
def connections_list(ctx: typer.Context) -> None:
    """List external OAuth connection status for this app installation."""
    from caraer_cli.api import installation as installation_api

    app_ctx, app_uuid = _require_app_uuid(ctx)
    response = installation_api.list_connections(app_ctx.api_client(), app_uuid)
    print_data(response.get("data"), app_ctx.output)


@connections_app.command("revoke")
def connections_revoke(
    ctx: typer.Context,
    provider: str = typer.Argument(..., help="Provider name to revoke."),
) -> None:
    """Revoke an external OAuth connection."""
    from caraer_cli.api import installation as installation_api

    app_ctx, app_uuid = _require_app_uuid(ctx)
    response = installation_api.delete_connection(app_ctx.api_client(), app_uuid, provider)
    print_success(f"Revoked connection '{provider}'")
    print_data(response.get("data"), app_ctx.output)
