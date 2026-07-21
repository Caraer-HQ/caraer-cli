#!/usr/bin/env bash
# Install caraer-cli (editable) and shell tab completion.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SHELL_NAME=""
DEV=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --shell|-s)
      SHELL_NAME="${2:-}"
      shift 2
      ;;
    --no-dev)
      DEV=0
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/install.sh [--shell zsh|bash|fish] [--no-dev]

Installs the Caraer CLI into the current Python environment and sets up
shell tab completion for the detected (or specified) shell.
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

python3 -m pip install --upgrade pip
if [[ "$DEV" -eq 1 ]]; then
  python3 -m pip install -e ".[dev]"
else
  python3 -m pip install -e .
fi

if [[ -n "$SHELL_NAME" ]]; then
  python3 -m caraer_cli.install_completion --shell "$SHELL_NAME"
else
  python3 -m caraer_cli.install_completion
fi

echo
echo "Done. Restart your terminal (or open a new tab) for tab completion."
echo "Try: caraer --help"
