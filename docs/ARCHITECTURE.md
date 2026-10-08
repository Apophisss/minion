# Minion architecture

> This document is also read by Minion's own brain when it improves itself.
> Keep it accurate when you change the code.

## 1. What Minion is

Minion is a self-hosted, self-improving AI platform that turns an Anthropic API key
into a working team:

* **Brain**: a Claude agent loop (`minion/brain`) with tools for everything below.
  It's the single chat interface: web UI (text + voice), CLI, Telegram, and an
  OpenAI-compatible API. It delegates work to other agents.
* **MCP hub** (`minion/mcp_hub`): connects to any number of MCP servers (stdio, docker,
  streamable HTTP, SSE), added at runtime by the user, the brain, the catalog or the
  official MCP registry.
* **MCP gateway** (`/mcp`): one aggregated MCP endpoint that exposes all hub tools,
  so OpenClaw, Hermes and any MCP client get every tool Minion has.
* **Workshop** (`minion/workshop`): tools written by the user or by the brain (plain Python
  files with `@tool`), validated in a subprocess, hot-loaded, and shared upstream.
* **Agents** (`minion/runtime/agents.py`): OpenClaw, Hermes and any other agent
  template run as Docker containers, wired to the gateway and to Claude.
* **Desktop** (`images/desktop`, `minion/runtime/desktop.py`): a built-in Linux desktop
  (browser, terminal, office apps) in Docker. The brain drives it through Claude's computer-use
  toolset, and humans watch it live via noVNC in the web UI.
* **Evolution** (`minion/evolve`): self-modification of its own code in git worktrees with
  tests, health-checked restarts and automatic rollback; self-update from the upstream
  repo; sharing of new capabilities back to the repo; scheduled automations; a
  self-improvement loop and a "frontier scout" that keeps the installation current.

```
                 ┌──────────────── minion-core container ────────────────┐
 Web UI / CLI ──►│ FastAPI (/api, /v1, /mcp, /desktop)                   │
 Telegram     ──►│   Brain ── ToolRegistry ─┬─ native tools (services)   │
 OpenAI API   ──►│                          ├─ MCP hub tools ────────────┼──► MCP servers (stdio / docker / http)
                 │                          └─ computer toolset ─────────┼──► minion-desktop (Xvfb+noVNC+control API)
                 │   MCP gateway (/mcp) ◄────────────────────────────────┼─── openclaw / hermes containers
                 │   Evolver / Updater / Contributor / Scheduler          │
                 │ supervisor.py (PID 1, from the image) runs the server  │
                 │ from /data/src (git) with health-checked rollback      │
                 └───────────────────────────────────────────────────────┘
```

## 2. Process model and directories

