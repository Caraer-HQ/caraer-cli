from __future__ import annotations

from types import SimpleNamespace

from caraer_cli.completion import detect_shell, show_completion_script
from caraer_cli.completion_callbacks import (
    complete_from_pairs,
    complete_output_format,
    complete_runtime,
)


def test_detect_shell_explicit() -> None:
    assert detect_shell("zsh") == "zsh"
    assert detect_shell("BASH") == "bash"


def test_show_completion_script_zsh() -> None:
    script = show_completion_script(shell="zsh", prog_name="caraer")
    assert "compdef" in script
    assert "_CARAER_COMPLETE" in script
    assert "caraer" in script


def test_complete_output_format() -> None:
    ctx = SimpleNamespace(obj=None)
    values = [item[0] for item in complete_output_format(ctx, "j")]  # type: ignore[arg-type]
    assert "json" in values


def test_complete_runtime() -> None:
    ctx = SimpleNamespace(obj=None)
    values = [item[0] for item in complete_runtime(ctx, "py")]  # type: ignore[arg-type]
    assert values == ["python312"]


def test_complete_from_pairs_case_insensitive() -> None:
    pairs = complete_from_pairs([("Dev", "Development"), ("prod", "Production")], "de")
    assert pairs == [("Dev", "Development")]
