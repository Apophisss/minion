# Common rules for every Minion implementer

You are implementing part of **Minion** - repo at `<repo root>` (Python 3.11+, FastAPI, asyncio).
Minion is a self-hosted, self-improving AI agent platform - an open-source alternative to Meta Muse /
OpenAI Dots. One Claude "brain" (Anthropic API key) is the single chat interface (web UI with voice,
CLI, Telegram, OpenAI-compatible API used by an Open WebUI front-end). It orchestrates MCP servers
(hub + aggregated gateway), existing open-source agent harnesses in Docker (OpenClaw, Hermes, opencode,
Goose, Aider, ...), a built-in Docker desktop it drives with Claude computer use, user/AI-written tools
(workshop), scheduled automations, approval gates, proactive suggestions, and its own code
(self-evolution with health-checked rollback, self-update from the GitHub repo, sharing new
capabilities back to the repo's shared `catalog/`). It will be published as a public open-source
project, so quality matters: clean code, real error handling, real tests.

## Read first
* `<repo root>/docs/ARCHITECTURE.md` - the contracts. Implement them exactly: other agents are
  coding against the same signatures in parallel right now.
* Foundation modules (use as-is): `minion/config.py`, `minion/db.py` (ALL tables are already declared
  there), `minion/events.py`, `minion/secrets.py`, `minion/models.py`, `minion/context.py`,
  `minion/supervisor.py`; `tests/conftest.py` (fixtures `settings`, `db`, `services`, `docker_ok`).

## Rules
* Write ONLY the files assigned to your unit. Other agents write other files in the same working tree
  concurrently: never modify or delete files you don't own. Never `git commit`, never touch `.git`.
* Do NOT modify foundation files. If you need a change there, work around it locally (e.g. a helper in
  your own module) and list the change under `foundation_changes_needed` in your report.
* Peers you depend on may not exist yet: code against ARCHITECTURE.md, and in tests use small fakes
  that implement the contract (e.g. `services.hub = FakeHub()`).
* Python: shared venv `V=.venv` (create once: `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`)
  (`$V/bin/python`). Installed: anthropic 1.12.1, mcp 2.3.0, docker 7.2, fastapi, uvicorn, pydantic 2,
  pydantic-settings, aiosqlite, httpx, pyyaml, croniter, websockets, pytest, pytest-asyncio, ruff.
  Need another package? `$V/bin/pip install` it and list it under `new_dependencies`.
* The installed SDKs are NEWER than your training data (mcp 2.x is a rewrite; anthropic 1.x is built on
  httpx2). Verify every API you use by reading the installed source under
  `$V/lib/python3.13/site-packages/` (and by running small snippets) before relying on it.
* Tests: `cd <repo root> && $V/bin/python -m pytest -q <your test files>` (asyncio_mode=auto) and
  `$V/bin/ruff check <your files>` must both pass. There is NO Anthropic API key here: use fakes. Docker
  IS available locally; docker tests must take the `docker_ok` fixture (so they skip elsewhere) and must
  clean up what they create (names prefixed `minion-test-`). Tests must never write into the real repo
  tree (`<repo root>/catalog` etc.): point settings at tmp dirs.
* Disk may be limited: don't pull/build big images unless your unit says so; remove what you build when
  done.
* Style: `from __future__ import annotations`; type hints; `logging.getLogger(__name__)` (no print in
  library code); async APIs (blocking work via `asyncio.to_thread`); clear, actionable error messages
  (errors are read by the brain, which must be able to fix things itself); comment density like the
  foundation files. No stubs, no TODOs, no fake implementations: everything must actually work.
* Research notes: `docs/research/*.md`
  and raw drafts under `docs/research/drafts/` (unverified). Read what is relevant.
* Your final answer is the structured report (files, test results, foundation changes needed, new
  dependencies, contract deviations, notes for the integrator).
