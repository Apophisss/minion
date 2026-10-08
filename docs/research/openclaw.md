# OpenClaw research report: running it headless under Minion

**Sources checked:** the live `openclaw/openclaw` repo at `main` commit `36bd762422b3` (2026-10-08, `package.json` version `2026.9.8`), docs.openclaw.ai (whose paths match `docs/*.md` in the repo), the GHCR tag API and the npm registry.

**Live tests:** I ran `ghcr.io/openclaw/openclaw:2026.9.8` in Docker against two stdlib-only Python mocks on a Docker bridge network:
- an MCP server at `http://minion:8700/mcp` that requires `Authorization: Bearer <token>`;
- an Anthropic Messages API at `http://mockanthropic:9000`.

The whole loop worked: HTTP request → OpenClaw → Anthropic `tool_use` → MCP `tools/call` on the gateway → final answer. Items marked **[VERIFIED-LIVE]** I ran myself; **UNVERIFIED** marks things I could not test.

Test files are in `docs/research/drafts/ (not all copied) openclaw/`: `mock/mock.py`, `state/`, `state2/` and `agent-json.json`. The repo clone is in `repo/`.

---

## 1. Running it in Docker headless

**Image** — source: https://docs.openclaw.ai/install/docker
- Main registry is `ghcr.io/openclaw/openclaw`. Docker Hub has a mirror at `openclaw/openclaw`.
- Moving tags: `latest`, `main`, `extended-stable`. Variants: `-slim` and `-browser` (Chromium baked in).
- Version tags are immutable. Weekly OS-refresh tags look like `2026.8.1-r20260820`.
- What I found on GHCR:
  - `latest` = `2026.9.9`, digest `sha256:7f10d5cc975a90b65192eaa099454fe33ce8ce2390806c61c65cd868e9ef730d`. The `slim` tag currently has the same digest.
  - `2026.9.8` = `sha256:d0ded1dd76939b2bf4d67ef2d13247b8b160aa5666331d4a0b0e58811182cbb8`. This is the version I tested.
  - Betas `2026.10.1-beta.1` and `-beta.2` exist.
  - npm `latest` = `2026.9.9`, `beta` = `2026.10.1-beta.2`.
  - Sources: `https://ghcr.io/v2/openclaw/openclaw/tags/list` and `npm view openclaw`.

**What the image contains** — [VERIFIED-LIVE] with `docker image inspect`; source: https://github.com/openclaw/openclaw/blob/main/Dockerfile
- Based on `node:24-bookworm-slim` with Node `24.21.0`. Runs as user `node` (uid 1000). Working directory `/app`.
- `ENTRYPOINT ["tini","-s","--","node","/app/docker-entrypoint.mjs"]`
- `CMD ["node","openclaw.mjs","gateway"]`
- `/usr/local/bin/openclaw` links to `/app/openclaw.mjs`, so `docker exec <c> openclaw ...` works.
- The built-in healthcheck runs `node dist/docker-healthcheck.js` every 3 minutes and hits `/healthz`.
- Directories created ahead of time, owned by `node`:
  - `/home/node/.openclaw`
  - `/home/node/.openclaw/workspace`
  - `/home/node/.config/openclaw`
- Optional build args:
  - `OPENCLAW_EXTENSIONS`
  - `OPENCLAW_IMAGE_APT_PACKAGES`
  - `OPENCLAW_IMAGE_PIP_PACKAGES`
  - `OPENCLAW_INSTALL_BROWSER=1`
  - `OPENCLAW_INSTALL_DOCKER_CLI=1` (adds the docker CLI, needed only for the agent sandbox)

**The container runs `openclaw doctor --fix --non-interactive` before the gateway starts** — [VERIFIED-LIVE]; source: https://github.com/openclaw/openclaw/blob/main/docker-entrypoint.mjs
- This happens for any foreground `gateway` command. Doctor rewrites the config file (details in §6).

