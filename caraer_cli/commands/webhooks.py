from __future__ import annotations

import typer

from caraer_cli.api import webhooks as webhook_api
from caraer_cli.context import AppContext
from caraer_cli.formatters.output import print_data
from caraer_cli.resolve import resolve_app_uuid

app = typer.Typer(help="Webhook discovery and test helpers.", no_args_is_help=True)


@app.command("formats")
def formats(
    ctx: typer.Context,
    app_uuid: str | None = typer.Option(
        None, "--app", "--app-uuid", help="App UUID (defaults to selected app)."
    ),
) -> None:
    """List available webhook payload formats."""
    app_ctx: AppContext = ctx.obj
    resolved = resolve_app_uuid(app_ctx, app_uuid)
    response = webhook_api.get_formats(app_ctx.api_client(), resolved)
    print_data(response.get("data", response), app_ctx.output)


@app.command("events")
def events(
    ctx: typer.Context,
    app_uuid: str | None = typer.Option(
        None, "--app", "--app-uuid", help="App UUID (defaults to selected app)."
    ),
) -> None:
    """List available webhook record events."""
    app_ctx: AppContext = ctx.obj
    resolved = resolve_app_uuid(app_ctx, app_uuid)
    response = webhook_api.get_events(app_ctx.api_client(), resolved)
    print_data(response.get("data", response), app_ctx.output)


@app.command("test")
def test(
    ctx: typer.Context,
    webhook_uuid: str | None = typer.Argument(
        None,
        help="Remote webhook UUID. Prompted if omitted.",
    ),
    record: str | None = typer.Option(
        None,
        "--record",
        help="Record UUID to include in the test payload. Prompted if omitted.",
    ),
    event: str = typer.Option("created", "--event", help="Record event type, e.g. created|updated."),
    app_uuid: str | None = typer.Option(
        None, "--app", "--app-uuid", help="App UUID (defaults to selected app)."
    ),
) -> None:
    """Fire a test webhook delivery for a record event."""
    from caraer_cli.wizard.prompts import require_text

    app_ctx: AppContext = ctx.obj
    webhook_uuid = require_text(webhook_uuid, "Webhook UUID", flag="webhook-uuid")
    record = require_text(record, "Record UUID", flag="--record")
    resolved = resolve_app_uuid(app_ctx, app_uuid)
    response = webhook_api.test_webhook(
        app_ctx.api_client(), resolved, webhook_uuid, record, event
    )
    print_data(response.get("data", response), app_ctx.output)
