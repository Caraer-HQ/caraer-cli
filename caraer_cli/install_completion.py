"""Install shell tab completion (used by scripts/install.sh)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from caraer_cli.completion import install_completion


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install Caraer CLI shell completion.")
    parser.add_argument(
        "--shell",
        "-s",
        help="Shell to install for (zsh|bash|fish). Auto-detected when omitted.",
    )
    args = parser.parse_args(argv)
    try:
        installed_shell, path = install_completion(shell=args.shell, prog_name="caraer")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"{installed_shell} completion installed in {path}")
    if installed_shell == "zsh":
        fpath_hint = Path.home() / ".zfunc"
        print(
            "If completion still does not work, ensure your ~/.zshrc contains:\n"
            f'  fpath=("{fpath_hint}" $fpath)\n'
            "  autoload -Uz compinit && compinit"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