**Repo compose file** — source: https://github.com/openclaw/openclaw/blob/main/docker-compose.yml
- Service `openclaw-gateway`, with environment:
  - `HOME=/home/node`
  - `OPENCLAW_HOME=/home/node`
  - `OPENCLAW_STATE_DIR=/home/node/.openclaw`
  - `OPENCLAW_CONFIG_PATH=/home/node/.openclaw/openclaw.json`
  - `OPENCLAW_CONFIG_DIR=/home/node/.openclaw`
  - `OPENCLAW_WORKSPACE_DIR=/home/node/.openclaw/workspace`
  - `OPENCLAW_GATEWAY_PORT=18789`
  - `OPENCLAW_GATEWAY_TOKEN`
  - `OPENCLAW_DISABLE_BONJOUR`
  - `TZ`
- Volumes:
  - `${OPENCLAW_CONFIG_DIR}:/home/node/.openclaw`
  - `${OPENCLAW_WORKSPACE_DIR}:/home/node/.openclaw/workspace`
  - `${OPENCLAW_AUTH_PROFILE_SECRET_DIR}:/home/node/.config/openclaw`
- Ports: `18789` (gateway, HTTP and WebSocket on one port), `18790` (bridge), `3978` (MS Teams). Only 18789 matters for Minion.
- Command: `["node","dist/index.js","gateway","--bind","lan","--port","18789"]`
- Hardening: `cap_drop: [NET_RAW, NET_ADMIN]`, `no-new-privileges`, `init: true`, `restart: unless-stopped`, and `extra_hosts: host.docker.internal:host-gateway`.

**Gateway start command and bind address** — source: https://docs.openclaw.ai/gateway/config-gateway
- Command: `openclaw gateway [--bind lan] [--port 18789]`.
- Port precedence: `--port` > `OPENCLAW_GATEWAY_PORT` > `gateway.port` > `18789`.
- The default bind is `loopback`. Over Docker bridge networking that makes it unreachable from other containers, so set `gateway.bind: "lan"` or pass `--bind lan`. [VERIFIED-LIVE] Setting `bind: "lan"` in config with the image's default CMD worked.
- Any non-loopback bind requires auth.
- `gateway.mode: "local"` is required, or the gateway refuses to start.

**Onboarding without the wizard** — source: https://docs.openclaw.ai/cli/onboard
- The wizard is not needed at all. [VERIFIED-LIVE] A hand-written `openclaw.json` plus environment variables boots cleanly with no onboarding.
- If you want the official non-interactive onboarding anyway:
  ```
  openclaw onboard --non-interactive --accept-risk --skip-health --mode local \
    --auth-choice apiKey --anthropic-api-key "$ANTHROPIC_API_KEY" \
    --secret-input-mode ref --gateway-auth token --gateway-token-ref-env OPENCLAW_GATEWAY_TOKEN \
    --skip-channels --no-install-daemon
  ```
  - The Anthropic API-key auth choice id is `apiKey`. Source: `extensions/anthropic/openclaw.plugin.json`, entry `"choiceId": "apiKey"`, `"cliFlag": "--anthropic-api-key"`. The other Anthropic choices are `anthropic-cli` and `setup-token`.
  - `OPENCLAW_SKIP_ONBOARDING=1` only applies to `scripts/docker/setup.sh`.

**Gateway auth token** — sources: https://docs.openclaw.ai/gateway/openai-http-api and https://docs.openclaw.ai/gateway/config-secrets-env
- Set `gateway.auth.mode: "token"`. The token comes from `gateway.auth.token` or the `OPENCLAW_GATEWAY_TOKEN` env var.
- [VERIFIED-LIVE] The SecretRef form `token: {source:"env",provider:"default",id:"OPENCLAW_GATEWAY_TOKEN"}` works and triggers no warning.
- The string form `"${OPENCLAW_GATEWAY_TOKEN}"` also works, but doctor then warns about a "plaintext secret-bearing config field".
- Clients send `Authorization: Bearer <token>`. A wrong token returns 401 [VERIFIED-LIVE].

