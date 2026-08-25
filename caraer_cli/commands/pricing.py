from __future__ import annotations

import typer

from caraer_cli.api import apps as apps_api
from caraer_cli.context import AppContext
from caraer_cli.formatters.output import print_data, print_success
from caraer_cli.utils import deep_merge, load_structured_file

app = typer.Typer(help="Pricing management commands.")


@app.command("get")
def get_pricing(ctx: typer.Context, app_uuid: str) -> None:
    app_ctx: AppContext = ctx.obj
    response = apps_api.get_public_app(app_ctx.api_client(), app_uuid)
    print_data(response.get("data", {}).get("pricingPlans", []), app_ctx.output)


@app.command("set")
def set_pricing(
    ctx: typer.Context,
    app_uuid: str,
    file: str = typer.Option(..., "--file", help="JSON/YAML object containing pricingPlans or full app payload."),
) -> None:
    app_ctx: AppContext = ctx.obj
    patch = load_structured_file(file)
    current = apps_api.get_public_app(app_ctx.api_client(), app_uuid).get("data", {})

    if "pricingPlans" in patch:
        merged = deep_merge(current, {"pricingPlans": patch["pricingPlans"]})
    else:
        merged = deep_merge(current, patch)

    response = apps_api.update_public_app(app_ctx.api_client(), app_uuid, merged)
    print_success("Updated pricing plans.")
    print_data(response.get("data", {}).get("pricingPlans", []), app_ctx.output)
