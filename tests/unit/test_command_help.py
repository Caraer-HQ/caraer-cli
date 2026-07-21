from __future__ import annotations

from typer.main import get_command

from caraer_cli.main import app as typer_app


def _iter_commands(cmd, prefix: str = "caraer"):
    yield prefix, cmd
    if not hasattr(cmd, "commands"):
        return
    for name, child in sorted(cmd.commands.items()):
        yield from _iter_commands(child, f"{prefix} {name}")


def test_every_visible_command_has_help() -> None:
    missing: list[str] = []
    for path, cmd in _iter_commands(get_command(typer_app)):
        if getattr(cmd, "hidden", False):
            continue
        help_text = (cmd.help or "").strip()
        if not help_text:
            missing.append(path)
    assert not missing, "Commands missing help/docstrings:\n" + "\n".join(missing)
