# Minion implementation plan

This folder is the build plan for Minion. Every unit spec in `units/` is written so that one agent
(or one human) can implement that piece independently, in parallel with the others, against the
contracts in [`../ARCHITECTURE.md`](../ARCHITECTURE.md).

## Status (2026-10-08)

| Area | State |
|---|---|
| Architecture + contracts (`docs/ARCHITECTURE.md`) | ✅ done |
| Foundation: `config.py`, `db.py` (all tables), `events.py`, `secrets.py`, `models.py`, `context.py` | ✅ done, smoke-tested (`tests/test_foundation.py`) |
| Supervisor (`minion/supervisor.py`): bootstrap, overlay venv, health-checked restarts, rollback, safe mode | ✅ written, ⏳ tests pending (unit `evolve`) |
| Research: OpenClaw, Hermes Agent, Claude computer-use toolset | ✅ `docs/research/*.md` |
| Research: MCP SDK 2.x, MCP registry, desktop image, opencode/Goose, Aider/OpenHands/Claude Code, Open WebUI | ⏳ partial drafts in `docs/research/drafts/` (unverified) |
| Units `hub`, `gateway`, `workshop`, `runtime`, `brain_core`, `brain_support`, `evolve`, `sched`, `api`, `web`, `packaging` | 📝 specs ready, not implemented |
| Units `desktop`, `harnesses` | 📝 to be specified (see below) |
| Integration, full test run, adversarial review, README | ⏳ after the units |

## Units

| Unit | Spec | Owns |
|---|---|---|
| MCP hub + registry client | [`units/hub.md`](units/hub.md) | `minion/mcp_hub/{connection,hub,registry_client}.py`, `catalog/servers/` |
| MCP gateway (`/mcp`) | [`units/gateway.md`](units/gateway.md) | `minion/mcp_hub/gateway.py` |
| Workshop (tools written by users / the brain) | [`units/workshop.md`](units/workshop.md) | `minion/workshop/`, `catalog/tools/` |
| Docker manager + harness runtime | [`units/runtime.md`](units/runtime.md) | `minion/runtime/{docker_manager,agents}.py` |
| Brain core (LLM, tools, runs, prompts, approvals, suggestions, parallel sub-agents) | [`units/brain_core.md`](units/brain_core.md) | `minion/brain/{llm,tools,agent,prompts,policy,suggestions}.py` |
| Brain support (native tools, memory, skills, usage) | [`units/brain_support.md`](units/brain_support.md) | `minion/brain/{native_tools,memory,skills,usage}.py`, `catalog/skills/` |
| Self-evolution, self-update, sharing | [`units/evolve.md`](units/evolve.md) | `minion/evolve/{git,evolver,contrib,updater,helper}.py` |
| Automations + self-improvement + frontier scout | [`units/sched.md`](units/sched.md) | `minion/evolve/{scheduler,improver}.py` |
| App, REST API, channels, CLI | [`units/api.md`](units/api.md) | `minion/{app,server,cli}.py`, `minion/api/`, `minion/channels/` |
| Web UI | [`units/web.md`](units/web.md) | `minion/web/`, `docs/screenshots/` |
| Packaging, installer, CI, community files | [`units/packaging.md`](units/packaging.md) | `Dockerfile`, `docker-compose.yml`, `install.sh`, `minionctl`, `.github/` |
| Built-in desktop | *to write* - see below | `images/desktop/`, `minion/runtime/desktop.py` |
| Harness templates | *to write* - see below | `catalog/agents/*` |

[`units/COMMON.md`](units/COMMON.md) holds the rules every implementer follows (ownership, no
foundation edits, testing, style).

### Desktop unit (spec outline)
* `images/desktop/`: Debian + Xvfb (1280x800x24) + openbox/tint2 + x11vnc + noVNC (6080) + Firefox/Chromium
  + terminal + editor + Hebrew fonts + xdotool; supervisord; non-root user. Start from the draft in
  `docs/research/drafts/desktop-image/` (built and partially tested during research - verify).
* Control API on port 8000: `/health`, `/screenshot`, `/action` (every `computer_toolset_20260801` member,
  exact semantics in `docs/research/computer_toolset.md`), `/bash`, `/open`, and an MCP endpoint at `/mcp`
  exposing the same capabilities to other agents.
* `minion/runtime/desktop.py` implementing ARCHITECTURE.md §5.7 (build/run/health, `computer_action`
  returning tool_result content blocks, halt semantics live in the brain's ToolRegistry, register MCP
  server `desktop` in the hub, noVNC upstream for the core's `/desktop/vnc/` proxy).
* Tests: action validation/mapping with a mocked control API; a docker test that builds the image,
  takes a real screenshot (valid PNG 1280x800), opens a URL and clicks.

### Harness templates unit (spec outline)
`catalog/agents/<name>/template.yaml` (+ Dockerfile / config templates / README) for: `openclaw`
(official image `ghcr.io/openclaw/openclaw`, see `docs/research/openclaw.md`), `hermes` (official image
`nousresearch/hermes-agent`, see `docs/research/hermes.md`), `opencode` (`ghcr.io/anomalyco/opencode`),
`goose`, `aider`, `claude-code` (optional; not open source), `openhands` (optional, heavy), and
`open-webui` (category `ui`, pointed at `http://minion:8700/v1`). Each: Anthropic + model from
`{{model}}`, Minion's MCP gateway (`{{gateway_url}}` + bearer `{{gateway_token}}`) when the harness
supports MCP, headless interface (`openai_http` or `exec_cli`), data volume, upgrade strategy (`pull` for
official `:latest` images, `rebuild` for Dockerfiles that install the latest release). Test: every
template parses as `AgentTemplate`, referenced files exist, placeholders are known; smoke-run the small
images (`--help`).

## How to run the plan with Claude Code

1. One-time: `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`; Docker running.
2. Implement units in parallel. With Claude Code's Workflow tool (ask for "use a workflow" / ultracode),
   run [`implement-unit.workflow.js`](implement-unit.workflow.js) once per unit with `args: {"unit": "<name>"}`
   - launch them all at once; each workflow runs its own agent. Without workflows, open one Claude Code
   session per unit with the prompt:
   > Read docs/plan/units/COMMON.md and docs/plan/units/<unit>.md, then implement the unit completely,
   > test it until it passes, and report files, test results, foundation changes needed, new
   > dependencies and contract deviations.
3. Integrate: apply the reported foundation changes / dependencies, run the full suite
   (`.venv/bin/python -m pytest -q`), fix contract mismatches.
4. Real end-to-end check: `docker compose up -d --build`, open `http://localhost:8700`, paste the API key,
   then: chat, add an MCP server from the registry, write a workshop tool, deploy OpenClaw + Hermes and
   delegate a task to each, drive the desktop, run an automation, make a self-evolution change (and watch
   a deliberately broken one roll back), apply an update from a test upstream.
5. Adversarial review (correctness, security - docker socket, tokens, path traversal, secret leakage,
   prompt injection via tool results - and the self-modification safety net), fix findings.
6. README (English + Hebrew), screenshots, then publish.
