from __future__ import annotations

import sys
from typing import Any

import typer

from caraer_cli.api import webhooks as webhook_api
from caraer_cli.api.client import CaraerApiClient
from caraer_cli.context import AppContext
from caraer_cli.formatters.output import print_data
from caraer_cli.resolve import resolve_app_uuid

app = typer.Typer(help="Webhook discovery and test helpers.", no_args_is_help=True)


def webhook_choice_title(row: dict[str, Any]) -> str:
    """Build a human-readable label for a remote webhook row."""
    topic = str(row.get("topic") or "webhook").strip() or "webhook"
    mode = str(row.get("deliveryMode") or "").strip()
    enabled = row.get("enabled")
    if enabled is True:
        status = "enabled"
    elif enabled is False:
        status = "disabled"
    else:
        status = ""

    target = ""
    serverless = row.get("serverlessFunction")
    if isinstance(serverless, dict):
        target = str(serverless.get("name") or serverless.get("uuid") or "").strip()
    if not target:
        target = str(row.get("url") or "").strip()

    parts = [topic]
    if mode:
        parts.append(mode)
    if status:
        parts.append(status)
    if target:
        parts.append(target)

    title = " · ".join(parts)
    description = str(row.get("description") or "").strip()
    if description:
        if len(description) > 48:
            description = description[:45] + "..."
        title = f"{title} — {description}"

    uuid = str(row.get("uuid") or "").strip()
    if uuid:
        title = f"{title} ({uuid})"
    return title


def resolve_webhook_uuid(
    client: CaraerApiClient,
    app_uuid: str,
    webhook_uuid: str | None,
) -> str:
    """Return an explicit webhook UUID, or prompt the user to pick from a list."""
    if webhook_uuid is not None and str(webhook_uuid).strip():
        return str(webhook_uuid).strip()

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError(
            "Missing required value: webhook-uuid "
            "(pass a webhook UUID, or run interactively to pick from a list)"
        )

    from questionary import Choice

    from caraer_cli.wizard.prompts import WizardCancelled, ask_select

    response = webhook_api.list_webhooks(client, app_uuid, page=1, limit=200)
    rows = [
        row
        for row in (response.get("data") or [])
        if isinstance(row, dict) and row.get("uuid")
    ]
    if not rows:
        raise ValueError(
            "No webhooks found for this app. Create one locally under "
            "src/app/webhooks/ and push, or pass a webhook UUID explicitly."
        )

    choices = [
        Choice(title=webhook_choice_title(row), value=str(row["uuid"])) for row in rows
    ]
    try:
        return ask_select("Select a webhook", choices)
    except WizardCancelled:
        raise typer.Exit(code=1) from None


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
        help="Remote webhook UUID. Interactive list if omitted.",
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
    resolved = resolve_app_uuid(app_ctx, app_uuid)
    webhook_uuid = resolve_webhook_uuid(app_ctx.api_client(), resolved, webhook_uuid)
    record = require_text(record, "Record UUID", flag="--record")
    response = webhook_api.test_webhook(
        app_ctx.api_client(), resolved, webhook_uuid, record, event
    )
    print_data(response.get("data", response), app_ctx.output)
