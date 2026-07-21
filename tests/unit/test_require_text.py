from __future__ import annotations

import pytest

from caraer_cli.wizard.prompts import require_text


def test_require_text_returns_provided_value() -> None:
    assert require_text("  hello-world  ", "Function name") == "hello-world"


def test_require_text_fails_clearly_without_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("caraer_cli.wizard.prompts.sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("caraer_cli.wizard.prompts.sys.stdout.isatty", lambda: False)
    with pytest.raises(ValueError, match="Missing required value: name"):
        require_text(None, "Function name", flag="name")


def test_require_text_prompts_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("caraer_cli.wizard.prompts.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("caraer_cli.wizard.prompts.sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(
        "caraer_cli.wizard.prompts.ask_text",
        lambda message, default="", required=False: "prompted-value",
    )
    assert require_text(None, "Function name") == "prompted-value"
