from __future__ import annotations

import getpass
import time
import webbrowser

import typer

from caraer_cli.api import auth as auth_api
from caraer_cli.context import AppContext
from caraer_cli.errors import ApiError, AuthError
from caraer_cli.formatters.output import print_data, print_success, print_warning
from caraer_cli.state import session as session_store
from caraer_cli.state.config import save_config

app = typer.Typer(help="Authentication commands.", no_args_is_help=True)


def _store_tokens(profile: str, data: dict) -> str:
    """Extract and persist access (+ optional refresh) token from an auth payload."""
    token = None
    refresh_token = data.get("refreshToken")
    token_obj = data.get("token")
    if isinstance(token_obj, dict):
        token = token_obj.get("token")
    if not token:
        token = data.get("accessToken")
    if not token:
        raise typer.BadParameter("Login succeeded but no token was returned.")
    session_store.set_session_token(
        profile,
        str(token),
        refresh_token=str(refresh_token) if refresh_token else None,
    )
    return str(token)


@app.command("login")
def login(
    ctx: typer.Context,
    email: str | None = typer.Option(
        None,
        "--email",
        help="Account email (password login). Omit for device-code browser login.",
    ),
    password: str = typer.Option(
        None,
        "--password",
        prompt=False,
        hide_input=True,
        help="Password (prompted securely if --email is set and password omitted).",
    ),
    device: bool = typer.Option(
        False,
        "--device",
        help="Force device-code login (default when --email is omitted).",
    ),
) -> None:
    """Log in and store a session token for the active profile.

    Defaults to device-code / browser login. Pass --email for password login (CI).
    """
    app_ctx: AppContext = ctx.obj
    client = app_ctx.api_client()

    use_device = device or not email
    if use_device and email:
        print_warning("Ignoring --email/--password; using device-code login.")

    if use_device:
        try:
            start = auth_api.device_start(client).get("data") or {}
        except ApiError as exc:
            if email:
                print_warning(
                    f"Device login unavailable ({exc}). Falling back to password login."
                )
                use_device = False
            else:
                raise typer.BadParameter(
                    "Device login is unavailable on this backend. "
                    "Use 'caraer auth login --email you@example.com'."
                ) from exc
        else:
            device_code = str(start.get("deviceCode") or "")
            user_code = str(start.get("userCode") or "")
            verification_uri = str(
                start.get("verificationUriComplete")
                or start.get("verificationUri")
                or ""
            )
            interval = float(start.get("interval") or 5)
            expires_in = float(start.get("expiresIn") or 600)
            if not device_code or not user_code:
                raise typer.BadParameter("Device start response missing codes.")
            print_success(f"Device code: {user_code}")
            if verification_uri:
                print_success(f"Open: {verification_uri}")
                try:
                    webbrowser.open(verification_uri)
                except Exception:  # noqa: BLE001
                    pass
            print_success("Sign in and choose the default CLI company in the browser…")
            deadline = time.monotonic() + expires_in
            while time.monotonic() < deadline:
                time.sleep(max(1.0, interval))
                poll = auth_api.device_poll(client, device_code).get("data") or {}
                status = str(poll.get("status") or "").lower()
                if status == "approved":
                    _store_tokens(app_ctx.profile_name, poll)
                    _apply_login_company(app_ctx, poll)
                    print_success(f"Logged in for profile '{app_ctx.profile_name}'.")
                    _print_next_steps(app_ctx)
                    return
                if status in {"expired", "denied"}:
                    raise typer.BadParameter(f"Device login {status}.")
            raise typer.BadParameter("Device login timed out.")

    from caraer_cli.wizard.prompts import require_text

    email = require_text(email, "Email", flag="--email")
    resolved_password = password or getpass.getpass("Password: ")
    response = auth_api.login(client, email, resolved_password)
    data = response.get("data", {})
    _store_tokens(app_ctx.profile_name, data if isinstance(data, dict) else {})
    print_success(f"Logged in for profile '{app_ctx.profile_name}'.")
    _print_next_steps(app_ctx)


def _apply_login_company(app_ctx: AppContext, payload: dict) -> None:
    company_uuid = str(payload.get("companyUuid") or "").strip()
    if not company_uuid:
        return
    profile = app_ctx.config.profiles[app_ctx.profile_name]
    if profile.company_uuid != company_uuid:
        profile.sandbox_uuid = None  # sandboxes belong to the previous company
    profile.company_uuid = company_uuid
    save_config(app_ctx.config)


def _print_next_steps(app_ctx: AppContext) -> None:
    if app_ctx.profile.company_uuid:
        print_success(
            f"Default company for profile '{app_ctx.profile_name}': "
            f"{app_ctx.profile.company_uuid}. "
            "Run 'caraer company select' to change it."
        )
    else:
        print_success("Next: run 'caraer company select' and use the arrow keys to choose a company.")


@app.command("logout")
def logout(ctx: typer.Context) -> None:
    """Log out and clear the stored session token for the active profile."""
    app_ctx: AppContext = ctx.obj
    client = app_ctx.api_client()
    try:
        auth_api.logout(client)
    except AuthError:
        pass
    session_store.clear_session_token(app_ctx.profile_name)
    print_success(f"Logged out profile '{app_ctx.profile_name}'.")


@app.command("me")
def me(ctx: typer.Context) -> None:
    """Show the currently authenticated user."""
    app_ctx: AppContext = ctx.obj
    client = app_ctx.api_client()
    response = auth_api.me(client)
    print_data(response.get("data"), app_ctx.output)


@app.command("refresh")
def refresh_token(ctx: typer.Context) -> None:
    """Refresh the access token using the stored refresh token."""
    app_ctx: AppContext = ctx.obj
    refresh = session_store.get_refresh_token(app_ctx.profile_name)
    if not refresh:
        raise typer.BadParameter(
            "No refresh token stored. Run 'caraer auth login' (device flow) first."
        )
    client = app_ctx.api_client()
    data = auth_api.refresh(client, refresh).get("data") or {}
    _store_tokens(app_ctx.profile_name, data if isinstance(data, dict) else {})
    print_success(f"Refreshed session for profile '{app_ctx.profile_name}'.")
