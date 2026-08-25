from __future__ import annotations

import typer

from caraer_cli.api import apps as apps_api
from caraer_cli.context import AppContext
from caraer_cli.formatters.output import print_data, print_success
from caraer_cli.project.paths import find_project_root
from caraer_cli.project.schema import load_workspace
from caraer_cli.resolve import resolve_app_uuid
from caraer_cli.errors import CliError

app = typer.Typer(help="Publishing commands for app creators.", no_args_is_help=True)


def _reject_private_publish(app_ctx: AppContext, app_uuid: str) -> None:
    try:
        config = load_workspace(find_project_root())
        if config.privateApp:
            raise CliError("Private apps cannot be submitted to the marketplace.")
    except FileNotFoundError:
        pass
    response = apps_api.fetch_app(app_ctx.api_client(), app_uuid)
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    if apps_api.is_private_remote(data):
        raise CliError("Private apps cannot be submitted to the marketplace.")


@app.command("submit")
def submit(
    ctx: typer.Context,
    app_uuid: str | None = typer.Option(None, "--app", "--app-uuid", help="App UUID (defaults to selected app)."),
) -> None:
    """Submit the selected app for marketplace review."""
    app_ctx: AppContext = ctx.obj
    resolved = resolve_app_uuid(app_ctx, app_uuid)
    _reject_private_publish(app_ctx, resolved)
    response = apps_api.submit_for_review(app_ctx.api_client(), resolved)
    print_success("Submitted app for review.")
    print_data(response.get("data"), app_ctx.output)


@app.command("status")
def status(
    ctx: typer.Context,
    app_uuid: str | None = typer.Option(None, "--app", "--app-uuid", help="App UUID (defaults to selected app)."),
) -> None:
    """Show publish state and creator-visible feedback for the selected app."""
    app_ctx: AppContext = ctx.obj
    resolved = resolve_app_uuid(app_ctx, app_uuid)
    _reject_private_publish(app_ctx, resolved)
    response = apps_api.get_public_app(app_ctx.api_client(), resolved)
    data = response.get("data", {})
    publish_data = data.get("appPublish", {})
    if isinstance(publish_data, dict):
        # reviewerNotes are SUPER_ADMIN-only; drop defensively if ever present.
        publish_data = {k: v for k, v in publish_data.items() if k != "reviewerNotes"}
    print_data(publish_data, app_ctx.output)


@app.command("review")
def review(
    ctx: typer.Context,
    app_uuid: str | None = typer.Option(None, "--app", "--app-uuid", help="App UUID."),
    publish_state: str = typer.Option(
        ...,
        "--state",
        help="IN_REVIEW|APPROVED|PUBLISHED|REJECTED|CHANGES_REQUESTED|UNPUBLISHED",
    ),
    feedback: str | None = typer.Option(None, "--feedback", help="Creator-visible feedback."),
    reviewer_notes: str | None = typer.Option(
        None, "--notes", help="Internal reviewer notes (SUPER_ADMIN)."
    ),
) -> None:
    """Review a public app (SUPER_ADMIN / Caraer BV ops)."""
    app_ctx: AppContext = ctx.obj
    resolved = resolve_app_uuid(app_ctx, app_uuid)
    response = apps_api.review_public_app(
        app_ctx.api_client(),
        resolved,
        publish_state=publish_state,
        feedback=feedback,
        reviewer_notes=reviewer_notes,
    )
    print_success(f"Reviewed app → {publish_state}.")
    print_data(response.get("data"), app_ctx.output)


@app.command("queue")
def queue(
    ctx: typer.Context,
    states: str = typer.Option(
        "SUBMITTED,IN_REVIEW",
        "--states",
        help="Comma-separated publish states.",
    ),
    page: int = typer.Option(1, "--page"),
    limit: int = typer.Option(50, "--limit"),
) -> None:
    """List apps in the Caraer BV review queue (SUPER_ADMIN)."""
    app_ctx: AppContext = ctx.obj
    response = apps_api.review_queue(
        app_ctx.api_client(),
        states=states,
        page=page,
        limit=limit,
    )
    print_data(response.get("data"), app_ctx.output)
