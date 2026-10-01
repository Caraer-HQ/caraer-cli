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


@pytest.mark.parametrize("args", [
    ["--yes", "--version", "1.0.0"],
    ["--dry-run"],
    ["--no-deploy", "--yes"],
])
def test_push_validates_before_upgrade_plan_or_remote_actions(tmp_path, args):
    root = tmp_path / "demo"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        sample_function=None,
    )
    # A real validation error rather than a mocked report.
    manifest = root / "src/app/app.caraer.yaml"
    manifest.write_text("name: demo\nlabel: Demo\nauthMethod: INVALID\n")
    with (
        patch("caraer_cli.commands.apps._maybe_upgrade_layout_on_push") as upgrade,
        patch("caraer_cli.commands.apps._confirm_push_plan") as plan,
        patch("caraer_cli.commands.apps._run_push") as push,
        patch("caraer_cli.app_install.install_app_on_company") as install,
        patch.object(AppContext, "api_client") as client,
    ):
        result = _invoke_push(_app_ctx(company_uuid="company-1"), ["--file", str(root), *args])
    assert result.exit_code == 1, result.output
    assert "authMethod" in result.output
    assert "Push cancelled" in result.output
    assert "✓ Validating local app" not in result.output
    upgrade.assert_not_called()
    plan.assert_not_called()
    push.assert_not_called()
    install.assert_not_called()
    client.assert_not_called()


def test_push_validates_before_a_successful_dry_run(tmp_path):
    from caraer_cli.project.validate_app import ValidationIssue, ValidationReport

    root = tmp_path / "demo"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        sample_function=None,
    )
    stages = []

    def validate(_root):
        stages.append("validate")
        return ValidationReport(
            ok=True, root=str(_root),
            issues=[ValidationIssue("warning", "src/app/app.caraer.yaml", "Review optional branding")],
        )

    def plan(*_args, **_kwargs):
        stages.append("plan")
        return False

    with (
        patch("caraer_cli.project.validate_app.validate_local_app", side_effect=validate),
        patch("caraer_cli.commands.apps._confirm_push_plan", side_effect=plan),
        patch("caraer_cli.commands.apps._run_push") as push,
    ):
        result = _invoke_push(_app_ctx(company_uuid=None), ["--file", str(root), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert stages == ["validate", "plan"]
    assert "Review optional branding" in result.output
    assert "✓ Validating local app" in result.output
    push.assert_not_called()
