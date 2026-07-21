from __future__ import annotations

import typer

from caraer_cli.api import auth as auth_api
from caraer_cli.completion_callbacks import complete_company
from caraer_cli.context import AppContext
from caraer_cli.formatters.output import print_data, print_success
from caraer_cli.state.config import save_config

app = typer.Typer(help="Company context commands.", no_args_is_help=True)


@app.command("list")
def list_companies(ctx: typer.Context) -> None:
    """List companies available to the authenticated user."""
    app_ctx: AppContext = ctx.obj
    client = app_ctx.api_client()
    response = auth_api.companies(client)
    companies = response.get("data")
    if isinstance(companies, list):
        minimal = []
        for company in companies:
            if not isinstance(company, dict):
                continue
            minimal.append(
                {
                    "name": company.get("name"),
                    "uuid": company.get("uuid"),
                }
            )
        print_data(minimal, app_ctx.output)
        return
    print_data([], app_ctx.output)


@app.command("select")
def select_company(
    ctx: typer.Context,
    company_uuid: str = typer.Argument(
        ...,
        help="Company UUID to use for API calls.",
        autocompletion=complete_company,
    ),
) -> None:
    """Select a company for the active profile."""
    app_ctx: AppContext = ctx.obj
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