**Health endpoints (no auth)** — [VERIFIED-LIVE]
- `GET /healthz` returns `{"ok":true,"status":"live"}`.
- `GET /readyz` returns `{"ready":true}`.
- `GET /startupz` also exists.

## 2. Config file location and Anthropic setup

**Location and format** — source: https://docs.openclaw.ai/gateway/configuration
- `~/.openclaw/openclaw.json`, which is `/home/node/.openclaw/openclaw.json` in the container. Override with `OPENCLAW_CONFIG_PATH`.
- Format is JSON5. Validation is strict: an unknown key stops the gateway from booting.
- The gateway watches the file and hot-reloads it. `gateway.reload.mode` defaults to `"hybrid"`. Changes to the auth mode still need a restart.
- `${UPPER_CASE_VAR}` substitution works in any string, including `${VAR:-default}`. Use `$${VAR}` for a literal.
- `$include` lets you split config into separate files (§6 and §7).

**Anthropic key** — sources: https://docs.openclaw.ai/providers/anthropic and `extensions/anthropic/openclaw.plugin.json`
- The `anthropic` provider reads the env vars `ANTHROPIC_API_KEY` and `ANTHROPIC_OAUTH_TOKEN`. [VERIFIED-LIVE] `x-api-key` from the env var reached the mock.
- In-config alternative: `env: { vars: { ANTHROPIC_API_KEY: "..." } }`.
- Optional: `ANTHROPIC_ADMIN_KEY` turns on cost reporting.

**Model selection** — source: https://docs.openclaw.ai/gateway/config-agents/models
- Format is `provider/model`:
  ```json
  { "agents": { "defaults": { "model": { "primary": "anthropic/claude-opus-5-5", "fallbacks": ["anthropic/claude-sonnet-5-5"] }, "utilityModel": "anthropic/claude-haiku-5-5" } } }
  ```
- Anthropic model ids in the bundled catalog:
  - `claude-opus-5-5` (fresh-setup default)
  - `claude-sonnet-5-5`
  - `claude-haiku-5-5`
  - `claude-opus-5`
  - `claude-sonnet-5`
  - `claude-fable-5-1`
  - `claude-fable-5`
  - `claude-opus-4-8`
  - `claude-opus-4-7`
  - `claude-sonnet-4-6`
  - `claude-opus-4-6`
- CLI: `openclaw models set anthropic/claude-opus-5-5`.
- Per request: the `x-openclaw-model` header overrides the model.
- [VERIFIED-LIVE] The log line reads `agent model: anthropic/claude-opus-5-5 (thinking=medium)`.
- The base URL can be overridden with `models.providers.anthropic.baseUrl`. That is how I pointed it at the mock; it uses the `anthropic-messages` wire format.

## 3. MCP support

OpenClaw consumes external MCP servers natively. Server definitions go under `mcp.servers.<name>`. Sources: https://docs.openclaw.ai/tools/mcp, https://docs.openclaw.ai/cli/mcp/transports and https://docs.openclaw.ai/gateway/config-extensions

**Remote streamable HTTP server with a bearer token** — [VERIFIED-LIVE]
```json
"mcp": { "servers": { "minion": {
  "url": "http://minion:8700/mcp",
  "transport": "streamable-http",
  "headers": { "Authorization": "Bearer ${MINION_MCP_TOKEN}" },
  "connectionTimeoutMs": 10000, "requestTimeoutMs": 300000,
  "supportsParallelToolCalls": true,
  "toolFilter": { "include": ["*"] }
} } }
```
- `transport` must be `"streamable-http"`. If it is omitted, OpenClaw falls back to `sse`.
- `type: "http"` is accepted as an alias by `openclaw mcp set` and normalised by doctor.
- Other fields: `enabled`, `auth: "oauth"` with `oauth: {...}`, `sslVerify`, `clientCert`, `clientKey`, `toolFilter.include` / `toolFilter.exclude`.
- `requestTimeoutMs` defaults to 60s.
- `mcp.sessionIdleTtlMs` is optional.
- At most 256 MCP runtimes per gateway.

