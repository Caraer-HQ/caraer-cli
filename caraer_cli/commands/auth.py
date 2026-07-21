from __future__ import annotations

import getpass

import typer

from caraer_cli.api import auth as auth_api
from caraer_cli.context import AppContext
from caraer_cli.formatters.output import print_data, print_success
from caraer_cli.state import session as session_store

app = typer.Typer(help="Authentication commands.", no_args_is_help=True)


@app.command("login")
def login(
    ctx: typer.Context,
    email: str = typer.Option(..., "--email", help="Account email address."),
    password: str = typer.Option(
        None,
        "--password",
        prompt=False,
        hide_input=True,
        help="Password (prompted securely if omitted).",
    ),
) -> None:
    """Log in and store a session token for the active profile."""
    app_ctx: AppContext = ctx.obj
    resolved_password = password or getpass.getpass("Password: ")
    client = app_ctx.api_client()
    response = auth_api.login(client, email, resolved_password)
    data = response.get("data", {})
    token = data.get("token", {}).get("token")
    if not token:
        raise typer.BadParameter("Login succeeded but no token was returned.")
    session_store.set_session_token(app_ctx.profile_name, token)
    print_success(f"Logged in for profile '{app_ctx.profile_name}'.")
    if app_ctx.profile.company_uuid:
        print_success(
            f"Profile company is '{app_ctx.profile.company_uuid}'. "
            "If API calls fail with Company not found, run 'caraer company clear' then 'caraer company list'."
        )
    else:
        print_success("Next: run 'caraer company list' and 'caraer company select <uuid>'.")


@app.command("logout")
def logout(ctx: typer.Context) -> None:
    """Log out and clear the stored session token for the active profile."""
    app_ctx: AppContext = ctx.obj
    client = app_ctx.api_client()
    auth_api.logout(client)
    session_store.clear_session_token(app_ctx.profile_name)
    print_success(f"Logged out profile '{app_ctx.profile_name}'.")


@app.command("me")
def me(ctx: typer.Context) -> None:
    """Show the currently authenticated user."""
    app_ctx: AppContext = ctx.obj
    client = app_ctx.api_client()
    response = auth_api.me(client)
    print_data(response.get("data"), app_ctx.output)
