# Hermes Agent (NousResearch/hermes-agent): integration research for Minion

**Bottom line:** there is an official Docker image, `nousresearch/hermes-agent`. Run it with `gateway run` and the built-in OpenAI-compatible API server turned on, on port 8642. Minion writes `/opt/data/config.yaml` and `/opt/data/.env` before the first boot, sends work to `POST /v1/runs`, and reads results from SSE events or by polling.

I tested this live with image `v0.21.6` (`docker run … --version` prints `Hermes Agent v0.21.6 (2026.9.24) · upstream a28a5d03`, Python 3.14.7). The test used a bearer-token streamable-HTTP MCP server at `http://minion:8700/mcp`. These worked:
- the bearer header filled in from `${VAR}`
- tool registration
- dynamic `tools/list_changed` refresh
- config hot-reload
- the `/v1/runs` lifecycle

One thing I could not test: a full LLM turn. The sandbox's TLS-intercepting proxy blocked `api.anthropic.com` from inside the container. That part is UNVERIFIED end to end, though I confirmed the agent resolves `provider=anthropic base_url=https://api.anthropic.com model=claude-sonnet-4-6`.

**Sources.** Repo cloned at commit `89af8eac9a2d356568f2bb193cc1126079e42a9e` (2026-10-08). Below, `R/` means `https://github.com/NousResearch/hermes-agent/blob/89af8eac9a2d356568f2bb193cc1126079e42a9e/`. Docs pages also live at `https://hermes-agent.nousresearch.com/docs/<same path without website/docs and .md>`; I checked that three of them return 200.

---

## 1. Installation and running headless in Docker

**Official image:** `nousresearch/hermes-agent`, multi-arch amd64 and arm64.
- Source: Docker Hub API `https://hub.docker.com/v2/repositories/nousresearch/hermes-agent/tags`.
- Tags as of 2026-10-08:
  - `v0.21.6`: newest, pushed 2026-10-08. This is the one I tested.
  - `latest`: pushed 2026-09-24, digest `sha256:d4da4a40…`.
  - `main`: development builds.
  - `v2026.9.24` and older calendar tags. The latest git tag is `v2026.9.24`.
  - `-desktop` variants: these add a VNC desktop.
- There is **no `stable` tag** on Docker Hub, even though the docs mention one. Pin `v0.21.6` or a digest.
- Image size is about 1.1 GB compressed.

**What the image contains** (`R/Dockerfile`, `R/website/docs/user-guide/docker.md`):
- Debian 13.4, Python 3.14 venv at `/opt/hermes/.venv`, Node, full Chromium, ffmpeg, ripgrep, git, `docker-cli`.
- s6-overlay as PID 1.
- `ENTRYPOINT ["/opt/hermes/docker/entrypoint-dispatch.sh"]`, `CMD []`.
- `ENV HERMES_HOME=/opt/data`, and `VOLUME /opt/data`.
- Runtime user `hermes` (UID 10000). You can remap it with `HERMES_UID`/`HERMES_GID` (aliases `PUID`/`PGID`). Do **not** use `docker run --user`; the image rejects it.

**Data directory:** `/opt/data` is the container's `~/.hermes` and the **only volume needed**. It holds:
- `.env`, `config.yaml`, `SOUL.md`, `auth.json`
- `sessions/`, `state.db` (SQLite in WAL mode), `memories/`, `skills/`, `cron/`, `hooks/`, `logs/`, `home/` (HOME for tool subprocesses), `profiles/`

The application tree `/opt/hermes` is read-only. Self-improvement in the image is limited to skills, memory, plugins and config under `/opt/data` (docker.md, "Immutable install tree").

**First boot** (`R/docker/stage2-hook.sh`, lines 432–530, verified live):
- Seeds `.env` from `.env.example`, `config.yaml` from `cli-config.yaml.example`, and `SOUL.md`, **only if those files are missing**.
- If `API_SERVER_KEY` is not in the container environment, it generates a random one and **appends it to `/opt/data/.env`**. Because of this, the API server starts on `127.0.0.1:8642` by default.
- Runs config-schema migrations. Skip them with `HERMES_SKIP_CONFIG_MIGRATION=1`.
- Syncs 58 bundled skills into `/opt/data/skills`.