**Stdio server** — documented, not run:
```json
"local": { "command": "npx", "args": ["-y","@modelcontextprotocol/server-memory"], "env": {"API_BASE":"..."}, "cwd": "/srv/x" }
```
- Interpreter-hijack env keys such as `NODE_OPTIONS`, `LD_*` and `PYTHONSTARTUP` are dropped.
- The command must exist inside the OpenClaw container.

**CLI management** — source: https://docs.openclaw.ai/cli/mcp/registry; [VERIFIED-LIVE] via `docker exec`
- Commands:
  - `openclaw mcp add <name> --url ... --transport streamable-http --header ...`
  - `openclaw mcp set <name> '<json>'`
  - `openclaw mcp list|show|status --verbose|doctor --probe|probe <name> --json|unset <name>`
- `mcp set minion2 '{...}'` was picked up by the running gateway with no restart: log shows `[reload] config hot reload applied (mcp.servers.minion2)`, and the next turn had both `minion__*` and `minion2__*` tools.

**What I observed on the wire** — [VERIFIED-LIVE]
- Client name `openclaw-bundle-mcp`, protocol version `2025-11-25`.
- Headers: `Accept: application/json, text/event-stream`. It sends `initialize`, then `notifications/initialized`, then optionally `GET /mcp` for SSE (a 405 is tolerated), then `tools/list`, then `tools/call`. It honours `Mcp-Session-Id` and sends `DELETE` at the end.
- Private Docker IPs (172.x) are allowed.
- **Tools reach the model as `<server>__<tool>`**, for example `minion__minion_echo`.
- **Tool Search is on by default, so MCP tools are hidden behind `tool_search` / `tool_describe` / `tool_call`.** With the default, the model saw only 12 tools and none from MCP. With `tools.toolSearch: false` it saw 43 tools including `minion__minion_echo`. Source: https://docs.openclaw.ai/tools/tool-search
- MCP tools are available in the `coding` and `messaging` tool profiles, but hidden in `minimal`. Source: https://docs.openclaw.ai/gateway/config-tools/tool-policy
- No approval prompt appeared on the HTTP path for the MCP call.

**Alternatives**
- A bundled `mcporter` skill reads `config/mcporter.json`. It is not needed, and doctor disabled it because the binary is missing.
- `openclaw mcp serve` does the reverse: it exposes OpenClaw conversations to an MCP client over stdio. Source: https://docs.openclaw.ai/cli/mcp/serve

## 4. Programmatic access

**`POST /v1/chat/completions`** (OpenAI-compatible) — [VERIFIED-LIVE]; source: https://docs.openclaw.ai/gateway/openai-http-api
- Off by default. Enable with `gateway.http.endpoints.chatCompletions.enabled: true`.
- `model` names an agent: `openclaw/default`, `openclaw/<agentId>`, or `openclaw`.
- Session handling:
  - Stateless by default.
  - `"user": "<id>"` gives a stable session.
  - The `x-openclaw-session-key: <key>` header sets an explicit session. [VERIFIED-LIVE] `minion:task-42` became session `agent:main:minion:task-42`. The prefixes `subagent:`, `cron:` and `acp:` are reserved.
- `stream: true` returns SSE `chat.completion.chunk` events and then `data: [DONE]` [VERIFIED-LIVE].
- The reply is in `choices[0].message.content` [VERIFIED-LIVE: `"FINAL ANSWER: ECHO:hello-from-openclaw"`].
- If the HTTP client disconnects, the agent run is cancelled.

**`POST /v1/responses`** — [VERIFIED-LIVE]; source: https://docs.openclaw.ai/gateway/openresponses-http-api
- Enable with `gateway.http.endpoints.responses.enabled: true`.
- Takes `input` as a string or items, plus `previous_response_id` and `user`.
- The reply is in `output[0].content[0].text`, with `status: "completed"`.

**`GET /v1/models`** lists `openclaw`, `openclaw/default` and `openclaw/main` [VERIFIED-LIVE].

