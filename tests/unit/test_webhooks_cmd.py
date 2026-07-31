from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import typer

from caraer_cli.commands.webhooks import resolve_webhook_uuid, webhook_choice_title


def test_webhook_choice_title_includes_key_fields() -> None:
    title = webhook_choice_title(
        {
            "uuid": "11111111-2222-3333-4444-555555555555",
            "topic": "record.created",
            "deliveryMode": "SERVERLESS",
            "enabled": True,
            "description": "Notify on create",
            "serverlessFunction": {"name": "on-create"},
        }
    )
    assert "record.created" in title
    assert "SERVERLESS" in title
    assert "enabled" in title
    assert "on-create" in title
    assert "Notify on create" in title
    assert "11111111-2222-3333-4444-555555555555" in title


def test_webhook_choice_title_uses_url_and_disabled() -> None:
    title = webhook_choice_title(
        {
            "uuid": "abcd",
            "topic": "record.updated",
            "deliveryMode": "HTTP",
            "enabled": False,
            "url": "https://example.com/hook",
        }
    )
    assert "disabled" in title
    assert "https://example.com/hook" in title
    assert "abcd" in title


def test_webhook_choice_title_truncates_long_description() -> None:
    title = webhook_choice_title(
        {
            "uuid": "u1",
            "topic": "record.deleted",
            "description": "x" * 80,
        }
    )
    assert "..." in title
    assert len(title) < 160


def test_resolve_webhook_uuid_returns_provided_value() -> None:
    client = MagicMock()
    assert (
        resolve_webhook_uuid(client, "app-uuid", "  webhook-uuid  ") == "webhook-uuid"
    )
    client.request.assert_not_called()


def test_resolve_webhook_uuid_fails_without_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("caraer_cli.commands.webhooks.sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("caraer_cli.commands.webhooks.sys.stdout.isatty", lambda: False)
    with pytest.raises(ValueError, match="webhook-uuid"):
        resolve_webhook_uuid(MagicMock(), "app-uuid", None)


def test_resolve_webhook_uuid_prompts_from_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("caraer_cli.commands.webhooks.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("caraer_cli.commands.webhooks.sys.stdout.isatty", lambda: True)

    rows = {
        "data": [
            {
                "uuid": "wh-1",
                "topic": "record.created",
                "deliveryMode": "SERVERLESS",
                "enabled": True,
            },
            {
                "uuid": "wh-2",
                "topic": "record.updated",
                "deliveryMode": "HTTP",
                "enabled": False,
            },
        ]
    }
    monkeypatch.setattr(
        "caraer_cli.commands.webhooks.webhook_api.list_webhooks",
        lambda client, app_uuid, page, limit: rows,
    )
    monkeypatch.setattr(
        "caraer_cli.wizard.prompts.ask_select",
        lambda message, choices, default=None: "wh-2",
    )

    selected = resolve_webhook_uuid(MagicMock(), "app-uuid", None)
    assert selected == "wh-2"


def test_resolve_webhook_uuid_errors_when_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("caraer_cli.commands.webhooks.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("caraer_cli.commands.webhooks.sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(
        "caraer_cli.commands.webhooks.webhook_api.list_webhooks",
        lambda client, app_uuid, page, limit: {"data": []},
    )
    with pytest.raises(ValueError, match="No webhooks found"):
        resolve_webhook_uuid(MagicMock(), "app-uuid", None)


def test_resolve_webhook_uuid_cancelled_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from caraer_cli.wizard.prompts import WizardCancelled

    monkeypatch.setattr("caraer_cli.commands.webhooks.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("caraer_cli.commands.webhooks.sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(
        "caraer_cli.commands.webhooks.webhook_api.list_webhooks",
        lambda client, app_uuid, page, limit: {
            "data": [{"uuid": "wh-1", "topic": "record.created"}]
        },
    )

    def _cancel(message, choices, default=None):
        raise WizardCancelled()

    monkeypatch.setattr("caraer_cli.wizard.prompts.ask_select", _cancel)

    with pytest.raises(typer.Exit) as exc:
        resolve_webhook_uuid(MagicMock(), "app-uuid", None)
    assert exc.value.exit_code == 1
