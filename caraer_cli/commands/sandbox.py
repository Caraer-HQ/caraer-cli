from __future__ import annotations

import typer

from caraer_cli.api import sandboxes as sandboxes_api
from caraer_cli.context import AppContext
from caraer_cli.formatters.output import print_data, print_success
from caraer_cli.state.config import load_config, save_config

app = typer.Typer(help="Developer sandbox commands.", no_args_is_help=True)


@app.command("create")
def create_sandbox(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", help="Sandbox name (slug)."),
    label: str = typer.Option("", "--label", help="Display label (defaults to --name)."),
) -> None:
    """Clone the selected company's Neo4j database into a developer sandbox."""
    app_ctx: AppContext = ctx.obj
    if not app_ctx.profile.company_uuid:
        raise ValueError("Select a company first with 'caraer company select <uuid>'.")
    response = sandboxes_api.create_sandbox(
        app_ctx.api_client(),
        {"name": name, "label": label or name},
    )
    data = response.get("data") or {}
    print_success(
        "Created sandbox clone of the selected company. "
        "Activate with 'caraer sandbox use <sandbox-uuid>' "
        "(sends X-Caraer-Sandbox-Uuid; keeps X-Caraer-Company-Uuid as the owner)."
    )
    print_data(data, app_ctx.output)


@app.command("list")
def list_sandboxes(ctx: typer.Context) -> None:
    """List developer sandboxes owned by the selected company."""
    app_ctx: AppContext = ctx.obj
    response = sandboxes_api.list_sandboxes(app_ctx.api_client())
    print_data(response.get("data"), app_ctx.output)


@app.command("use")
def use_sandbox(
    ctx: typer.Context,
    sandbox_uuid: str = typer.Argument(..., help="Sandbox UUID (DeveloperSandbox uuid)."),
) -> None:
    """Activate a sandbox via X-Caraer-Sandbox-Uuid (owner company stays selected)."""
    app_ctx: AppContext = ctx.obj
    if not app_ctx.profile.company_uuid:
        raise ValueError("Select the owner company first with 'caraer company select <uuid>'.")
    response = sandboxes_api.get_sandbox(app_ctx.api_client(), sandbox_uuid)
    data = response.get("data") or {}
    owner = data.get("ownerCompanyUuid")
    if owner and str(owner) != str(app_ctx.profile.company_uuid):
        raise ValueError(
            f"Sandbox owner {owner} does not match selected company "
            f"{app_ctx.profile.company_uuid}. Select the owner company first."
        )
    cfg = load_config()
    profile = cfg.profiles[app_ctx.profile_name]
    profile.sandbox_uuid = str(data.get("uuid") or sandbox_uuid)
    save_config(cfg)
    print_success(
        f"Using sandbox {profile.sandbox_uuid} "
        f"(owner company {profile.company_uuid}). "
        "API calls will send X-Caraer-Sandbox-Uuid."
    )
    print_data(data, app_ctx.output)


@app.command("clear")
def clear_sandbox(ctx: typer.Context) -> None:
    """Stop sending X-Caraer-Sandbox-Uuid (return to the owner company database)."""
    app_ctx: AppContext = ctx.obj
    cfg = load_config()
    profile = cfg.profiles[app_ctx.profile_name]
    profile.sandbox_uuid = None
    save_config(cfg)
    print_success("Cleared sandbox override; requests use the selected company database.")
