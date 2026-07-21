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
    name: str | None = typer.Option(None, "--name", help="Sandbox name (slug). Prompted if omitted."),
    label: str = typer.Option("", "--label", help="Display label (defaults to --name)."),
) -> None:
    """Clone the selected company's Neo4j database into a developer sandbox."""
    from caraer_cli.wizard.prompts import require_text

    app_ctx: AppContext = ctx.obj
    if not app_ctx.profile.company_uuid:
        raise ValueError("Select a company first with 'caraer company select <uuid>'.")
    name = require_text(name, "Sandbox name", flag="--name")
    response = sandboxes_api.create_sandbox(
        app_ctx.api_client(),
        {"name": name, "label": label or name},
    )
    data = response.get("data") or {}
    print_success(
        "Created sandbox DB clone for the selected company. "
        "Activate with 'caraer sandbox use <sandbox-uuid>' "
        "(sends X-Caraer-Sandbox-Uuid; company identity stays the owner)."
    )
    print_data(data, app_ctx.output)


@app.command("list")
def list_sandboxes(ctx: typer.Context) -> None:
    """List sandboxes for the owner company (ignores active sandbox override)."""
    app_ctx: AppContext = ctx.obj
    if not app_ctx.profile.company_uuid:
        raise ValueError("Select a company first with 'caraer company select <uuid>'.")
    response = sandboxes_api.list_sandboxes(app_ctx.api_client())
    print_data(response.get("data"), app_ctx.output)


@app.command("use")
def use_sandbox(
    ctx: typer.Context,
    sandbox_uuid: str | None = typer.Argument(
        None,
        help="Sandbox UUID (DeveloperSandbox uuid). Prompted if omitted.",
    ),
) -> None:
    """Activate a sandbox via X-Caraer-Sandbox-Uuid (overrides Neo4j databaseid only)."""
    from caraer_cli.wizard.prompts import require_text

    app_ctx: AppContext = ctx.obj
    if not app_ctx.profile.company_uuid:
        raise ValueError("Select the owner company first with 'caraer company select <uuid>'.")
    sandbox_uuid = require_text(sandbox_uuid, "Sandbox UUID", flag="sandbox-uuid")
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
        f"(company {profile.company_uuid}, db override). "
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
