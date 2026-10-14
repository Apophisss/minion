#!/bin/sh
# Minion installer — https://github.com/apophisss/minion
#   curl -fsSL https://raw.githubusercontent.com/apophisss/minion/main/install.sh | sh
# Installs the `minion` command with uv (preferred), pipx or pip. Nothing else is touched.
set -eu

PKG="${MINION_PACKAGE:-minion-desktop}"
FALLBACK="git+https://github.com/apophisss/minion"

say() { printf '\033[1;35m▸\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$*" >&2; }

if command -v uv >/dev/null 2>&1; then
  say "Installing $PKG with uv"
  uv tool install --force "$PKG" || uv tool install --force "$FALLBACK"
elif command -v pipx >/dev/null 2>&1; then
  say "Installing $PKG with pipx"
  pipx install --force "$PKG" || pipx install --force "$FALLBACK"
elif command -v python3 >/dev/null 2>&1; then
  say "Installing uv (https://docs.astral.sh/uv/) to install Minion in its own environment"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$PATH"
  uv tool install --force "$PKG" || uv tool install --force "$FALLBACK"
else
  warn "Python 3.11+ is required: https://www.python.org/downloads/"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1 && ! command -v podman >/dev/null 2>&1; then
  warn "Docker was not found. Install Docker Desktop (macOS/Windows) or Docker Engine (Linux):"
  warn "  https://docs.docker.com/get-docker/"
  warn "On Linux you can also run desktops without Docker: MINION_BACKEND=local (see docs/faq.md)."
fi

say "Done. Try:"
printf '    minion doctor\n    minion up office && minion open writer && minion see\n'
printf '    claude mcp add minion -- minion mcp      # give Claude Code desktops\n'
