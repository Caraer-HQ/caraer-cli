from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from caraer_cli.main import app
from caraer_cli.project.scaffold import scaffold_app_project
from caraer_cli.project.schema import load_workspace
from caraer_cli.project.sync import scaffold_function
from caraer_cli.wizard.marketplace import (
    DEFAULT_SCHEDULE_CRON,
    prompt_cron_expression,
    prompt_schedule,
    validate_cron_expression,
)

runner = CliRunner()


def test_validate_cron_expression_accepts_5_and_6_field() -> None:
    assert validate_cron_expression("0 9 * * 1-5") == "0 9 * * 1-5"
    assert validate_cron_expression("  0 0 9 * * 1-5  ") == "0 0 9 * * 1-5"


def test_validate_cron_expression_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="does not look like"):
        validate_cron_expression("not-a-cron")
    with pytest.raises(ValueError, match="required"):
        validate_cron_expression("   ")


def test_prompt_schedule_noninteractive_uses_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("caraer_cli.wizard.marketplace._is_tty", lambda: False)
    result = prompt_schedule(
        name="renew-watch",
        function_name="my-action",
    )
    assert result["name"] == "renew-watch"
    assert result["function_name"] == "my-action"
    assert result["schedule"] == DEFAULT_SCHEDULE_CRON
    assert result["enabled"] is True
    assert "description" not in result


def test_prompt_schedule_noninteractive_requires_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("caraer_cli.wizard.marketplace._is_tty", lambda: False)
    with pytest.raises(ValueError, match="name"):
        prompt_schedule(function_name="my-action", cron="0 0 * * * *")


def test_prompt_schedule_interactive_cron_presets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("caraer_cli.wizard.marketplace._is_tty", lambda: True)
    monkeypatch.setattr(
        "caraer_cli.wizard.marketplace.ask_select",
        lambda message, choices, default=None: "0 0 9 * * 1-5",
    )
    monkeypatch.setattr(
        "caraer_cli.wizard.marketplace.ask_text",
        lambda message, default="", required=False: default or "ignored",
    )
    monkeypatch.setattr(
        "caraer_cli.wizard.marketplace.ask_confirm",
        lambda message, default=False: False,
    )
    result = prompt_schedule(
        name="weekday-sync",
        function_name="sync",
        function_choices=["sync", "other"],
    )
    assert result["schedule"] == "0 0 9 * * 1-5"
    assert result["enabled"] is False


def test_prompt_schedule_interactive_picks_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("caraer_cli.wizard.marketplace._is_tty", lambda: True)

    def fake_select(message, choices, default=None):
        if "Function" in message:
            return "my-action"
        return "0 0 * * * *"

    monkeypatch.setattr(
        "caraer_cli.wizard.marketplace.ask_select", fake_select
    )
    monkeypatch.setattr(
        "caraer_cli.wizard.marketplace.ask_text",
        lambda message, default="", required=False: "",
    )
    monkeypatch.setattr(
        "caraer_cli.wizard.marketplace.ask_confirm",
        lambda message, default=False: True,
    )
    result = prompt_schedule(
        name="tick",
        function_choices=["my-action", "other"],
    )
    assert result["function_name"] == "my-action"
    assert result["schedule"] == "0 0 * * * *"


def test_prompt_cron_expression_custom_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "caraer_cli.wizard.marketplace.ask_select",
        lambda message, choices, default=None: "",
    )
    monkeypatch.setattr(
        "caraer_cli.wizard.marketplace.ask_text",
        lambda message, default="", required=False: "0 0 */12 * * *",
    )
    assert prompt_cron_expression() == "0 0 */12 * * *"


def _scaffold_with_function(tmp_path: Path) -> Path:
    result = scaffold_app_project(
        tmp_path / "demo",
        app_payload={"name": "demo", "label": "Demo", "description": "Demo"},
        sample_function=None,
    )
    root = result["root"]
    scaffold_function(root, load_workspace(root), "my-action", "nodejs22")
    return root


def test_add_schedule_cli_noninteractive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _scaffold_with_function(tmp_path)
    monkeypatch.setattr("caraer_cli.wizard.marketplace._is_tty", lambda: False)
    monkeypatch.setattr(
        "caraer_cli.app_sync.resolve_app_root",
        lambda **_kwargs: root,
    )
    invoke = runner.invoke(
        app,
        [
            "apps",
            "add",
            "schedule",
            "renew-watch",
            "--function",
            "my-action",
            "--cron",
            "0 0 9 * * 1-5",
            "--description",
            "Weekday renew",
            "--disabled",
        ],
    )
    assert invoke.exit_code == 0, invoke.stdout + str(invoke.exception)
    path = root / "src" / "app" / "schedules" / "renew-watch.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["name"] == "renew_watch"
    assert payload["schedule"] == "0 0 9 * * 1-5"
    assert payload["enabled"] is False
    assert payload["description"] == "Weekday renew"
    assert payload["serverlessFunction"]["name"] == "my-action"


def test_add_schedule_cli_default_cron_without_tty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _scaffold_with_function(tmp_path)
    monkeypatch.setattr("caraer_cli.wizard.marketplace._is_tty", lambda: False)
    monkeypatch.setattr(
        "caraer_cli.app_sync.resolve_app_root",
        lambda **_kwargs: root,
    )
    invoke = runner.invoke(
        app,
        ["apps", "add", "schedule", "heartbeat", "--function", "my-action"],
    )
    assert invoke.exit_code == 0, invoke.stdout + str(invoke.exception)
    payload = json.loads(
        (root / "src" / "app" / "schedules" / "heartbeat.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["schedule"] == DEFAULT_SCHEDULE_CRON
