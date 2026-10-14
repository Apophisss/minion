#!/bin/sh
# Minion installer for macOS and Linux: https://github.com/apophisss/minion
#
#   curl -fsSL https://raw.githubusercontent.com/apophisss/minion/main/install.sh | sh
#
# It installs uv (https://docs.astral.sh/uv/) if it is missing, installs the `minion` command with
# `uv tool install`, then runs `minion setup`. It needs no admin rights and is safe to run again.
#
#   MINION_SPEC=git+https://github.com/apophisss/minion@main   what to install (default: minion-desktop)
#   MINION_NO_SETUP=1                                          install only, don't run `minion setup`
#   ... | sh -s -- --yes --profiles office                     arguments for `minion setup`
set -eu

SPEC="${MINION_SPEC:-${MINION_PACKAGE:-minion-desktop}}"
FALLBACK="git+https://github.com/apophisss/minion"

if [ -t 1 ]; then
  say() { printf '\033[1;35m==>\033[0m %s\n' "$*"; }
else
  say() { printf '==> %s\n' "$*"; }
fi
warn() { printf 'Warning: %s\n' "$*" >&2; }
die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

case "$(uname -s 2>/dev/null || true)" in
  MINGW* | MSYS* | CYGWIN*)
    die "on Windows, run this in PowerShell instead:  irm https://raw.githubusercontent.com/apophisss/minion/main/install.ps1 | iex"
    ;;
esac
if [ "$(id -u)" = 0 ] && [ -n "${SUDO_USER:-}" ]; then
  warn "this installs Minion for root. To install it for $SUDO_USER, run it without sudo: it needs no admin rights."
fi

find_uv() {
  if command -v uv >/dev/null 2>&1; then
    command -v uv
    return 0
  fi
  for dir in "${UV_INSTALL_DIR:-}" "${XDG_BIN_HOME:-}" "$HOME/.local/bin" "$HOME/.cargo/bin"; do
    if [ -n "$dir" ] && [ -x "$dir/uv" ]; then
      printf '%s\n' "$dir/uv"
      return 0
    fi
  done
  return 1
}

# 1. uv, which installs Minion and the Python it needs into a folder of their own.
if UV="$(find_uv)"; then
  say "Using uv: $UV"
else
  say "Installing uv, the Python package manager Minion installs with (https://docs.astral.sh/uv/)"
  if command -v curl >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- https://astral.sh/uv/install.sh | sh
  else
    die "neither curl nor wget is installed. Install one of them and run this again."
  fi
  UV="$(find_uv)" || die "uv did not install. See https://docs.astral.sh/uv/getting-started/installation/"
fi

# 2. Minion. Its commands go into uv's tool folder, usually ~/.local/bin.
BIN="$("$UV" tool dir --bin 2>/dev/null || printf '%s\n' "$HOME/.local/bin")"
FORCE=""
if [ -e "$BIN/minion" ] && ! "$UV" tool list 2>/dev/null | grep -q '^minion-desktop '; then
  if grep -qs 'minion.cli' "$BIN/minion"; then
    FORCE="--force" # Minion installed another way (pipx, pip): uv takes its command over
  else
    die "$BIN/minion is another program. Move it out of the way and run this again."
  fi
fi
say "Installing Minion ($SPEC)"
if ! "$UV" tool install --upgrade ${FORCE:+"$FORCE"} "$SPEC"; then
  [ "$SPEC" = minion-desktop ] || die "installing $SPEC failed (see above)."
  warn "minion-desktop could not be installed from PyPI; installing it from GitHub instead."
  "$UV" tool install --upgrade ${FORCE:+"$FORCE"} "$FALLBACK" || die "installing Minion failed (see above)."
fi

# 3. `minion` on PATH: now for the rest of this script, and through uv for new terminals.
case ":$PATH:" in
  *":$BIN:"*) NEW_PATH="" ;;
  *)
    PATH="$BIN:$PATH"
    export PATH
    "$UV" tool update-shell >/dev/null 2>&1 || true
    NEW_PATH=1
    ;;
esac

# 4. The first-run wizard. Piped from curl, stdin is this script, so answer on the terminal instead.
status=0
if [ -n "${MINION_NO_SETUP:-}" ]; then
  say "Minion is installed. Run \`minion setup\` when you're ready."
elif [ -t 0 ]; then
  "$BIN/minion" setup "$@" || status=$?
elif (true </dev/tty) 2>/dev/null; then
  "$BIN/minion" setup "$@" </dev/tty || status=$?
else
  "$BIN/minion" setup "$@" </dev/null || status=$? # no terminal at all: setup uses its defaults
fi

if [ -n "$NEW_PATH" ]; then
  say "Open a new terminal to use \`minion\` (or run: export PATH=\"$BIN:\$PATH\")"
fi
if [ "$status" -ne 0 ]; then
  warn "Minion is installed, but setup isn't finished. Run \`minion setup\` again once the problem above is fixed."
fi
exit "$status"
