from __future__ import annotations

from typing import Any

import typer

from caraer_cli.api import billing as billing_api
from caraer_cli.context import AppContext
from caraer_cli.formatters.output import print_data
from caraer_cli.resolve import resolve_app_uuid

app = typer.Typer(help="App billing, usage, and subscription commands.", no_args_is_help=True)
subscription_app = typer.Typer(help="Schedule and inspect subscription changes.", no_args_is_help=True)
meter_app = typer.Typer(help="Manual meter events.", no_args_is_help=True)
app.add_typer(subscription_app, name="subscription")
app.add_typer(meter_app, name="meter")


def _unwrap(payload: dict[str, Any]) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


@app.command("status")
def billing_status(
    ctx: typer.Context,
    app_uuid: str | None = typer.Option(None, "--app", help="App UUID."),
    all_apps: bool = typer.Option(False, "--all", help="Platform-wide status (super admin)."),
    app_wide: bool = typer.Option(
        False,
        "--app-wide",
        help="Creator rollup across every installation (developer).",
    ),
    period: str = typer.Option("current", "--period", help="Billing period (current)."),
) -> None:
    """Show current-period billing status for the selected company's installation."""
    del period
    app_ctx: AppContext = ctx.obj
    client = app_ctx.api_client()
    if all_apps:
        payload = billing_api.get_platform_billing_status(client)
    elif app_wide:
        resolved = resolve_app_uuid(app_ctx, app_uuid)
        payload = billing_api.get_app_billing_status(client, resolved)
    else:
        resolved = resolve_app_uuid(app_ctx, app_uuid)
        payload = billing_api.get_installation_billing_status(client, resolved)
    print_data(_unwrap(payload), app_ctx.output)


@app.command("periods")
def billing_periods(
    ctx: typer.Context,
    app_uuid: str | None = typer.Option(None, "--app", help="App UUID."),
) -> None:
    """List usage periods for the selected company's installation."""
    app_ctx: AppContext = ctx.obj
    client = app_ctx.api_client()
    resolved = resolve_app_uuid(app_ctx, app_uuid)
    payload = billing_api.get_usage_periods(client, resolved)
    print_data(_unwrap(payload), app_ctx.output)


@meter_app.command("record")
def meter_record(
    ctx: typer.Context,
    line_item: str = typer.Option(..., "--line-item", help="Line item name."),
    quantity: int = typer.Option(..., "--quantity", help="Units to record."),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
    app_uuid: str | None = typer.Option(None, "--app", help="App UUID."),
) -> None:
    """Record a manual meter event for the selected company's installation."""
    app_ctx: AppContext = ctx.obj
    client = app_ctx.api_client()
    resolved = resolve_app_uuid(app_ctx, app_uuid)
    payload = billing_api.record_meter_event(
        client,
        resolved,
        line_item_name=line_item,
        quantity=quantity,
        idempotency_key=idempotency_key,
    )
    print_data(_unwrap(payload), app_ctx.output)


@subscription_app.command("status")
def subscription_status(
    ctx: typer.Context,
    app_uuid: str | None = typer.Option(None, "--app", help="App UUID."),
) -> None:
    """Show the current and pending subscription."""
    app_ctx: AppContext = ctx.obj
    client = app_ctx.api_client()
    resolved = resolve_app_uuid(app_ctx, app_uuid)
    payload = billing_api.get_subscription(client, resolved)
    print_data(_unwrap(payload), app_ctx.output)


@subscription_app.command("schedule")
def subscription_schedule(
    ctx: typer.Context,
    plan: str = typer.Option(..., "--plan", help="Target pricing plan UUID."),
    commitment: str | None = typer.Option(None, "--commitment", help="MONTHLY or ANNUAL."),
    app_uuid: str | None = typer.Option(None, "--app", help="App UUID."),
) -> None:
    """Schedule a plan or commitment change for the next billing boundary."""
    app_ctx: AppContext = ctx.obj
    client = app_ctx.api_client()
    resolved = resolve_app_uuid(app_ctx, app_uuid)
    payload = billing_api.schedule_subscription_change(
        client,
        resolved,
        plan_uuid=plan,
        commitment=commitment,
    )
    print_data(_unwrap(payload), app_ctx.output)


@subscription_app.command("cancel-pending")
def subscription_cancel_pending(
    ctx: typer.Context,
    app_uuid: str | None = typer.Option(None, "--app", help="App UUID."),
) -> None:
    """Cancel a scheduled subscription change."""
    app_ctx: AppContext = ctx.obj
    client = app_ctx.api_client()
    resolved = resolve_app_uuid(app_ctx, app_uuid)
    payload = billing_api.cancel_pending_subscription(client, resolved)
    print_data(_unwrap(payload), app_ctx.output)
