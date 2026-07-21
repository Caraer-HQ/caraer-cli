from __future__ import annotations

from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from caraer_cli.commands import profile as profile_commands
from caraer_cli.context import AppContext
from caraer_cli.state.config import CliConfig, ProfileConfig, profile_as_dict, save_config


runner = CliRunner()


def _app_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppContext:
    monkeypatch.setattr(
        "caraer_cli.state.config.config_dir",
        lambda: tmp_path / "config",
    )
    cfg = CliConfig(
        active_profile="dev",
        profiles={
            "dev": ProfileConfig(base_url="http://localhost:8080", output="table"),
            "staging": ProfileConfig(
                base_url="https://staging.caraer.com",
                company_uuid="company-1",
                app_uuid="app-1",
            ),
        },
    )
    save_config(cfg)
    return AppContext(
        config=cfg,
        profile_name="dev",
        profile=cfg.profiles["dev"],
        token=None,
        output="json",
        debug=False,
    )


def _invoke(app_ctx: AppContext, args: list[str]):
    app = typer.Typer()
    app.add_typer(profile_commands.app, name="profile")

    @app.callback()
    def _root(ctx: typer.Context) -> None:
        ctx.obj = app_ctx

    return runner.invoke(app, args)


def test_profile_as_dict() -> None:
    profile = ProfileConfig(base_url="http://localhost:8080", verify_ssl=False)
    assert profile_as_dict(profile)["verify_ssl"] is False


def test_list_and_use_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app_ctx = _app_ctx(tmp_path, monkeypatch)

    result = _invoke(app_ctx, ["profile", "list"])
    assert result.exit_code == 0
    assert '"name": "dev"' in result.stdout
    assert '"active": true' in result.stdout

    result = _invoke(app_ctx, ["profile", "use", "staging"])
    assert result.exit_code == 0
    assert app_ctx.config.active_profile == "staging"


def test_set_and_show_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app_ctx = _app_ctx(tmp_path, monkeypatch)

    result = _invoke(
        app_ctx,
        [
            "profile",
            "set",
            "staging",
            "--base-url",
            "https://staging.example.com",
            "--output",
            "yaml",
            "--clear-app",
            "--clear-company",
        ],
    )
    assert result.exit_code == 0
    profile = app_ctx.config.profiles["staging"]
    assert profile.base_url == "https://staging.example.com"
    assert profile.output == "yaml"
    assert profile.app_uuid is None
    assert profile.company_uuid is None

    result = _invoke(app_ctx, ["profile", "show", "staging"])
    assert result.exit_code == 0
    assert "https://staging.example.com" in result.stdout


def test_create_and_delete_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app_ctx = _app_ctx(tmp_path, monkeypatch)

    result = _invoke(
        app_ctx,
        [
            "profile",
            "create",
            "qa",
            "--from",
            "staging",
            "--base-url",
            "https://qa.example.com",
            "--use",
        ],
    )
    assert result.exit_code == 0
    assert "qa" in app_ctx.config.profiles
    assert app_ctx.config.active_profile == "qa"
    assert app_ctx.config.profiles["qa"].base_url == "https://qa.example.com"
    assert app_ctx.config.profiles["qa"].company_uuid == "company-1"

    result = _invoke(app_ctx, ["profile", "delete", "qa", "--force"])
    assert result.exit_code == 0
    assert "qa" not in app_ctx.config.profiles
    assert app_ctx.config.active_profile in app_ctx.config.profiles


def test_delete_active_without_force_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_ctx = _app_ctx(tmp_path, monkeypatch)
    result = _invoke(app_ctx, ["profile", "delete", "dev"])
    assert result.exit_code != 0
    assert "dev" in app_ctx.config.profiles
