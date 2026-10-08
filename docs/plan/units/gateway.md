# Unit: MCP gateway

Files you own: `minion/mcp_hub/gateway.py`, `tests/test_gateway.py`.

Implement ARCHITECTURE.md §5.4 exactly.

* A low-level MCP server (verify the mcp 2.3.0 API: `mcp.server.lowlevel` or its 2.x equivalent) whose
  list_tools / call_tool handlers read `services.hub` dynamically (contract §5.2: `list_tools()`,
  `call_tool(qualified_name, arguments)`, `on_change(cb)`), exposing only tools whose server spec has
  `expose_in_gateway=True` (use `hub.get_spec(server)`), with qualified names.
* Meta tools: `minion_status` (servers/tools/agents/desktop summary - read peers defensively) and
  `minion_ask(message, session_id?)` that calls `services.brain.chat(session_id, message, source="gateway")`
  and returns the reply (only listed when `services.brain` exists). These let OpenClaw/Hermes (and their
  WhatsApp/Telegram/Slack channels) talk to Minion's brain.
* Streamable HTTP, stateful sessions (needed so notifications reach clients), mounted by app.py at `/mcp`.
  Provide `asgi_app` and `lifespan()` (async context manager that runs the session manager) and make it
  work when mounted inside FastAPI via `app.mount("/mcp", gateway.asgi_app)` with the FastAPI lifespan
  entering `gateway.lifespan()`. Verify trailing-slash behaviour (`/mcp` and `/mcp/` should both work;
  clients will use `http://minion:8700/mcp`).
* `notify_tools_changed()`: send `notifications/tools/list_changed` to every active session; register it
  with `hub.on_change` in `start()`. Must not crash when sessions are gone.
* Auth: ASGI middleware around the app: `Authorization: Bearer <token>` must equal `settings.gateway_token`
  or `settings.api_token` (`hmac.compare_digest`), else 401 JSON. Also accept `?token=` query param.
* Convert `ToolCallResult` back to MCP content (text / image) + `isError`, and `structured` to
  structuredContent when present.
* Tests: FastAPI app + mounted gateway + fake hub implementing the contract; connect with the SDK's
  streamable HTTP client using a bearer header (real HTTP via uvicorn on a free port in the test, or an
  ASGI transport if the SDK client supports injecting an httpx client); list tools, call a tool, change
  the fake hub's tools -> client receives list_changed (assert via the client message handler), 401
  without/with wrong token, minion_ask with a fake brain.
