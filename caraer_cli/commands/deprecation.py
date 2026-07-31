"""Helpers for hidden deprecated CLI aliases."""

from __future__ import annotations

import functools
from typing import Any

import typer
from typer.models import CommandInfo


def warn_deprecated(old_path: str, new_path: str) -> None:
    """Print a one-line deprecation warning pointing at the new command."""
    from caraer_cli.formatters.output import print_warning

    print_warning(f"'{old_path}' is deprecated; use '{new_path}' instead.")


def _command_name(info: CommandInfo) -> str | None:
    if info.name:
        return info.name
    if info.callback is not None:
        return info.callback.__name__.replace("_", "-")
    return None


def register_deprecated_leaf_alias(
    parent: typer.Typer,
    source: typer.Typer,
    *,
    source_name: str,
    alias_name: str,
    old_path: str,
    new_path: str,
) -> None:
    """Register a hidden leaf alias that warns, then runs the source command."""
    match: CommandInfo | None = None
    for info in source.registered_commands:
        if _command_name(info) == source_name:
            match = info
            break
    if match is None or match.callback is None:
        raise KeyError(f"Command '{source_name}' not found on source typer")

    original = match.callback

    @functools.wraps(original)
    def wrapper(
        *args: Any,
        __orig=original,
        __old=old_path,
        __new=new_path,
        **kwargs: Any,
    ) -> Any:
        warn_deprecated(__old, __new)
        return __orig(*args, **kwargs)

    parent.registered_commands.append(
        CommandInfo(
            name=alias_name,
            cls=match.cls,
            context_settings=match.context_settings,
            callback=wrapper,
            help=match.help,
            epilog=match.epilog,
            short_help=match.short_help,
            options_metavar=match.options_metavar,
            add_help_option=match.add_help_option,
            no_args_is_help=match.no_args_is_help,
            hidden=True,
            deprecated=False,
            rich_help_panel=match.rich_help_panel,
        )
    )


def register_deprecated_group_alias(
    parent: typer.Typer,
    source: typer.Typer,
    *,
    alias_name: str,
    old_path: str,
    new_path: str,
    help: str | None = None,
) -> None:
    """Register a hidden group alias that warns, then runs source subcommands."""

    def _warn_callback(ctx: typer.Context) -> None:
        warn_deprecated(old_path, new_path)

    legacy = typer.Typer(
        help=help or source.info.help or f"Deprecated alias for '{new_path}'.",
        no_args_is_help=True,
        callback=_warn_callback,
    )
    legacy.registered_commands.extend(source.registered_commands)
    parent.add_typer(legacy, name=alias_name, hidden=True)
