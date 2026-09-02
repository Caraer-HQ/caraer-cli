"""Apps CLI regrouping: nested groups + hidden deprecated aliases."""

from __future__ import annotations

from typer.main import get_command
from typer.testing import CliRunner

from caraer_cli.main import app as typer_app

runner = CliRunner()


def _apps_command():
    return get_command(typer_app).commands["apps"]


def test_visible_apps_groups_and_golden_path_leaves() -> None:
    apps = _apps_command()
    visible = {name for name, cmd in apps.commands.items() if not getattr(cmd, "hidden", False)}
    assert {
        "list",
        "select",
        "clear",
        "current",
        "get",
        "init",
        "wizard",
        "pull",
        "push",
        "validate",
        "status",
        "add",
        "local",
        "release",
        "state",
        "secrets",
        "jobs",
        "connections",
    } <= visible
    # Flat legacy leaves must stay hidden, not disappear from the tree.
    assert getattr(apps.commands["add-function"], "hidden", False)
    assert getattr(apps.commands["dev"], "hidden", False)
    assert getattr(apps.commands["deploy"], "hidden", False)
    assert getattr(apps.commands["builds"], "hidden", False)
    assert "add-function" not in visible
    assert "dev" not in visible
    assert "deploy" not in visible
    assert "builds" not in visible


def test_nested_group_children() -> None:
    apps = _apps_command()
    assert set(apps.commands["add"].commands) == {
        "function",
        "options-function",
        "webhook",
        "schedule",
        "inbound",
        "setting",
        "lifecycle-hook",
    }
    assert "app-bar" not in apps.commands["add"].commands
    assert set(apps.commands["local"].commands) == {"dev", "test", "logs"}
    assert set(apps.commands["release"].commands) == {
        "deploy",
        "rollback",
        "deploys",
        "version",
        "builds",
    }
    assert set(apps.commands["release"].commands["builds"].commands) == {"list", "get"}


def test_help_lists_new_groups() -> None:
    for args in (
        ["apps", "--help"],
        ["apps", "add", "--help"],
        ["apps", "local", "--help"],
        ["apps", "release", "--help"],
        ["apps", "release", "builds", "--help"],
    ):
        result = runner.invoke(typer_app, list(args))
        assert result.exit_code == 0, result.output


def test_deprecated_aliases_warn_and_forward(monkeypatch) -> None:
    import caraer_cli.app_sync as app_sync
    import caraer_cli.wizard.public_app as public_app

    def boom(*_args, **_kwargs):
        raise RuntimeError("stop-after-warn")

    monkeypatch.setattr(app_sync, "resolve_app_root", boom)
    monkeypatch.setattr(public_app, "run_public_app_wizard", boom)

    cases = [
        (["apps", "add-function", "hello"], "caraer apps add function"),
        (["apps", "dev"], "caraer apps local dev"),
        (["apps", "deploy"], "caraer apps release deploy"),
        (["apps", "builds", "list"], "caraer apps release builds"),
        (["apps", "create-public-wizard"], "caraer apps wizard"),
    ]
    for args, new_path in cases:
        result = runner.invoke(typer_app, args)
        assert "deprecated" in result.output, result.output
        assert new_path in result.output, result.output


def test_new_paths_do_not_warn(monkeypatch) -> None:
    import caraer_cli.app_sync as app_sync

    def boom(*_args, **_kwargs):
        raise RuntimeError("stop-without-warn")

    monkeypatch.setattr(app_sync, "resolve_app_root", boom)

    result = runner.invoke(typer_app, ["apps", "add", "function", "hello"])
    assert "deprecated" not in result.output.lower()
    assert "stop-without-warn" in (result.output + str(result.exception))
