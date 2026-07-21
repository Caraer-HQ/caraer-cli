"""Thin wrappers around questionary with cancel handling."""

from __future__ import annotations

import sys
from typing import Any, Sequence

import questionary
import typer
from questionary import Choice, Style

PROMPT_STYLE = Style(
    [
        ("qmark", "fg:#E74363 bold"),
        ("question", "bold"),
        ("answer", "fg:#E74363"),
        ("pointer", "fg:#E74363 bold"),
        ("highlighted", "fg:#E74363 bold"),
        ("selected", "fg:#66bb6a"),
    ]
)


class WizardCancelled(typer.Exit):
    """Raised when the user cancels an interactive prompt."""

    def __init__(self) -> None:
        super().__init__(code=1)


def _or_cancel(value: Any) -> Any:
    if value is None:
        raise WizardCancelled()
    return value


def ask_text(message: str, *, default: str = "", required: bool = False) -> str:
    while True:
        value = _or_cancel(
            questionary.text(message, default=default, style=PROMPT_STYLE).ask()
        )
        text = str(value).strip()
        if text or not required:
            return text
        print("This field is required.")


def require_text(
    value: str | None,
    message: str,
    *,
    default: str = "",
    flag: str | None = None,
) -> str:
    """Return a stripped value, or interactively ask when missing.

    In non-interactive environments (no TTY), raises ``ValueError`` instead of
    prompting so CI/scripts still fail clearly.
    """
    if value is not None and str(value).strip():
        return str(value).strip()
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        hint = flag or message
        raise ValueError(f"Missing required value: {hint}")
    return ask_text(message, default=default, required=True)


def ask_confirm(message: str, *, default: bool = False) -> bool:
    return bool(
        _or_cancel(questionary.confirm(message, default=default, style=PROMPT_STYLE).ask())
    )


def ask_select(
    message: str,
    choices: Sequence[str | Choice],
    *,
    default: str | None = None,
) -> str:
    kwargs: dict[str, Any] = {"style": PROMPT_STYLE}
    if default is not None:
        kwargs["default"] = default
    return str(_or_cancel(questionary.select(message, choices=list(choices), **kwargs).ask()))


def ask_checkbox(
    message: str,
    choices: Sequence[str | Choice],
    *,
    min_selected: int = 0,
) -> list[str]:
    while True:
        selected = _or_cancel(
            questionary.checkbox(message, choices=list(choices), style=PROMPT_STYLE).ask()
        )
        values = [str(item) for item in selected]
        if len(values) >= min_selected:
            return values
        print(f"Select at least {min_selected}.")