**Commands** (docker.md):
```sh
docker run -d --name hermes --restart unless-stopped -v ~/.hermes:/opt/data -p 8642:8642 nousresearch/hermes-agent gateway run
docker run -it --rm -v ~/.hermes:/opt/data nousresearch/hermes-agent setup   # interactive wizard (not needed if you template config)
```
- `gateway run` runs under s6 supervision: it restarts on crash, and the container's CMD becomes a heartbeat.
- To make the gateway the container's main process instead, use `--no-supervise` or `HERMES_GATEWAY_NO_SUPERVISE=1`.
- Use `--shm-size=1g` for the browser tools. Recommended resources are 2–4 GB RAM and 2 CPUs.
- Do not override `entrypoint:`. Without `/init`, nothing supervises processes and zombies are never reaped.

**Without Docker:** `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash` (`R/README.md`, line 40). The project requires Python `>=3.11,<3.15` (`R/pyproject.toml`). PyPI has a `hermes-agent` package at 0.19.0, but it is stale and I could not confirm it is official (UNVERIFIED). Use the image.

## 2. Config format and Anthropic

**Files** (configuration.md):
- `/opt/data/config.yaml` holds settings.
- `/opt/data/.env` holds secrets.
- `${VAR}` and `${env:VAR}` are expanded inside config.yaml. Bare `$VAR` is not expanded.

**Anthropic provider** (`R/website/docs/integrations/providers.md`, "Anthropic (Native)"; `R/cli-config.yaml.example`):
```yaml
model:
  provider: "anthropic"          # aliases: claude, claude-code
  default: "claude-sonnet-4-6"   # key may be `default` or `model`
```
- Environment variables:
  - `ANTHROPIC_API_KEY` (required)
  - `ANTHROPIC_BASE_URL` (optional)
  - `ANTHROPIC_TOKEN` (setup-token/OAuth override, not needed here)
- Anthropic model IDs in the curated list (`R/hermes_cli/models_catalog_static.py`, line 219): `claude-fable-5.1, claude-fable-5, claude-opus-5-5, claude-opus-5, claude-sonnet-5, claude-opus-4-8, claude-opus-4-7, claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5-20251001, …`
- Per-invocation CLI flags: `--provider anthropic -m <model>`.
- Do not leave the example's `base_url: https://openrouter.ai/api/v1` in the `model:` block. Template a clean `model:` block instead.

**Env precedence (important, verified in code):** `R/hermes_cli/env_loader.py` line 507 loads `/opt/data/.env` with `override=True`. So **values in `.env` beat `docker run -e`**. The docker.md statement that "-e flags override .env" is wrong for any key that is also in `.env`. stage2 warns about this for `API_SERVER_KEY`.

## 3. MCP client support

**Schema** (`R/website/docs/reference/mcp-config-reference.md`):
```yaml
mcp_servers:
  <name>:
    command: "npx"            # stdio
    args: ["-y", "pkg"]
    env: {KEY: "${KEY}"}
    cwd: "/path"              # optional
    # OR remote:
    url: "https://host/mcp"   # Streamable HTTP is the default; `transport: sse` for SSE
    headers: {Authorization: "Bearer ${TOKEN}"}
    enabled: true
    timeout: 300              # tool call timeout (s), default 300
    connect_timeout: 60
    keepalive_interval: 180   # HTTP default 180s
    protocol: auto            # auto|stateless|legacy
    skip_preflight: false
    lazy: false
    trust: full               # or untrusted -> write tools need approval
    supports_parallel_tool_calls: false
    tools: {include: [], exclude: [], resources: true, prompts: true}
```
- If a `${VAR}` used in a `url` or `headers` value is not set, the connection fails closed with an error naming the variable.