**`POST /tools/invoke`** is always on. Body: `{"tool":"...","args":{},"sessionKey":"main"}`. It invokes a single tool directly. Source: https://docs.openclaw.ai/gateway/tools-invoke-http-api

**Security:** the bearer token gives full operator (owner) access. Keep the port on the internal network only.

**CLI one-shot via `docker exec`** — [VERIFIED-LIVE]; source: https://docs.openclaw.ai/cli/agent
```
docker exec <c> openclaw agent --agent main --session-key <key> --message "<task>" --json [--timeout 1800] [--model anthropic/...]
```
- Output shape: `{"runId", "status":"ok", "summary":"completed", "result":{"payloads":[{"text","mediaUrl"}], "meta":{"finalAssistantVisibleText", "toolSummary":{"calls","tools","failures"}, "executionTrace", "stopReason"}}}`.
- Exit codes: 0 for ok, 1 for error or timeout.
- `--message-file -` reads the message from stdin.
- `openclaw agent exec` is a separate isolated embedded one-shot. It refuses to run while a gateway owns the same state directory.

**WebSocket protocol:** this is the full control plane, with handshake, roles/scopes and device identity. Source: https://docs.openclaw.ai/gateway/protocol. Not tested. HTTP is much simpler for Minion.

## 5. Skills and plugins directories

**Skills** — [VERIFIED-LIVE] for both directories; source: https://docs.openclaw.ai/tools/skills
- Each skill is a directory containing `SKILL.md` with YAML frontmatter (`name`, `description`).
- Precedence, highest first:
  1. `<workspace>/skills` (shown as source `openclaw-workspace`)
  2. `<workspace>/.agents/skills`
  3. `~/.agents/skills`
  4. `<state-dir>/skills` = `/home/node/.openclaw/skills` (shown as `openclaw-managed`)
  5. `<state-dir>/agents/<id>/agent/workshop-skills`
  6. Bundled skills in `/app/skills`
  7. Anything in `skills.load.extraDirs`
- Dropping a skill into `/home/node/.openclaw/skills/minion-hello/SKILL.md` or `/home/node/.openclaw/workspace/skills/minion-ws/SKILL.md` showed up as "ready" in `openclaw skills list` without a restart.

**Plugins** — source: https://docs.openclaw.ai/gateway/config-extensions
- Loaded from `~/.openclaw/extensions`, `<workspace>/.openclaw/extensions` and `plugins.load.paths`.
- Install with `openclaw plugins install <pkg>`.

## 6. Resources and gotchas for unattended Docker

**Resource numbers**
- **Node:** engines `>=24.16.0 <25 || >=26.1.0`; the image ships Node 24.21.0.
- **Image size:** about 4.97 GB on disk, 1.24 GB compressed.
- **Memory:** about 1.37 GiB at idle [VERIFIED-LIVE with `docker stats`]. A local source build needs at least 6 GB RAM.
- **Startup:** about 25–30 s from `docker run` until `/readyz` succeeds, because doctor runs first.

**Gotchas, in rough order of impact**

1. **Doctor rewrites `openclaw.json` on every start** [VERIFIED-LIVE].
   - It strips JSON5 comments.
   - It adds `agents.entries.main`, `plugins.entries.anthropic.enabled`, `skills.entries.<x>.enabled:false` for skills whose binaries are missing, `wizard` and `meta`.
   - It keeps a `.bak` ring and `.last-good`. `${VAR}` references are preserved.
   - So Minion should read-modify-write the file, use `openclaw config set` / `openclaw mcp set`, or own a separate `$include` file.
   - [VERIFIED-LIVE] `mcp: {"$include":"./minion-mcp.json5"}` hot-reloads, survives a restart with doctor, and `openclaw mcp set` writes through into the included file.
