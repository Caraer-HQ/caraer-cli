from __future__ import annotations

import sys

import typer
from questionary import Choice

from caraer_cli.api import auth as auth_api
from caraer_cli.completion_callbacks import complete_company
from caraer_cli.context import AppContext
from caraer_cli.formatters.output import print_data, print_success
from caraer_cli.state.config import save_config

app = typer.Typer(help="Company context commands.", no_args_is_help=True)


def _company_rows(payload: object) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not isinstance(payload, list):
        return rows
    for company in payload:
        if not isinstance(company, dict):
            continue
        uuid = str(company.get("uuid") or "").strip()
        if not uuid:
            continue
        name = str(company.get("name") or "").strip() or uuid
        rows.append({"name": name, "uuid": uuid})
    return rows


def _pick_company_uuid(rows: list[dict[str, str]], current: str | None) -> str:
    from caraer_cli.wizard.prompts import ask_select

    if not rows:
        raise typer.BadParameter(
            "No companies available. Create or join a company, then try again."
        )
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise typer.BadParameter(
            "Missing company UUID. Pass it as an argument or run in a terminal."
        )
    choices = [
        Choice(title=f"{row['name']}  ({row['uuid']})", value=row["uuid"])
        for row in rows
    ]
    default = current if current in {row["uuid"] for row in rows} else rows[0]["uuid"]
    return ask_select("Company", choices, default=default)


@app.command("list")
def list_companies(ctx: typer.Context) -> None:
    """List companies available to the authenticated user."""
    app_ctx: AppContext = ctx.obj
    client = app_ctx.api_client()
    response = auth_api.companies(client)
    print_data(_company_rows(response.get("data")), app_ctx.output)


@app.command("select")
def select_company(
    ctx: typer.Context,
    company_uuid: str | None = typer.Argument(
        None,
        help="Company UUID to use for API calls. Shown as a list if omitted.",
        autocompletion=complete_company,
    ),
) -> None:
    """Select a company for the active profile."""
    app_ctx: AppContext = ctx.obj
    if company_uuid is None or not str(company_uuid).strip():
        response = auth_api.companies(app_ctx.api_client())
        company_uuid = _pick_company_uuid(
            _company_rows(response.get("data")),
            app_ctx.profile.company_uuid,
        )
    else:
        company_uuid = str(company_uuid).strip()
    cfg = app_ctx.config
    profile = cfg.profiles[app_ctx.profile_name]
    profile.company_uuid = company_uuid
    profile.sandbox_uuid = None  # sandbox is always scoped to its owner company
    save_config(cfg)
    print_success(f"Selected company '{company_uuid}' for profile '{app_ctx.profile_name}'.")


@app.command("clear")
def clear_company(ctx: typer.Context) -> None:
    """Remove the selected company from the active profile."""
    app_ctx: AppContext = ctx.obj
    cfg = app_ctx.config
    profile = cfg.profiles[app_ctx.profile_name]
    profile.company_uuid = None
    profile.sandbox_uuid = None
    save_config(cfg)
    print_success(f"Cleared company for profile '{app_ctx.profile_name}'.")