**Tool naming:**
- In code and as observed live, tools are named `mcp__<server>__<tool>`, for example `mcp__minion__echo`. The longer docs page (features/mcp.md) wrongly shows `mcp_<server>_<tool>`.
- Characters outside `[A-Za-z0-9_]` become `_`.
- Names are capped at 64 characters, using a hash suffix (`R/tools/mcp_tool_schema.py`, line 172).
- Each server also gets a toolset named `mcp-<server>`.

**Dynamic refresh with `tools/list_changed`: yes.**
- Code path:
  - `R/tools/mcp_tool_health.py`, lines 99–163: refresh on `ToolListChangedNotification`.
  - `R/tools/mcp_tool_agent.py`: refresh of a live agent's tool list.
  - `R/agent/turn_context.py`, line 544: `_refresh_mcp_tools_between_turns`, so new tools appear on the next turn of a live session.
- **Live test:** my server added a tool and pushed `notifications/tools/list_changed` over the standalone GET SSE stream. Within about 10 ms Hermes logged `received tools/list_changed notification` and `tools changed dynamically — added: mcp__minion__weather_lookup`.
- `prompts/list_changed` and `resources/list_changed` are ignored.
- Hermes does **not** implement the MCP 2026-07-28 `subscriptions/listen` mechanism (I grepped and found nothing). Notifications only arrive on legacy `initialize`-handshake sessions, which is what `protocol: auto` uses first.
- What I saw on the wire from Hermes (mcp SDK 2.0.0 client, protocol `2025-11-25`):
  1. `HEAD /mcp` (405 is tolerated)
  2. `GET /mcp` without SSE accept (400 is tolerated)
  3. `POST initialize`
  4. `GET` SSE stream
  5. `tools/list`

**Config hot-reload, verified:** the running gateway watches `config.yaml`. After `hermes config set mcp_servers.minion2.url …`, the new server was connected in about 15 s (`MCP servers reconciled with config (default): added=['minion2']`). A failed connection is retried at 30 s, doubling up to 10 min. In interactive sessions you can also use `/reload-mcp`.

**Notes for Minion's own gateway** (mcp 2.3.0 Python SDK, verified):
- `FastMCP` was renamed to `mcp.server.mcpserver.MCPServer`.
- Its streamable app does **not** advertise `tools.listChanged: true` by default. Pass `NotificationOptions(tools_changed=True)` to `create_initialization_options`. I tested with `true`. Hermes's handler does not appear to check the flag, but that is inferred from code only.
- Mark read-only tools with `readOnlyHint: true`. After a session expires, only those are replayed; write-capable tools return `outcome_uncertain`.

## 4. Programmatic access

**API server** (`R/website/docs/user-guide/features/api-server.md`; `R/gateway/platforms/api_server.py`, line 1718; `R/gateway/platforms/api_server_runs.py`, line 234):

How it is enabled:
- The gateway's `api_server` platform starts whenever `API_SERVER_KEY` is usable: **16 or more characters and not a placeholder**. The docs say 8; the code enforces 16 (`R/gateway/platforms/api_server.py`, around line 4440; `R/gateway/config.py`, line 544).

| Variable | Default | Notes |
|---|---|---|
| `API_SERVER_ENABLED` | | Set to `true`; docs say it is required. |
| `API_SERVER_HOST` | `127.0.0.1` | Use `0.0.0.0` so other containers can reach it. |
| `API_SERVER_PORT` | `8642` | |
| `API_SERVER_KEY` | | Bearer token, 16+ characters. |
| `API_SERVER_CORS_ORIGINS` | | |
| `API_SERVER_MODEL_NAME` | | |

- config.yaml equivalent: `gateway.api_server.{enabled,port,host,key,cors_origins,model_name,max_concurrent_runs (default 10; 429 when exceeded)}`.

Endpoints (all need `Authorization: Bearer <key>` except `/health`):
- Health: `GET /health` and `/v1/health` return `{"status":"ok","platform":"hermes-agent","version":"0.21.6"}` (verified). `GET /health/detailed` also exists.
- OpenAI-compatible:
  - `GET /v1/models`: returns `hermes-agent` (verified).
  - `POST /v1/chat/completions`: stateless. Send the `X-Hermes-Session-Id` header for continuity.
  - `POST /v1/responses`: supports `previous_response_id` and `conversation`.
  - `GET` and `DELETE /v1/responses/{id}`.