2. **Mount the directory, never the single file.** Bind-mounting only `openclaw.json` makes doctor fail with `EBUSY ... rename ... openclaw.json`, and the container exits with code 1 [VERIFIED-LIVE].
3. **The host directory must be owned by uid 1000.** OpenClaw sets its files to mode 0600.
4. **Bind address and auth:** use `bind: "lan"` together with token auth. The image default CMD binds to loopback unless config overrides it. The gateway auto-seeds `controlUi.allowedOrigins`.
5. **Set `tools.toolSearch: false`** if you want MCP tools sent to the model directly (§3).
6. **Memory search defaults to OpenAI embeddings** and warns when there is no `OPENAI_API_KEY`. Set `memory: {search: {provider: "none"}}` to get full-text-only recall with no warning [VERIFIED-LIVE]. Source: https://docs.openclaw.ai/reference/memory-config
7. **Stale lease after a hard kill.** After `docker rm -f` or SIGKILL, the SQLite lease `state_leases(scope='gateway-owner')` stays valid for **5 minutes after the last heartbeat**. A new container on the same state directory in that window exits with code 1: "Another Gateway owner lease is still active for this state directory" [VERIFIED-LIVE on 2026.9.8; the docs claim about 90 s].
   - A graceful `docker stop` releases the lease. Idle shutdown took 215 ms, and an immediate restart succeeded.
   - Use `restart: unless-stopped` and a `stop_grace_period` of at least 60 s. The internal drain budget is up to 330 s.
   - Run only one gateway per state directory. Source: https://docs.openclaw.ai/gateway/gateway-lock
8. **Shell access without prompts.** Host `exec` defaults to `mode=full`, meaning no approval prompts, and the sandbox is off. The agent's shell runs inside the OpenClaw container. `openclaw exec-policy show` reports `auto · full · no approval prompts` [VERIFIED-LIVE]. Source: https://docs.openclaw.ai/tools/exec
9. **Long failure paths.** A real provider error took 2 min 50 s before returning HTTP 408 in my sandbox. The underlying cause was `SELF_SIGNED_CERT_IN_CHAIN` from this sandbox's TLS-intercepting proxy, which is an environment artifact. Minion should use generous timeouts or streaming. **UNVERIFIED:** a real api.anthropic.com call, because of that proxy. The Anthropic wire format was verified against the mock.
10. **Bonjour:** it auto-disables inside containers. Set `OPENCLAW_DISABLE_BONJOUR=1` to be explicit.
11. **Rebuild warnings:** doctor warns when a configured MCP server is unreachable or rejects auth, but the gateway still starts.

**Not tested (UNVERIFIED):**
- Stdio MCP servers.
- Behaviour on `notifications/tools/list_changed`. The docs say it invalidates the cached catalog.
- The WebSocket protocol.

---

## RECOMMENDED INTEGRATION

**1. Image**

Use `ghcr.io/openclaw/openclaw:2026.9.9` (equal to `latest` today). Pin the version or the digest `sha256:7f10d5cc975a90b65192eaa099454fe33ce8ce2390806c61c65cd868e9ef730d`. I tested on `2026.9.8`, so run one smoke test on 2026.9.9 before relying on it. No build is needed. For extra packages, rebuild from the repo with `--build-arg OPENCLAW_IMAGE_APT_PACKAGES=...`.

**2. Host state directory**

Create `/srv/minion/openclaw/<instance>/` with `chown -R 1000:1000` and mount it at `/home/node/.openclaw`. Put these two files in it.

`openclaw.json` (plain JSON, since doctor rewrites it to JSON anyway):
```json
{
  "gateway": {
    "mode": "local",
    "port": 18789,
    "bind": "lan",
    "auth": { "mode": "token", "token": { "source": "env", "provider": "default", "id": "OPENCLAW_GATEWAY_TOKEN" } },
    "http": { "endpoints": { "chatCompletions": { "enabled": true }, "responses": { "enabled": true } } }
  },
  "agents": {
    "defaults": {
      "workspace": "/home/node/.openclaw/workspace",
      "model": { "primary": "anthropic/{{MODEL|claude-opus-5-5}}", "fallbacks": ["anthropic/claude-sonnet-5-5"] },
      "utilityModel": "anthropic/claude-haiku-5-5",
      "timeoutSeconds": 3600
    }
  },
  "tools": { "profile": "coding", "toolSearch": false },
  "memory": { "search": { "provider": "none" } },
  "plugins": { "entries": { "anthropic": { "enabled": true } } },
  "mcp": { "$include": "./minion-mcp.json5" }
}
```

