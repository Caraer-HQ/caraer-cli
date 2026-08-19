from __future__ import annotations

import pytest
import typer
from typer.testing import CliRunner

from caraer_cli.commands import billing
from caraer_cli.context import AppContext
from caraer_cli.state.config import CliConfig, ProfileConfig


runner = CliRunner()


def _app_ctx() -> AppContext:
    profile = ProfileConfig(
        base_url="http://localhost:8080",
        output="json",
        app_uuid="app-1",
        company_uuid="company-1",
    )
    return AppContext(
        config=CliConfig(active_profile="dev", profiles={"dev": profile}),
        profile_name="dev",
        profile=profile,
        token="token",
        output="json",
        debug=False,
    )


def _invoke(app_ctx: AppContext, args: list[str]):
    app = typer.Typer()
    app.add_typer(billing.app, name="billing")

    @app.callback()
    def _root(ctx: typer.Context) -> None:
        ctx.obj = app_ctx

    return runner.invoke(app, args)


def test_billing_command_group_exists() -> None:
    assert billing.app is not None
    assert billing.subscription_app is not None
    assert billing.meter_app is not None


def test_billing_status_default_uses_installation_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(AppContext, "api_client", lambda self: object())
    monkeypatch.setattr("caraer_cli.commands.billing.print_data", lambda *a, **k: None)
    monkeypatch.setattr(
        "caraer_cli.commands.billing.billing_api.get_installation_billing_status",
        lambda client, uuid: calls.append(("installation", uuid)) or {"data": {}},
    )
    monkeypatch.setattr(
        "caraer_cli.commands.billing.billing_api.get_app_billing_status",
        lambda client, uuid: calls.append(("app", uuid)) or {"data": {}},
    )
    monkeypatch.setattr(
        "caraer_cli.commands.billing.billing_api.get_platform_billing_status",
        lambda client: calls.append(("platform", "")) or {"data": {}},
    )

    result = _invoke(_app_ctx(), ["billing", "status"])
    assert result.exit_code == 0, result.output
    assert calls == [("installation", "app-1")]


def test_billing_status_app_wide_uses_creator_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(AppContext, "api_client", lambda self: object())
    monkeypatch.setattr("caraer_cli.commands.billing.print_data", lambda *a, **k: None)
    monkeypatch.setattr(
        "caraer_cli.commands.billing.billing_api.get_installation_billing_status",
        lambda client, uuid: calls.append(("installation", uuid)) or {"data": {}},
    )
    monkeypatch.setattr(
        "caraer_cli.commands.billing.billing_api.get_app_billing_status",
        lambda client, uuid: calls.append(("app", uuid)) or {"data": {}},
    )
    monkeypatch.setattr(
        "caraer_cli.commands.billing.billing_api.get_platform_billing_status",
        lambda client: calls.append(("platform", "")) or {"data": {}},
    )

    result = _invoke(_app_ctx(), ["billing", "status", "--app-wide"])
    assert result.exit_code == 0, result.output
    assert calls == [("app", "app-1")]


def test_billing_status_all_uses_platform_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(AppContext, "api_client", lambda self: object())
    monkeypatch.setattr("caraer_cli.commands.billing.print_data", lambda *a, **k: None)
    monkeypatch.setattr(
        "caraer_cli.commands.billing.billing_api.get_installation_billing_status",
        lambda client, uuid: calls.append(("installation", uuid)) or {"data": {}},
    )
    monkeypatch.setattr(
        "caraer_cli.commands.billing.billing_api.get_app_billing_status",
        lambda client, uuid: calls.append(("app", uuid)) or {"data": {}},
    )
    monkeypatch.setattr(
        "caraer_cli.commands.billing.billing_api.get_platform_billing_status",
        lambda client: calls.append(("platform", "")) or {"data": {}},
    )

    result = _invoke(_app_ctx(), ["billing", "status", "--all"])
    assert result.exit_code == 0, result.output
    assert calls == [("platform", "")]