- Runs:
  - `POST /v1/runs` with body `{input, session_id?, instructions?, conversation_history?, previous_response_id?, model?, provider?}`. Returns **202** `{"run_id","status":"started","replayed":false}`. Supports an `Idempotency-Key` header; a replay returns `Idempotency-Replayed: true` (verified).
  - `GET /v1/runs/{id}`: `status` is `queued`, `running`, `completed`, `failed`, `cancelled` or `interrupted`. The response also carries `output`, `usage`, `runtime`, `completed`, `partial`, `interrupted`, `last_event`. Stopping and polling were verified.
  - `GET /v1/runs/{id}/events`: SSE frames shaped `id: <seq>\ndata: {"event":…, "run_id":…, "timestamp":…, "seq":…}`. Resume with `Last-Event-ID` or `?last_seq=`. There is a `: keepalive` comment every 10 s. Event names: `run.started`, `run.queued`, `message.started`, `message.delta`, `message.interim`, `reasoning.available`, `tool.started`, `tool.progress`, `tool.completed`, `tool.failed`, `approval.request`, `approval.responded`, `subagent.start`, `subagent.complete`, `run.steered`, `run.stopping`, `run.completed`, `run.failed`, `run.cancelled`, `run.interrupted`.
  - `POST /v1/runs/{id}/stop` returns `{"status":"stopping"}` and the run then settles as `cancelled` (verified).
  - `POST /v1/runs/{id}/steer` and `POST /v1/runs/{id}/approval`.
- Sessions: `GET`/`POST /api/sessions`, `GET`/`PATCH`/`DELETE /api/sessions/{id}`, `/messages`, `/fork`, `POST /api/sessions/{id}/chat` (synchronous; body `{"input": …}` per the docs example), `/chat/stream` (SSE).
- Discovery: `GET /v1/skills`, `GET /v1/toolsets` (this does **not** list MCP toolsets, observed), `GET /v1/capabilities` (verified).
- Jobs: `/api/jobs` CRUD.

**One-shot CLI** (`R/website/docs/reference/cli-commands.md`; flags confirmed with `hermes chat --help` in the image):
- `docker exec minion-hermes hermes -z "<prompt>" [--usage-file /opt/data/cache/usage.json] [-m M --provider P]`
  - stdout contains **only the final answer**.
  - Approvals are bypassed automatically (it sets `HERMES_YOLO_MODE=1`).
  - Exit codes: `0` success, `2` failed or partial, `1` produced no text, `130` interrupted.
- `docker exec minion-hermes hermes chat --oneshot -q "<prompt>" --format stream-json --yolo --source tool [--max-turns N] [--run-budget SEC] [-s skill] [-t toolsets]`
  - Output is JSONL. Event `type`s are `system`/`init` (verified), `text`, `tool_use`, `tool_result`, and a final `result` with `{session_id, exit_code, text, tokens, duration_ms, error?}`.
  - A non-TTY `docker exec` (no `-t`) implies one-shot.
  - For untrusted text, use `--query-file -` with `docker exec -i`.
- One-shot runs **hide `skill_manage`**, so no self-improvement happens in them (`R/agent/oneshot_footprint.py`). Use the API server for long-lived, learning sessions.
- I saw `--run-budget 15` fail to stop a run within 40 s while the provider was unreachable. Its effect during provider-outage retries is UNVERIFIED.

## 5. Skills and self-improvement

- Skills are `SKILL.md` files (agentskills.io format with YAML frontmatter) under **`/opt/data/skills/<category>/<name>/`**, with optional `references/`, `templates/`, `scripts/`, `assets/`. Source: `R/website/docs/user-guide/features/skills.md`.
- The agent writes them with the `skill_manage` tool. Actions: `create`, `patch`, `delete`, `write_file`, `remove_file`.
- Config keys:
  - `skills.external_dirs: [...]`: extra directories scanned for skills, and editable if writable.
  - `skills.create_dir: /path`: where new skills are written. This could be a Minion-shared volume.
  - `skills.write_approval: false`: the default. When `true`, writes are staged under `/opt/data/pending/skills/`.
