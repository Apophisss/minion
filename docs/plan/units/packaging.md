# Unit: Packaging, one-line installer, host control script, CI, community files

Files you own: `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.env.example`, `install.sh`,
`minionctl`, `scripts/*` (if needed), `.github/workflows/*.yml`, `.github/ISSUE_TEMPLATE/*`,
`.github/pull_request_template.md`, `LICENSE` (MIT, "Minion contributors"), `CONTRIBUTING.md`,
`CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), `SECURITY.md`, `docs/INSTALL.md`, `docs/CONFIGURATION.md`
(every env var in `minion/config.py`, grouped, with defaults and meaning), `tests/test_packaging.py`.
NOT yours: README.md (written at the end), application code.

Read ARCHITECTURE.md §2 (process model) and §6 (safety) carefully, plus `minion/supervisor.py` and
`minion/config.py`.

* Dockerfile (core image `minion-core`): `python:3.12-slim-bookworm`; apt: git, curl, ca-certificates,
  tini, nodejs + npm (for `npx` MCP servers - use a current LTS from the distro or NodeSource; verify),
  docker CLI + compose plugin (copy static binaries from the official `docker:cli` image via multi-stage,
  pin a version), `uv`/`uvx` (copy from `ghcr.io/astral-sh/uv:<pinned>`); `pip install -r requirements.txt`;
  `COPY . /app` INCLUDING `.git` (needed by the supervisor's clone/merge logic; `.dockerignore` must NOT
  exclude .git, but must exclude data/, .env, venvs, caches); a `/usr/local/bin/minion` wrapper running the
  CLI; `ENV MINION_DATA_DIR=/data MINION_IN_DOCKER=1 PYTHONUNBUFFERED=1`; `EXPOSE 8700`; `HEALTHCHECK` on
  `/health`; `ENTRYPOINT ["tini", "--", "python", "/app/minion/supervisor.py"]`. Runs as root (it needs the
  docker socket) - document it. Keep it lean; multi-arch friendly (amd64/arm64).
* docker-compose.yml: project `minion`; service `minion` (build `.`, image `minion-core:latest`,
  container_name `minion`, `restart: unless-stopped`, `env_file: .env`, port `${MINION_PORT:-8700}:8700`,
  volumes `/var/run/docker.sock:/var/run/docker.sock` and named volume `minion-data:/data`, network
  `minion-net` with alias `minion`); named volume `minion-data` (name: minion-data), network
  `minion-net` (name: minion-net). Satellites (desktop, harnesses, Open WebUI) are created by Minion itself,
  not by compose. Optional `ghcr.io` prebuilt image via `MINION_IMAGE`.
* `.env.example`: every user-facing setting with comments (ANTHROPIC_API_KEY first; MINION_API_TOKEN;
  MINION_AUTOSTART=desktop,openclaw,hermes,open-webui; budget/autonomy; persona; evolve/update/contribute
  modes; GITHUB_TOKEN; MINION_REPO_URL=https://github.com/apophisss/minion.git; TELEGRAM_*; MINION_HOST_DIR
  etc. filled by the installer).
* `install.sh` - the "super easy" one-liner: `curl -fsSL https://raw.githubusercontent.com/apophisss/minion/main/install.sh | bash`
  (also works with `bash -s -- --flags`). POSIX-friendly bash, `set -euo pipefail`, pretty but plain
  output, idempotent (re-running upgrades). Steps: detect OS/arch (Linux; macOS with Docker Desktop);
  check/install Docker (offer `get.docker.com` on Linux, with confirmation unless `--yes`), ensure compose
  v2; ensure git; clone or update the repo into `${MINION_DIR:-$HOME/minion}` (branch flag); create `.env`
  from `.env.example` if missing; ask for the Anthropic API key (read from `--key`, `ANTHROPIC_API_KEY`
  env, or prompt via `/dev/tty` so it works under `curl | bash`; allow skipping - the web UI can take it
  later); generate `MINION_API_TOKEN` (openssl/urandom); write `MINION_HOST_DIR`, `MINION_HOST_UID/GID`,
  `MINION_DOCKER_GID`, `MINION_REPO_URL`; choose satellites via flags (`--with openclaw,hermes,...`,
  `--minimal`), `--port`, `--no-start`, `--uninstall` (stop + optional `--purge` volumes), `--dry-run`
  (print actions only); `docker compose up -d --build`; wait for `/health`; print the URL (detect the
  server IP), the admin token, and next steps; install a `minion` shortcut (symlink `minionctl` into
  `/usr/local/bin` or `~/.local/bin`).
* `minionctl`: host control script: `start|stop|restart|status|logs [-f]|update|token|chat|ask "..."|open|
  shell|backup|restore <file>|uninstall`; `update` = `git pull --ff-only && docker compose up -d --build`;
  `chat`/`ask` exec the in-container `minion` CLI; `backup` tars the `minion-data` volume.
* CI `.github/workflows/ci.yml`: on push/PR - setup Python 3.12, install requirements-dev, ruff, pytest
  (`-m "not network and not docker and not slow"`), validate catalog (python script/pytest), `bash -n` +
  shellcheck on scripts, docker build of the core image (no push). `release.yml`: on tags `v*` and on main,
  build multi-arch `ghcr.io/<owner>/minion:latest|<tag>` with buildx and push (GITHUB_TOKEN). Keep actions
  pinned to major versions.
* Issue templates (bug, feature, new capability/MCP server request), PR template (mirrors CONTRIBUTING),
  CONTRIBUTING (dev setup, tests, how catalog contributions from Minion installs arrive as PRs and how they
  are reviewed), SECURITY (docker socket = root, tokens, exposing the port, reporting vulnerabilities).
* Verify for real: `bash -n` + `shellcheck` (install if possible) on install.sh/minionctl; run
  `install.sh --dry-run --yes --key test` in a clean `debian:bookworm-slim` container (mount the repo) to
  exercise argument parsing and checks; build the core image (`docker build -t minion-test-core .`) and run
  it briefly with a temp volume to confirm the supervisor bootstraps `/data/src` from `/app` (the app may
  not fully start yet if other modules are unfinished - that's OK, report what you observe); remove the
  test image/containers/volumes afterwards. `tests/test_packaging.py`: compose file parses and has the
  required keys, .env.example covers every Settings field with a `MINION_` env name, install.sh has
  `--dry-run`, Dockerfile entrypoint is the supervisor, .dockerignore keeps .git.