* The core image contains the pristine source at `/app` (a git checkout, `.git` included).
* `minion/supervisor.py` (stdlib only) is PID 1 (under tini). It always runs from `/app`,
  so self-modification can never break the safety net. On boot it:
  1. creates `/data/src` by `git clone /app /data/src` the first time, sets `origin` to
     `MINION_REPO_URL` (or `/app`'s origin), and configures a git identity;
  2. installs `/data/src/requirements-extra.txt` (when its hash changed) into `/data/venv`
     (created with `--system-site-packages`);
  3. launches `python -m minion.server` with `cwd=/data/src`, `PYTHONPATH=/data/src`,
     `MINION_SRC_DIR=/data/src`;
  4. after any start where `HEAD != last_good`, waits up to `MINION_HEALTH_TIMEOUT_S` for
     `GET /health` → 200, then records `HEAD` as last good (`/data/run/last_good` + tag
     `minion-last-good`). If the child crashes or never becomes healthy, it runs
     `git reset --hard <last_good>`, writes `/data/run/rollback.json` (failed commit + log tail),
     and restarts. After 3 consecutive rollbacks it enters safe mode (runs `/app` code).
  5. exit code `75` from the child means "restart requested" (see `Services.request_restart`).
* Data volume `/data`: `minion.db` (SQLite), `src/` (running source, git), `venv/`, `run/`
  (supervisor coordination), `local/` (private tools/skills/agents), `workshop/` (tool venv),
  `logs/`.

## 3. Shared foundation (do not duplicate)

| Module | Purpose |
|---|---|
| `minion/config.py` | `Settings` (env vars), `get_settings()` |
| `minion/db.py` | `Database` (aiosqlite) - **all tables are declared in `SCHEMA`** |
| `minion/events.py` | `EventBus` pub/sub for live UI updates |
| `minion/secrets.py` | `SecretStore` + `${secret:NAME}` / `${env:NAME}` placeholders |
| `minion/models.py` | `ServerSpec`, `ContainerSpec`, `ToolInfo`, `ToolCallResult`, `AgentTemplate`, ... |
| `minion/context.py` | `Services` container, `spawn()`, `request_restart()`, `git_lock` |

Every service class takes `services: Services` as its first constructor argument and
exposes `async start()` and `async stop()` (both idempotent; `start` must not block for
long - spawn background work with `services.spawn`). Services must tolerate optional peers
being `None` (e.g. Docker unavailable → desktop/agents disabled, everything else works).

## 4. The shared catalog (capabilities everyone gets)

```
catalog/
  tools/<name>.py          workshop tools (one file may define several @tool functions)
  servers/<name>.yaml      MCP server specs (ServerSpec YAML)
  servers/<name>/          full MCP server projects: server.yaml + Dockerfile + source
  agents/<name>/           agent templates: template.yaml + Dockerfile + config templates
  skills/<name>.md         playbooks for the brain (YAML front matter: name, description)
```

New capabilities created on request (a tool, an MCP server, an agent type, a skill) go into
the catalog in `/data/src`, are committed locally, and are shared upstream by the
`Contributor` (PR or push, per `MINION_CONTRIBUTE_MODE`). Every installation receives them
through self-update. Anything that embeds personal data goes to `/data/local/...` instead
and is never shared. Secrets are always `${secret:NAME}` placeholders, never literals.

## 5. Component contracts

All methods below are `async` unless marked *(sync)*.

### 5.1 DockerManager - `minion/runtime/docker_manager.py`
Wraps the `docker` SDK (sync) with `asyncio.to_thread`. Labels every container it creates
with `minion.managed=true`, `minion.kind=<kind>`, `minion.name=<name>`; names are prefixed
`minion-` when missing.
```
DockerManager(services)
  available: bool                       (sync property) daemon reachable
  start() / stop()                      connect, ensure network settings.docker_network
  ensure_network(name=None) -> str
  ensure_volume(name) -> str
  image_exists(tag) -> bool
  pull(image) -> None
  build_image(context_dir: Path, tag, dockerfile="Dockerfile", build_args=None, on_log=None) -> str
  run(spec: ContainerSpec, replace=True, pull_missing=True) -> dict  # resolves ${secret:..} in env; builds when build_context set and image missing
  stop(name, timeout=10) / remove(name, force=True) / restart(name)
  inspect(name) -> dict | None          {id,name,image,status,kind,labels,ports,ip,created}
  list(kind=None, all=True) -> list[dict]
  logs(name, tail=200) -> str
  exec(name, cmd: list[str] | str, workdir=None, env=None, user=None, timeout=120) -> tuple[int, str, str]
  put_file(name, path, content: bytes | str, mode=0o644) -> None   # via put_archive (works on created-but-not-started containers)
  wait_http(url, timeout=60) -> bool
  self_container() -> dict | None       the container Minion itself runs in (if any)
```

### 5.2 MCPHub - `minion/mcp_hub/hub.py` (+ `connection.py`)
One `MCPConnection` per server, each owned by its own asyncio task that enters the
transport + `ClientSession` context managers, signals ready, and waits for a stop event
(anyio cancel scopes must exit in the task that entered them). Reconnects with backoff.
Refreshes its tool list on `notifications/tools/list_changed` and on demand.
```
MCPHub(services)
  start()                     load specs: DB table `servers` + catalog/servers + local/servers + builtin
                              (workshop, desktop when running); connect enabled ones in background
  stop()
  add_server(spec: ServerSpec, persist=True, connect=True) -> ServerStatus   # replaces same name
  remove_server(name) -> None
  set_enabled(name, enabled: bool) -> ServerStatus
  restart_server(name) -> ServerStatus
  get_spec(name) -> ServerSpec | None                        (sync)
  list_servers() -> list[tuple[ServerSpec, ServerStatus]]    (sync)
  list_tools(server: str | None = None) -> list[ToolInfo]    (sync)
  get_tool(qualified_name) -> ToolInfo | None                (sync)
  call_tool(qualified_name, arguments: dict, timeout=None) -> ToolCallResult
  call(server, tool, arguments, timeout=None) -> ToolCallResult
  wait_ready(name, timeout=30) -> ServerStatus
  on_change(callback: Callable[[], Any]) -> None             (sync) called after the tool set changes
  list_resources(server) / read_resource(server, uri) / list_prompts(server) / get_prompt(server, name, args)
qualify(server, tool) -> str   (module function) "<server>__<tool>", [a-zA-Z0-9_-], <=64 chars (hash suffix)
```
Missing secrets put a server in state `needs_secret` (with `missing_secrets`) instead of failing.
Docker-based stdio servers use `command: docker`, `args: [run, -i, --rm, ..., image]`.

### 5.3 RegistryClient - `minion/mcp_hub/registry_client.py`
Official MCP registry (`https://registry.modelcontextprotocol.io`).
```
RegistryClient(services)
  search(query, limit=20) -> list[dict]     normalised {name, title, description, version, packages, remotes, repository}
  get(name, version="latest") -> dict | None
  to_spec(entry: dict, prefer: str | None = None, server_name: str | None = None) -> tuple[ServerSpec, list[dict]]
      # second value: env/header vars the user must provide [{name, description, is_secret, is_required}]
      # npm -> npx -y pkg@ver ; pypi -> uvx pkg==ver ; oci -> docker run -i --rm image ; remotes -> http/sse url
```

### 5.4 MCPGateway - `minion/mcp_hub/gateway.py`
A low-level MCP server whose `list_tools`/`call_tool` read the hub dynamically. Served over
streamable HTTP and mounted at `/mcp`. Sends `notifications/tools/list_changed` to connected
sessions when the hub changes. Exposes hub tools with `expose_in_gateway=True` (qualified
names), plus Minion meta tools `minion_ask` (ask the brain; disabled for calls coming from
the brain itself) and `minion_status`. Auth: `Authorization: Bearer <gateway_token or api_token>`.
```
MCPGateway(services)
  start() / stop()
  asgi_app -> ASGI app          (sync property) mounted by app.py at /mcp
  lifespan() -> async context manager    run inside the FastAPI lifespan (session manager)
  notify_tools_changed() -> None
```

### 5.5 Workshop - `minion/workshop/`
* `sdk.py`: `@tool` / `@tool(name=..., description=...)` decorator for tool authors; functions
  may be sync or async, typed parameters become the JSON schema, the docstring is the description.
* `server.py`: `python -m minion.workshop.server --dir A --dir B` - a stdio MCP server that
  imports every `*.py` in the dirs (each in isolation; a broken file is reported, not fatal) and
  registers their tools. Registered in the hub as builtin server `workshop`.
* `validator.py`: `python -m minion.workshop.validator <file> [--call name --args JSON]` →
  JSON report `{ok, tools: [{name, description, input_schema}], error, call_result}`.
* A tool file may declare `# requirements: pkg1, pkg2>=1.0` - installed into
  `<data_dir>/workshop/venv` (created with `--system-site-packages`); the workshop server runs
  with that venv's python.
```
Workshop(services)
  start() / stop()                       ensure venv, register the builtin `workshop` server in the hub
  list_tools() -> list[dict]             [{file, scope, tools:[{name, description}], requirements, error}]
  read_tool(file_name) -> dict           {file, scope, code}
  write_tool(file_name, code, scope="shared", test_call: dict | None = None, share=True) -> dict
      # validate in a subprocess → install requirements → optional test call → move into place
      # → reload the workshop server → (shared) commit + contribute. Returns {ok, tools, error, contribution}
  delete_tool(file_name, scope="shared") -> dict
  test_tool(tool_name, arguments) -> ToolCallResult      via the hub
  scaffold_server(name, description, language="python", code: str | None = None, share=True) -> dict
      # full MCP server project in catalog/servers/<name>/ (server.yaml + Dockerfile + source),
      # builds its image, registers it in the hub
```

### 5.6 AgentManager - `minion/runtime/agents.py`
Minion does not reinvent agents: it wraps existing open-source **harnesses** that keep getting
better upstream, and unifies them behind its chat. Shipped templates: `openclaw` (personal
assistant with messaging channels), `hermes` (Nous Research self-improving agent), `opencode`
and `goose` (coding / general agents), `aider` (pair-programming), `claude-code` (optional,
Anthropic's CLI - not open source), `openhands` (optional, heavy), and `open-webui`
(category `ui`: a rich chat front-end wired to Minion's OpenAI-compatible API). Each template's
Dockerfile installs the **latest** upstream release, so `upgrade(name)` (rebuild with `--pull`,
keep the previous image as `<image>-previous` for rollback) moves it forward; the scheduler runs
`upgrade_all()` weekly.

Templates: `catalog/agents/*/template.yaml` and `<data_dir>/local/agents/*/template.yaml`.
Config files are rendered with `{{var}}` substitution. Variables: `name`, `gateway_url`,
`gateway_token`, `model`, `fast_model`, `anthropic_api_key` (resolved secret), `agent_token`,
`core_url`, plus template-specific `overrides`. Configs are written into the container with
`put_file` after create and before start (or into the agent's data volume).
```
AgentManager(services)
  start() / stop()                       load templates + instances; autostart from settings.autostart
  list_templates() -> list[AgentTemplate]          (sync)
  get_template(name) -> AgentTemplate | None       (sync)
  list_instances() -> list[AgentInstance]
  deploy(template, name=None, overrides=None, wait=True) -> AgentInstance  # build image if needed, run, health
  stop(name) / start_instance(name) / remove(name, purge_data=False)
  status(name) -> AgentInstance
  send(name, message, session: str | None = None, timeout=None) -> str     # delegate a task, return the reply
  logs(name, tail=200) -> str
  upgrade(name) -> dict                  # rebuild/pull latest upstream, redeploy, health-check, roll back on failure
  upgrade_all() -> list[dict]
  write_template(name, files: dict[str, str], share=True) -> dict          # new agent type in the catalog
```

### 5.7 DesktopManager - `minion/runtime/desktop.py`
Container `minion-desktop` (image built from `images/desktop`) on the minion network.
Control API on port 8000 (`/health`, `/screenshot`, `/action`, `/bash`, `/open`, and an MCP
endpoint at `/mcp`), noVNC on 6080 (proxied by the core at `/desktop/vnc/`).
```
DesktopManager(services)
  start() / stop()                         autostart when "desktop" in settings.autostart
  ensure_running(wait=True) -> dict        build image if missing, run, wait for health, register MCP server "desktop"
  shutdown() -> None
  status() -> dict                         {state, resolution, vnc_path, error}
  screenshot() -> tuple[bytes, int, int]   PNG bytes, width, height
  computer_action(name: str, input: dict) -> list[dict]   # Claude computer-toolset member → tool_result content blocks
  bash(cmd, timeout=120) -> dict           {exit_code, stdout, stderr}
  open(target: str) -> dict                URL or application name
  control_url / vnc_url -> str             (sync properties) upstream URLs inside the docker network
```

### 5.8 Brain - `minion/brain/`
* `llm.py` - `LLMClient(services)` wraps `anthropic.AsyncAnthropic` streaming
  (`client.beta.messages.stream(...)` + `get_final_message()`), adaptive thinking with
  `display` (`MINION_THINKING_DISPLAY`), `output_config.effort`, prompt caching (cached system
  prefix + top-level automatic caching), server-side refusal fallbacks
  (`fallbacks="default"` + beta `server-side-fallback-2026-07-01`), compaction
  (`compact-2026-01-12`), `eager_input_streaming` on client tools. **Self-healing requests**:
  when the API rejects an optional feature with a 400, the client drops that feature,
  remembers it (kv `llm.disabled_features`) and retries. Records usage via `UsageTracker`.
  `FakeLLM` (same interface) replays scripted responses for tests.
  ```
  LLMClient.stream_turn(*, system: list[dict], messages: list[dict], tools: list[dict],
                        on_event: Callable[[dict], Awaitable[None]] | None, purpose="chat",
                        session_id=None, model=None, effort=None) -> dict
      # returns the final message as a plain dict {id, model, role, content: [blocks as dicts], stop_reason, usage}
  ```
* `tools.py` - `ToolRegistry(services)`: native tools + hub tools + server tools (web search/fetch)
  + the computer toolset (when the desktop runs). Deterministic ordering (prompt caching).
  Above `tool_search_threshold` tools, hub tools get `defer_loading: true` and
  `tool_search_tool_bm25_20251119` is added.
  ```
  register(name, description, input_schema, handler, *, group="system", dangerous=False)   (sync)
  definitions(ctx: ToolContext) -> list[dict]
  execute(block: dict, ctx: ToolContext) -> dict      # one tool_result block (never raises)
  ```
  `ToolContext(session_id, source, purpose, depth)`; handlers: `async (args: dict, ctx) -> str | dict | list[content blocks]`.
* `native_tools.py` - `register_native_tools(registry, services)`: the system tools:
  `mcp_*` (list/add/remove/restart/registry search/install), `workshop_*`, `docker_*`,
  `agent_*` (deploy/send/list/stop/logs/write_template), `desktop_*` (start/status/bash/open),
  `memory_*`, `skill_*`, `secret_list`/`secret_request`, `schedule_*`, `goal_*`,
  `self_*` (evolve: begin/read/write/edit/list/grep/diff/check/finish/abort, history, rollback),
  `update_*` (check/apply), `contribute`, `usage_report`, `notify_user`.
* `agent.py` - `Brain(services)`. Runs are **background tasks**: they keep going when the
  client disconnects (like Muse/Dots); clients (re)attach to a run's event stream.
  ```
  start_run(session_id: str | None, message: str | list, *, source="web", purpose="chat",
            title=None, depth=0, target: str | None = None) -> dict   # {run_id, session_id}
  events(run_id, after: int = 0) -> AsyncIterator[dict]   # replays buffered events then follows live
      # each event has "seq"; types: {type: "run", run_id, session_id} | {"text_delta", text}
      #   | {"thinking", text} | {"tool_call", id, name, input} | {"tool_result", id, name, ok, summary}
      #   | {"approval", approval_id, tool, input, reason} | {"suggestion", id, title}
      #   | {"done", text, stop_reason, usage} | {"error", message}
  run(session_id, message, **kw) -> AsyncIterator[dict]   # start_run + events (convenience)
  chat(session_id, message, **kw) -> tuple[str, str]      # (session_id, final text)
  cancel(run_id_or_session_id) -> bool
  active_runs() -> list[dict]
  list_sessions(limit=50) / get_session(session_id) / delete_session(session_id)
  ```
  `target` (or a message starting with `@<agent>`) routes straight to that agent harness and
  stores both sides in the session. Transcripts are append-only (preserved thinking). One run per
  session at a time (a new message while a run is active is queued).
* `policy.py` - `PolicyEngine(services)`: approval gates (like Muse "Sentinel" / Dots approval
  gates). `decide(tool_name, tool_input, ctx, annotations=None) -> "allow" | "ask" | "deny"` from
  user rules (`tool_policies`), MCP tool annotations (`destructiveHint`, `openWorldHint`,
  `readOnlyHint`) and name heuristics (send/delete/pay/purchase/transfer/publish/...), per
  `MINION_APPROVALS` (`smart` default, `strict`, `off`). `request(tool, input, ctx, reason) -> bool`
  creates an `approvals` row, emits `approval.request`, waits for `resolve(id, decision, remember)`
  (API/UI/Telegram buttons) up to `MINION_APPROVAL_TIMEOUT_S`. Autonomous runs (automation,
  improve, scout) never wait: "ask" becomes "deny + suggestion/notify".
* `suggestions.py` - `SuggestionBox(services)`: proactive capability ideas.
  `add(title, description, kind, payload=None, source="brain") -> int`, `list(status=None)`,
  `set_status(id, status, result="")`, `build(id) -> dict` (starts a brain run that builds and
  integrates it). Shown in the UI with one-click "Build it".
* `prompts.py` - system prompt builder (stable prefix: identity, principles, self-knowledge
  pointers; volatile state goes into a mid-conversation system message, not the prefix).
* `memory.py` - `MemoryStore(services)`: `add(kind, content, tags=(), source="") -> int`,
  `search(query, limit=10)`, `recent(kind=None, limit=20)`, `delete(id)`.
* `skills.py` - `SkillLibrary(services)`: markdown playbooks with front matter.
  `list() -> [{name, description, scope}]`, `read(name) -> str`,
  `write(name, description, body, scope="shared", share=True) -> dict`, `delete(name, scope)`.
* `usage.py` - `UsageTracker(services)`: `record(model, usage, purpose, session_id)`,
  `summary(period="month") -> dict` (tokens, cost, budget, remaining, pace),
  `autonomy_factor() -> float` (how much spare budget autonomous jobs may use).

### 5.9 Evolution - `minion/evolve/`
* `git.py` - `Git(repo: Path)`: async wrapper over the git CLI
  (`run, head, branch, status, is_clean, add, commit, log, diff, show, fetch, merge, reset_hard,
  tag, worktree_add, worktree_remove, changed_files, ahead_behind, push, remote_url`).
* `evolver.py` - `Evolver(services)`: self-modification in worktrees under `<data_dir>/evolve/`.
  ```
  begin(goal) -> dict                      {id, branch, path}
  read_file(ws, path) / write_file(ws, path, content) / edit_file(ws, path, old, new)
  list_files(ws, pattern="**/*") / grep(ws, pattern) / diff(ws)
  run_checks(ws) -> CheckResult            compileall + import smoke test + pytest (timeout)
  finish(ws, message, share=True) -> dict  commit → checks → (approve mode) proposal | (auto) merge to
                                           main + request_restart + contribute
  abort(ws)
  list_proposals(status=None) / approve(id) / reject(id)
  history(limit=50) -> list[dict]          evolve_log rows
  rollback(commit=None) -> dict            reset main to last good (or commit) + restart
  ```
* `updater.py` - `Updater(services)`: polls `origin/<branch>` every `update_interval_minutes`
  (and on the GitHub webhook `POST /api/update/webhook`). `check() -> {behind, ahead, commits}`,
  `apply(force=False) -> dict`: merge in a worktree → checks → code-only changes: fast-forward
  main + restart (supervisor rollback protects it); image-level changes (Dockerfile,
  `images/**`, `docker-compose.yml`, dependencies in `pyproject.toml`, `minion/supervisor.py`):
  spawn the host update helper. `notify` mode only reports.
* `helper.py` - `python -m minion.evolve.helper`: runs in a short-lived helper container with
  the docker socket and the host install dir mounted: `git pull --ff-only` in the host dir,
  `docker compose up -d --build`, waits for health, rolls back the host checkout on failure.
* `contrib.py` - `Contributor(services)`: `commit_paths(paths, message) -> sha` (local commit
  in the source repo, under `git_lock`), `share(sha | None, title, body, paths) -> dict`:
  `pr` → branch `minion/contrib/<install_id>/<slug>` on top of `origin/<branch>` + GitHub PR
  (when the token cannot push to the upstream repo - the normal case for a public project - it
  forks the repo into the token owner's account, pushes the branch there and opens a cross-repo
  PR); `push` → push to the branch (maintainers only); `off`/no token → recorded as local.
  The token is passed per command (`-c http.extraheader`), never stored in git config.
* `scheduler.py` - `Scheduler(services)`: 5-field cron automations stored in `schedules`;
  `add(name, cron, prompt) -> dict`, `list()`, `remove(id)`, `set_enabled(id, bool)`,
  `run_now(id)`. Built-in jobs: self-improvement, frontier scout, update check.
* `improver.py` - `Improver(services)`: gathers signals (failed tool calls, negative feedback,
  rollbacks, open goals, errors) and runs the brain with an improvement brief; `scout()` runs
  the frontier scout (new MCP servers / AI tools / techniques → install, propose or write a
  digest). Both respect `UsageTracker.autonomy_factor()`.

### 5.10 API, channels, UI
* `minion/app.py` - `create_app(settings=None, services=None) -> FastAPI`; lifespan builds and
  starts services in order: db → secrets/tokens → bus → git → docker → hub → registry →
  workshop → desktop → agents → memory/skills/usage → tools/brain → gateway → evolver →
  contrib → updater → scheduler → improver → channels. Stops in reverse.
* `minion/server.py` - runs uvicorn; exits with `MINION_EXIT_CODE` (75 = restart) afterwards.
* `minion/api/` - REST under `/api` (auth: `Authorization: Bearer <api_token>`, cookie
  `minion_token`, or `?token=` for EventSource/WebSocket). `/health` is public.
* `minion/channels/openai_compat.py` - `/v1/models`, `/v1/chat/completions` (streaming SSE);
  models `minion` (the brain, which delegates as it sees fit) and `minion/<agent>` (talk to one
  harness directly). This is what the Open WebUI front-end and any OpenAI-compatible app use.
  Session mapping: header `X-Minion-Session`, Open WebUI's chat-id header, the `user` field, or a
  hash of the first user message.
* `minion/channels/telegram.py` - optional Telegram bot (long polling; inline buttons for approvals).
  OpenClaw's own channels (WhatsApp, Slack, Discord, ...) reach Minion through the gateway's
  `minion_ask` tool.
* `minion/web/` - single-page dashboard (Hebrew/RTL aware): chat with voice input/output and
  a hands-free voice mode, agent picker (Minion or a specific harness), live run cards (tool
  calls, approvals), desktop viewer, suggestions ("Build it"), servers & registry, tools/workshop,
  agents/harnesses, automations, evolution & updates, memory & skills, usage/budget,
  settings/setup (paste the Anthropic key on first run).
* `minion/cli.py` - `minion` CLI talking to the API (`chat`, `ask`, `servers`, `tools`, `agents`,
  `update`, `status`).

## 6. Safety model

* The Docker socket gives Minion root-equivalent power on the host: run it on a machine you
  control, keep `/api` and `/mcp` behind the tokens, and expose port 8700 only over TLS/VPN.
* The brain never sees secret values; logs shown to it are redacted.
* Self-modification: worktree → checks → health-checked restart → automatic rollback.
  `MINION_EVOLVE_MODE=approve` requires a human to approve every code change.
* Shared catalog items reach other installations only through the upstream repo; the default
  `MINION_CONTRIBUTE_MODE=pr` keeps a human review step in front of everyone else.

### 5.11 REST API contract (`minion/api/`)

Public: `GET /health` → `{ok, version, uptime_s}`; `GET /api/setup/status` →
`{needs_api_key, persona_name, version}`; `POST /api/update/webhook` (GitHub HMAC
`X-Hub-Signature-256` with `MINION_GITHUB_WEBHOOK_SECRET`).

Everything else requires the admin token (`Authorization: Bearer`, cookie `minion_token`, or
`?token=`). JSON in/out; errors are `{"detail": "..."}` with a 4xx/5xx status.

| Area | Endpoints |
|---|---|
| auth/setup | `POST /api/login {token}` (sets cookie) · `POST /api/logout` · `POST /api/setup {anthropic_api_key}` |
| status | `GET /api/status` → `{version, uptime_s, model, persona_name, docker, servers, tools, agents, desktop, usage, update, active_runs, pending_approvals, new_suggestions}` · `GET /api/events?prefix=` (SSE of bus events) |
| settings | `GET /api/settings` (effective, non-secret) · `PATCH /api/settings {persona_name, persona_style, language, model, effort, autonomy, monthly_budget_usd, approvals, evolve_mode, update_mode, contribute_mode}` (stored in kv `settings.overrides`, applied live) |
| chat | `POST /api/chat {message, session_id?, target?}` → `{run_id, session_id}` · `GET /api/runs?active=1` · `GET /api/runs/{id}/events?after=N` (SSE; each `data:` is one brain event with `seq`) · `POST /api/runs/{id}/cancel` |
| sessions | `GET /api/sessions` · `GET /api/sessions/{id}` → `{session, messages: [{role, text, tools: [...], created_at}]}` · `DELETE /api/sessions/{id}` · `POST /api/sessions/{id}/feedback {rating, comment}` |
| approvals | `GET /api/approvals?status=pending` · `POST /api/approvals/{id} {decision: "approve"\|"deny", remember: bool}` |
| suggestions | `GET /api/suggestions?status=` · `POST /api/suggestions/{id}/build` → `{run_id, session_id}` · `POST /api/suggestions/{id}/dismiss` |
| MCP | `GET /api/servers` → `[{spec, status}]` · `POST /api/servers` (ServerSpec) · `PATCH /api/servers/{name} {enabled}` · `DELETE /api/servers/{name}` · `POST /api/servers/{name}/restart` · `GET /api/registry/search?q=` · `POST /api/registry/install {name, server_name?, env?}` · `GET /api/tools` · `POST /api/tools/call {name, arguments}` |
| workshop | `GET /api/workshop/tools` · `GET /api/workshop/tools/{file}` · `PUT /api/workshop/tools/{file} {code, scope, share}` · `DELETE /api/workshop/tools/{file}?scope=` |
| agents | `GET /api/agents/templates` · `GET /api/agents` · `POST /api/agents {template, name?, overrides?}` · `POST /api/agents/{name}/start\|stop\|upgrade` · `DELETE /api/agents/{name}` · `GET /api/agents/{name}/logs` · `POST /api/agents/{name}/send {message}` |
| desktop | `GET /api/desktop` · `POST /api/desktop/start` · `POST /api/desktop/stop` · `GET /api/desktop/screenshot` (image/png) · `/desktop/vnc/{path}` HTTP + WebSocket proxy to noVNC |
| containers | `GET /api/containers` · `GET /api/containers/{name}/logs?tail=` |
| automations | `GET /api/schedules` · `POST /api/schedules {name, cron, prompt}` · `PATCH /api/schedules/{id} {enabled}` · `DELETE /api/schedules/{id}` · `POST /api/schedules/{id}/run` |
| goals | `GET /api/goals` · `POST /api/goals {text}` · `PATCH /api/goals/{id} {status}` |
| memory/skills | `GET /api/memory?q=` · `POST /api/memory {kind, content, tags}` · `DELETE /api/memory/{id}` · `GET /api/skills` · `GET /api/skills/{name}` |
| secrets | `GET /api/secrets` (names only) · `PUT /api/secrets/{name} {value, description}` · `DELETE /api/secrets/{name}` |
| evolution | `GET /api/evolve/history` · `GET /api/evolve/proposals` · `POST /api/evolve/proposals/{id}/approve\|reject` · `POST /api/evolve/rollback {commit?}` · `POST /api/improve/run` · `POST /api/scout/run` |
| update | `GET /api/update` · `POST /api/update/check` · `POST /api/update/apply` |
| sharing | `GET /api/contributions` |
| usage | `GET /api/usage?period=day\|month` |

The web UI is served at `/` (static files from `minion/web/`), the Open WebUI front-end (when
deployed) on `MINION_CHAT_UI_PORT`, the OpenAI-compatible API at `/v1`, the MCP gateway at `/mcp`.