- Memory lives in `/opt/data/memories/MEMORY.md` (2,200 characters) and `USER.md` (1,375 characters). It is snapshotted into the system prompt when a session starts.
- A background review fork runs after turns and can stage skill and memory updates (`auxiliary.background_review`).
- The curator (`curator.*`, every 7 days by default) prunes and archives agent-created skills. Its LLM consolidation step is off unless `curator.consolidate: true`.
- `SOUL.md` sets the agent's identity.
- In the image, core code under `/opt/hermes` cannot be modified.

## 6. Gotchas for unattended container runs

1. **No setup wizard is needed.** If `ANTHROPIC_API_KEY` (or another provider key) is in the environment or `.env`, `_has_any_provider_configured()` passes. Without a TTY and without a key, `hermes chat` exits 1 with guidance; it never hangs (`R/hermes_cli/main.py`, lines 1092 and 1662). Pre-writing `config.yaml` and `.env` is enough.
2. **Approvals:** the defaults in image v0.21.6 are `approvals.mode: smart`, `unattended_mode: deny` (this covers api_server, webhook and cron), and `single_query_mode: deny` (verified with the image's `DEFAULT_CONFIG`). Dangerous commands are therefore **refused** in API runs unless you set `approvals.mode: "off"` (same as `HERMES_YOLO_MODE`) or `unattended_mode: approve`. `approvals.deny` globs still apply under yolo.
3. **`.env` overrides `-e`.** Also, stage2 writes a random `API_SERVER_KEY` into `.env` on first boot unless `API_SERVER_KEY` was already in the container environment. After that, a different `-e API_SERVER_KEY` is shadowed. **Minion should write `.env` itself** and treat it as the source of truth.
4. **The main wrapper routes on the first argument.** If the first argument is an executable on PATH, it runs that directly. So `docker run IMG mcp test x` runs the **mcp SDK's own CLI** and fails with "typer is required" (verified). Use `docker run IMG hermes mcp …`. `docker exec <c> hermes …` is fine and drops to UID 10000 through a shim.
5. Gateway logs go to `docker logs` and to `/opt/data/logs/gateways/default/current`. Agent and MCP logs go to `/opt/data/logs/agent.log` and `errors.log`.
6. Never run two gateway containers on the same `/opt/data`. Use one container per agent, or profiles.
7. The API server warns that `0.0.0.0` combined with the `terminal.backend: local` default means unsandboxed shell access. The container is the sandbox: do not mount `docker.sock` (the image has `docker-cli`), and do not publish 8642 publicly.
8. If the provider is unreachable, runs keep retrying: `agent.api_max_retries` 3, then `agent.auto_recovery_cycles` 5 at 15/30/60/60/60 s. Lower these and use `/v1/runs/{id}/stop` for timeouts.
9. WAL SQLite: on NFS, SMB or virtiofs mounts, set `database.journal_mode: delete`, or use a named Docker volume.

---

## RECOMMENDED INTEGRATION

**Image:** use the official one, `nousresearch/hermes-agent:v0.21.6` (pin a digest in production). You only need a derived image to add apt packages:
```dockerfile
FROM nousresearch/hermes-agent:v0.21.6
USER root
RUN apt-get update && apt-get install -y --no-install-recommends <pkgs> && rm -rf /var/lib/apt/lists/*
# keep default ENTRYPOINT/CMD (s6 /init drops to uid 10000)
```

**`/opt/data/.env`** (Minion writes it with mode 0600 before first start):
```
ANTHROPIC_API_KEY={{anthropic_api_key}}
MINION_MCP_TOKEN={{mcp_bearer_token}}
API_SERVER_ENABLED=true
API_SERVER_HOST=0.0.0.0
API_SERVER_PORT=8642
API_SERVER_KEY={{hex32}}            # >=16 chars, e.g. secrets.token_hex(32)
```

**`/opt/data/config.yaml`** (this exact model and MCP block was tested live; the extra keys come from the docs):
```yaml
model:
  provider: anthropic
  default: "{{model|default('claude-sonnet-4-6')}}"   # e.g. claude-opus-5-5 / claude-sonnet-5

approvals:
  mode: "off"                 # container is the sandbox; alternative: smart + unattended_mode: approve
  unattended_mode: approve
  single_query_mode: approve
  deny: ["*rm -rf /opt/data*"]

agent:
  max_turns: 200
  run_budget_seconds: 1800
  api_max_retries: 2
  auto_recovery_cycles: 1

gateway:
  api_server:
    max_concurrent_runs: 4

mcp_servers:
  minion:
    url: "http://minion:8700/mcp"
    headers:
      Authorization: "Bearer ${MINION_MCP_TOKEN}"
    timeout: 300
    connect_timeout: 30
    keepalive_interval: 120    # below Minion's MCP session idle timeout (mcp SDK default 1800s)
    tools:
      resources: false
      prompts: false

skills:
  write_approval: false
  # create_dir: /opt/minion-skills   # optional shared volume for agent-created skills
```

**Start command** (bridge network; 8642 is reached by service name and is not published):
```sh
docker network create minion-net
docker volume create minion-hermes-data
# write config.yaml/.env into the volume (e.g. docker cp into a created-but-not-started container, or a helper container)
docker run -d --name minion-hermes --network minion-net --restart unless-stopped \
  -v minion-hermes-data:/opt/data --shm-size=1g --memory=4g --cpus=2 \
  nousresearch/hermes-agent:v0.21.6 gateway run
```
- Port: 8642/tcp (API server). Optional 9119 is the dashboard (needs `HERMES_DASHBOARD=1` and an auth provider); skip it.
- Readiness check: `GET http://minion-hermes:8642/health`.
- MCP check: `docker exec minion-hermes hermes mcp test minion` (verified output: `✓ Connected … Tools discovered: N`).

**How Minion sends tasks and reads results:**
1. `POST http://minion-hermes:8642/v1/runs`
   - Headers: `Authorization: Bearer $API_SERVER_KEY`, `Idempotency-Key: <task-uuid>`.
   - Body: `{"input": "<task>", "session_id": "minion-<task-or-thread-id>", "instructions": "<extra system guidance>"}`.
   - Response: `202 {"run_id": …}`.
2. Stream `GET /v1/runs/{run_id}/events` (SSE; parse `data:` JSON, skip lines starting with `:`, resume with `Last-Event-ID`) until `run.completed`, `run.failed`, `run.cancelled` or `run.interrupted`. Or poll `GET /v1/runs/{run_id}` until `status` is terminal. The result is in `output`, plus `usage` and `runtime`.
3. To cancel: `POST /v1/runs/{id}/stop`. To steer mid-run: `POST /v1/runs/{id}/steer`. History: `GET /api/sessions/{session_id}/messages`.
4. Reusing `session_id` keeps conversation context and lets Hermes learn skills and memory. One-shot `docker exec … hermes -z` gives plain stdout but no skill learning.
5. New tools appear automatically. Minion's MCP gateway pushes `notifications/tools/list_changed` on each Hermes session's standalone GET SSE stream (a legacy `initialize` session). Hermes re-lists tools and live agents pick them up on the next turn. Adding or removing whole MCP servers means editing `mcp_servers` in config.yaml (applied in about 15 s) or running `docker exec minion-hermes hermes config set mcp_servers.<name>.url …`.

**Test files** (scratch, safe to delete):
- `docs/research/drafts/ (not all copied) hermes/mcpsrv/server.py`: bearer-auth MCPServer with an `/admin/add` route that adds a tool and broadcasts list_changed.
- `docs/research/drafts/ (not all copied) hermes/data2/`: the tested config.yaml and `.env` (fake keys only).
- The repo clone is under `.../research/hermes/repo`.

The test containers and network have been removed. The image `nousresearch/hermes-agent:v0.21.6` is still pulled locally.