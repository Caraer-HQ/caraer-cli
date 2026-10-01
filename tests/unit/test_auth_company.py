from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from caraer_cli.commands import auth
from caraer_cli.context import AppContext
from caraer_cli.state.config import CliConfig, ProfileConfig, load_config


def app_context():
    profile = ProfileConfig(
        base_url="https://api.caraer.com", company_uuid="company-old", sandbox_uuid="sandbox-old",
    )
    config = CliConfig(active_profile="prod", profiles={"prod": profile})
    return AppContext(config, "prod", profile, None, "table", False)


@pytest.mark.parametrize("selected,expected_sandbox", [
    ("company-new", None),
    ("company-old", "sandbox-old"),
])
def test_browser_company_selection_is_persisted(tmp_path, selected, expected_sandbox):
    ctx = app_context()
    with patch("caraer_cli.state.config.config_path", return_value=tmp_path / "config.toml"):
        auth._apply_login_company(ctx, {"companyUuid": selected})
        saved = load_config().profiles["prod"]
    assert saved.company_uuid == selected
    assert saved.sandbox_uuid == expected_sandbox
    assert ctx.api_client().context.company_uuid == selected


def test_older_backend_without_company_preserves_existing_selection():
    ctx = app_context()
    with patch("caraer_cli.commands.auth.save_config") as save:
        auth._apply_login_company(ctx, {"status": "approved"})
    assert ctx.profile.company_uuid == "company-old"
    assert ctx.profile.sandbox_uuid == "sandbox-old"
    save.assert_not_called()


def test_browser_login_saves_selected_company_as_default(tmp_path):
    ctx = app_context()
    app = typer.Typer()
    app.add_typer(auth.app, name="auth")

    @app.callback()
    def root(context: typer.Context):
        context.obj = ctx

    with (
        patch("caraer_cli.state.config.config_path", return_value=tmp_path / "config.toml"),
        patch.object(AppContext, "api_client"),
        patch("caraer_cli.commands.auth.auth_api.device_start", return_value={"data": {
            "deviceCode": "secret-device-code", "userCode": "ABCD-EFGH",
            "verificationUriComplete": "https://example.com/approve?userCode=ABCD-EFGH",
        }}),
        patch("caraer_cli.commands.auth.auth_api.device_poll", side_effect=[
            {"data": {"status": "pending"}},
            {"data": {"status": "approved", "companyUuid": "company-new", "accessToken": "secret-token"}},
        ]),
        patch("caraer_cli.commands.auth.session_store.set_session_token") as store,
        patch("caraer_cli.commands.auth.webbrowser.open") as browser,
        patch("caraer_cli.commands.auth.time.sleep"),
    ):
        result = CliRunner().invoke(app, ["auth", "login"])
        saved = load_config().profiles["prod"]
    assert result.exit_code == 0, result.output
    assert saved.company_uuid == "company-new"
    assert saved.sandbox_uuid is None
    store.assert_called_once_with("prod", "secret-token", refresh_token=None)
    browser.assert_called_once()
    assert "Default company for profile 'prod': company-new" in result.output
    assert "secret-token" not in result.output
