# Contributing to Minion

Thanks for helping. Minion aims to be the simplest, lightest way to give an AI agent a computer.

## Setup

```bash
git clone https://github.com/apophisss/minion && cd minion
uv venv && uv pip install -e ".[dev]"       # or: python -m venv .venv && pip install -e ".[dev]"
pytest                                       # unit tests (no Docker needed)
ruff check . && ruff format --check .
```

Integration tests run real desktops:

```bash
# Linux with X tools: sudo apt-get install xvfb xdotool wmctrl x11-utils jwm xterm python3-pil python3-gi \
#   gir1.2-atspi-2.0 at-spi2-core dbus-daemon tesseract-ocr xclip xauth
pytest -m x11
MINION_TEST_DOCKER=1 pytest -m docker        # needs Docker; builds/pulls the base image
```

## Layout

- `minion/agent/` runs **inside** desktops (stdlib + Pillow + optional PyGObject). It must never import host code.
- Everything else runs on the host and must stay **pure standard library**: no dependencies, ever.
- `minion/profiles/*.toml` are the built-in desktops, and `minion/images/base.Dockerfile` is the base image.
- `docs/` holds the user docs, `scripts/` the benchmark and image tools.

## Good contributions

- **Profiles**: a new desktop for a job (design, video, GIS, accounting…) is often a 15-line TOML file.
- **Better `see` for an app**: improvements in `minion/agent/a11y.py` that make a popular app's UI clearer
  or cheaper in tokens.
- **Agent client recipes**: tested MCP setups for more clients in `docs/agents.md`.
- **Bugs with a repro**: run `minion replay -o bug.html` and attach the timeline.

## Pull requests

Keep changes focused, add or update tests, and update the docs when behavior changes. CI runs lint, unit tests
on Python 3.11–3.14, local-backend integration tests, and an image build.
