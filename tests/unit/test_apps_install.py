from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from caraer_cli.app_install import install_app_on_company, install_payload
from caraer_cli.commands import apps as apps_commands
from caraer_cli.commands.apps import build_public_app_placeholder
from caraer_cli.context import AppContext
from caraer_cli.project.scaffold import scaffold_app_project
from caraer_cli.state.config import CliConfig, ProfileConfig

runner = CliRunner()


def test_install_payload_omits_unset_keys() -> None:
    assert install_payload() == {}
    assert install_payload(settings={"inbox": "Support"}) == {
        "settings": [{"name": "inbox", "value": "Support"}]
    }
    assert install_payload(scopes=["tools.apps.read"]) == {
        "scopes": ["tools.apps.read"]
    }


def test_install_app_on_company_posts_install() -> None:
    client = MagicMock()
    with patch(
        "caraer_cli.app_install.apps_api.install_app",
        return_value={"data": {"uuid": "app-1", "installed": True}},
    ) as install:
        result = install_app_on_company(
            client, "app-1", settings={"name": "A"}, scopes=["s"]
        )
    install.assert_called_once_with(
        client,
        "app-1",
        {
            "settings": [{"name": "name", "value": "A"}],
            "scopes": ["s"],
        },
    )
    assert result["installed"] is True


def test_install_app_on_company_requires_uuid() -> None:
    with pytest.raises(ValueError, match="no remote UUID"):
        install_app_on_company(MagicMock(), "")


def _app_ctx(*, company_uuid: str | None, app_uuid: str | None = "app-1") -> AppContext:
    profile = ProfileConfig(
        base_url="http://localhost:8080",
        company_uuid=company_uuid,
        app_uuid=app_uuid,
        output="json",
    )
    cfg = CliConfig(active_profile="dev", profiles={"dev": profile})
    return AppContext(
        config=cfg,
        profile_name="dev",
        profile=profile,
        token="token",
        output="json",
        debug=False,
    )


def _invoke_push(app_ctx: AppContext, args: list[str]):
    app = typer.Typer()
    app.add_typer(apps_commands.app, name="apps")

    @app.callback()
    def _root(ctx: typer.Context) -> None:
        ctx.obj = app_ctx

    return runner.invoke(app, ["apps", "push", *args])


def test_push_without_company_skips_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "demo"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        app_uuid="app-1",
        sample_function=None,
        force=True,
    )
    monkeypatch.chdir(root)
    with (
        patch("caraer_cli.commands.apps._confirm_push_plan", return_value=True),
        patch(
            "caraer_cli.commands.apps._run_push",
            return_value={"appUuid": "app-1"},
        ) as pushed,
        patch("caraer_cli.app_install.install_app_on_company") as install,
    ):
        result = _invoke_push(
            _app_ctx(company_uuid=None),
            ["--yes", "--version", "1.0.0", "--notes", "first"],
        )
    assert result.exit_code == 0, result.output
    assert pushed.call_args.kwargs["deploy"] is True
    assert pushed.call_args.kwargs["wait"] is False
    install.assert_not_called()
    assert "Skipped company install" in result.output


def test_push_installs_when_company_selected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "demo"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        app_uuid="app-1",
        sample_function=None,
        force=True,
    )
    monkeypatch.chdir(root)
    with (
        patch("caraer_cli.commands.apps._confirm_push_plan", return_value=True),
        patch(
            "caraer_cli.commands.apps._run_push",
            return_value={"appUuid": "app-1"},
        ) as pushed,
        patch(
            "caraer_cli.app_install.install_app_on_company",
            return_value={"uuid": "app-1", "installed": True},
        ) as install,
    ):
        result = _invoke_push(
            _app_ctx(company_uuid="company-1"),
            ["--yes", "--version", "1.0.0", "--notes", "first"],
        )
    assert result.exit_code == 0, result.output
    assert pushed.call_args.kwargs["deploy"] is True
    assert pushed.call_args.kwargs["wait"] is False
    install.assert_called_once()
    assert install.call_args.args[1] == "app-1"
    assert "Pushed and installed" in result.output


def test_push_wait_and_no_deploy_pass_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "demo"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        app_uuid="app-1",
        sample_function=None,
        force=True,
    )
    monkeypatch.chdir(root)
    with (
        patch("caraer_cli.commands.apps._confirm_push_plan", return_value=True),
        patch(
            "caraer_cli.commands.apps._run_push",
            return_value={"appUuid": "app-1"},
        ) as pushed,
        patch("caraer_cli.app_install.install_app_on_company", return_value={}),
    ):
        result = _invoke_push(
            _app_ctx(company_uuid="company-1"),
            ["--wait", "--no-deploy", "--yes"],
        )
    assert result.exit_code == 0, result.output
    assert pushed.call_args.kwargs["deploy"] is False
    assert pushed.call_args.kwargs["wait"] is True
