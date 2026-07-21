"""Shell completion helpers and installers for the Caraer CLI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from typer._completion_shared import get_completion_script, install as typer_install

SUPPORTED_SHELLS = ("zsh", "bash", "fish", "powershell", "pwsh")


def detect_shell(explicit: str | None = None) -> str:
    """Resolve a shell name, preferring an explicit value then common fallbacks."""
    if explicit:
        shell = explicit.strip().lower()
        if shell not in SUPPORTED_SHELLS:
            raise ValueError(
                f"Unsupported shell '{explicit}'. Use one of: {', '.join(SUPPORTED_SHELLS)}"
            )
        return shell

    try:
        import shellingham

        name, _cmd = shellingham.detect_shell()
        if name:
            return str(name).lower()
    except Exception:
        pass

    env_shell = (os.environ.get("SHELL") or "").strip()
    if env_shell:
        return Path(env_shell).name.lower()

    raise ValueError(
        "Could not detect your shell. Pass --shell zsh|bash|fish to the installer."
    )


def completion_env_var(prog_name: str = "caraer") -> str:
    return "_{}_COMPLETE".format(prog_name.replace("-", "_").upper())


def show_completion_script(*, shell: str | None = None, prog_name: str = "caraer") -> str:
    resolved = detect_shell(shell)
    return get_completion_script(
        prog_name=prog_name,
        complete_var=completion_env_var(prog_name),
        shell=resolved,
    )


def install_completion(*, shell: str | None = None, prog_name: str = "caraer") -> tuple[str, Path]:
    resolved = detect_shell(shell)
    installed_shell, path = typer_install(
        shell=resolved,
        prog_name=prog_name,
        complete_var=completion_env_var(prog_name),
    )
    return installed_shell, Path(path)


def _safe_startswith(value: str, incomplete: str) -> bool:
    return value.lower().startswith((incomplete or "").lower())


def complete_from_pairs(
    pairs: Iterable[tuple[str, str]],
    incomplete: str,
) -> list[tuple[str, str]]:
    return [
        (value, help_text)
        for value, help_text in pairs
        if _safe_startswith(value, incomplete) or _safe_startswith(help_text, incomplete)
    ]