`minion-mcp.json5`, owned by Minion and hot-reloaded; add more servers here at runtime:
```json5
{
  servers: {
    minion: {
      url: "http://minion:8700/mcp",
      transport: "streamable-http",
      headers: { Authorization: "Bearer ${MINION_MCP_TOKEN}" },
      connectionTimeoutMs: 10000,
      requestTimeoutMs: 300000,
      supportsParallelToolCalls: true,
    },
  },
}
```
Inlining the same object as `"mcp": {"servers": {...}}` in `openclaw.json` also works [VERIFIED-LIVE].

**3. Environment variables**
- `ANTHROPIC_API_KEY=<key>`
- `OPENCLAW_GATEWAY_TOKEN=<random 32+ bytes>`
- `MINION_MCP_TOKEN=<bearer token Minion's MCP gateway accepts>`
- `OPENCLAW_DISABLE_BONJOUR=1`
- `TZ=UTC`

**4. Run** (compose-equivalent; Minion can do the same through the Docker SDK)
```
docker run -d --name openclaw-1 --network minion-net --network-alias openclaw \
  --restart unless-stopped --stop-timeout 120 \
  --cap-drop NET_RAW --cap-drop NET_ADMIN --security-opt no-new-privileges \
  -e ANTHROPIC_API_KEY -e OPENCLAW_GATEWAY_TOKEN -e MINION_MCP_TOKEN -e OPENCLAW_DISABLE_BONJOUR=1 -e TZ=UTC \
  -v /srv/minion/openclaw/1:/home/node/.openclaw \
  ghcr.io/openclaw/openclaw:2026.9.9 node openclaw.mjs gateway --bind lan --port 18789
```
- Port: 18789, internal to `minion-net` only. Do not publish it publicly.
- Readiness: poll `GET http://openclaw:18789/readyz` until it returns 200 (about 30 s).
- The Minion MCP server must be reachable as `minion:8700` on the same network.

**5. Sending tasks and reading results**

Primary path:
```
POST http://openclaw:18789/v1/chat/completions
Authorization: Bearer $OPENCLAW_GATEWAY_TOKEN
x-openclaw-session-key: minion:<task-id>
(optional) x-openclaw-model: anthropic/claude-sonnet-5-5
{"model":"openclaw/default","messages":[{"role":"user","content":"<task>"}],"stream":false}
```
- Read the result from `choices[0].message.content`.
- Use `stream: true` for SSE progress, and keep the connection open: a disconnect cancels the run.
- Reusing the same session key continues the conversation.
- Alternatives:
  - `POST /v1/responses`, which supports `previous_response_id`.
  - `docker exec openclaw-1 openclaw agent --agent main --session-key minion:<id> --message-file - --json --timeout 3600`, then parse `result.payloads[].text` or `result.meta.finalAssistantVisibleText`, plus `result.meta.toolSummary`.

**6. Dynamic MCP and skill management by Minion**
- To add or remove MCP servers, either rewrite `minion-mcp.json5` atomically or run `docker exec openclaw-1 openclaw mcp set <name> '<json>'`. Both apply without a restart.
- Verify with `docker exec openclaw-1 openclaw mcp probe <name> --json`. It reports a tool count and `"tools":["<name>__<tool>"]`.
- Tools a session has already loaded are cached, so use a new session key to pick up a changed tool list.
- To add skills, write `/home/node/.openclaw/skills/<skill>/SKILL.md` (or `workspace/skills/...`) on the mounted host directory. They are picked up live.

**7. Lifecycle**
- Stop with `docker stop -t 120`, never `rm -f` on a live instance, because of the 5-minute lease lockout.
- Run one gateway per state directory, and give each OpenClaw instance its own directory.