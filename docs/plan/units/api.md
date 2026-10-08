# Unit: App assembly, REST API, channels, CLI

Files you own: `minion/app.py`, `minion/server.py`, `minion/cli.py`, `minion/__main__.py`,
`minion/api/*.py` (split by area: auth.py, chat.py, mcp.py, agents.py, desktop.py, evolve.py, misc.py ...),
`minion/channels/openai_compat.py`, `minion/channels/telegram.py`, `tests/test_api.py`,
`tests/test_openai_compat.py`, `tests/test_telegram.py`, `tests/test_app.py`, `tests/test_cli.py`.
NOT yours: `minion/web/*` (the web UI agent builds the front-end against the same REST contract).

Implement ARCHITECTURE.md §5.10 and §5.11 exactly.

* `create_app(settings=None, services=None) -> FastAPI`. When `services` is passed (tests), use it as-is
  and skip construction. Otherwise the lifespan builds every component in the §5.10 order. Robustness
  matters more than purity here: Minion modifies its own code, so construct and start EACH component in its
  own try/except - on failure log the traceback, publish a `notify` (error) and keep going with that peer
  set to None (the brain must stay reachable to repair itself). Apply runtime settings overrides from kv
  `settings.overrides` at start. Generate tokens on first boot: `api_token` (secret `MINION_API_TOKEN`) and
  `gateway_token` (secret `MINION_GATEWAY_TOKEN`) when unset; write the admin token to
  `<run_dir>/api_token` (mode 600) and log a clear banner with the URL. `install_id` likewise (kv).
  Register native tools via `minion.brain.native_tools.register_native_tools(registry, services)`.
  Mount the gateway at `/mcp` and enter `gateway.lifespan()` inside the app lifespan. Serve `minion/web/`
  at `/` (index.html fallback) if the directory exists. Stop components in reverse order.
  Component constructors: `Cls(services)`; LLM: `LLMClient(services)` passed to `Brain` via services
  (`services.llm`? - there is no such field: construct `Brain(services)` and let it build its LLMClient
  unless `services.brain` was injected).
* Auth dependency: Bearer header, `minion_token` cookie, or `?token=` -> constant-time compare with
  `settings.api_token`. `/health` and `/api/setup/status` public; `/api/update/webhook` uses the GitHub
  HMAC instead.
* Endpoints: everything in §5.11, thin handlers over the service contracts, returning 503 with a clear
  message when the needed component is unavailable. `/api/chat` -> `brain.start_run`; `/api/runs/{id}/events`
  -> SSE (`text/event-stream`, `data: <json>\n\n`, heartbeat comments every 15 s, honours `after`);
  `/api/events` -> SSE of bus events. `GET /api/sessions/{id}` converts raw Anthropic messages into
  display messages (text, tool calls with short results, thinking updates; hide `<context>` blocks).
* Desktop proxy: `/desktop/vnc/{path}` reverse-proxies HTTP to `services.desktop.vnc_url` and a WebSocket
  route `/desktop/vnc/websockify` bridges to the upstream websockify (use the `websockets` client; binary
  frames both ways; close propagation). Auth via cookie/query token.
* `channels/openai_compat.py`: `/v1/models` (`minion` + `minion/<agent>` for each deployed agent harness),
  `/v1/chat/completions` (stream and non-stream, OpenAI chunk format, `[DONE]`), auth with api_token (also
  accept the gateway token? no - api token only). Session mapping per ARCHITECTURE (`X-Minion-Session`,
  Open WebUI chat id header - check `docs/research/openwebui.md` when it appears; `user`; hash of first user
  message). Only the LAST user message is sent to the brain (Minion keeps its own history); images in the
  last message are passed through as image blocks. Tool activity is streamed as short italic progress lines
  so chat front-ends show what's happening; final text follows.
* `channels/telegram.py`: `TelegramChannel(services)` with `start/stop`; long polling getUpdates via httpx;
  only `settings.telegram_allowed_users` (ids or @usernames; if empty, the first user to send `/start <api
  token>` is bound and stored in kv); session per chat `telegram:<chat_id>`; `/new` resets; streams the final
  answer (split >4096 chars); approval requests -> inline keyboard buttons -> `policy.resolve`; photos ->
  image blocks. Started by app.py when a token is configured.
* `server.py`: run uvicorn (`settings.host/port`, proxy headers, log level), then
  `sys.exit(int(os.environ.get("MINION_EXIT_CODE", "0")))`; configure logging (plain text, timestamps).
* `cli.py` (`minion` command, argparse): `chat` (interactive REPL with streaming via SSE, `/new`, `@agent`
  routing), `ask "..."`, `status`, `servers [list|add|rm]`, `tools [list|call]`, `agents [list|deploy|send]`,
  `update [check|apply]`, `token`; URL from `MINION_URL` (default `http://127.0.0.1:8700`), token from
  `MINION_API_TOKEN` or `<data_dir>/run/api_token`. `__main__.py` -> `cli.main()`.
* Tests with injected fake services (no Docker, no network, no API key): auth (header/cookie/query, 401s),
  setup flow, status, chat -> run events SSE (fake brain), sessions display conversion, approvals,
  suggestions, servers CRUD (fake hub), settings PATCH persists + applies, webhook HMAC, openai-compat
  stream + non-stream + session mapping, telegram update handling with httpx MockTransport, CLI against
  the test app (httpx transport injection), and an app lifespan smoke test with real components where
  possible (Docker disabled via settings/env) that boots `create_app()` and checks `/health` - skip parts
  whose modules are not written yet (`pytest.importorskip`).
