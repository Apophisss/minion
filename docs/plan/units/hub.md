# Unit: MCP hub + registry client

Files you own: `minion/mcp_hub/connection.py`, `minion/mcp_hub/hub.py`, `minion/mcp_hub/registry_client.py`,
`tests/fixtures/echo_server.py`, `tests/test_hub.py`, `tests/test_registry.py`, `catalog/servers/*` (curated specs).

Implement ARCHITECTURE.md §5.2 and §5.3 exactly.

## MCPConnection (connection.py)
* Transports: stdio (command/args/env/cwd; env inherits PATH/HOME; placeholders resolved through
  `services.secrets.resolve`), streamable HTTP (url + headers), legacy SSE. Optional `spec.container`:
  start it with `services.docker.run(spec.container)` first, then wait for the URL.
* One owner task per connection that enters the transport + ClientSession context managers, signals
  "ready", then waits for a stop event (anyio cancel scopes must be exited in the task that entered them).
  Other tasks call tools through the session. Reconnect with exponential backoff (cap 60 s) after
  unexpected disconnects; stop cleanly.
* Handle `notifications/tools/list_changed` (client message handler) by re-listing tools and calling the
  hub's change callback. Support paginated `list_tools`.
* `call_tool` with timeout; normalise results into `ToolCallResult` (text, image -> base64 + mimeType,
  embedded/linked resources -> text with uri, structuredContent). Exceptions/timeouts become
  `ToolCallResult(is_error=True, content=[{"type": "text", "text": <actionable message>}])`.
* Capture the server's stderr (stdio) into a bounded buffer; include its tail in error messages
  (that's what lets the brain debug a broken server).

## MCPHub (hub.py)
* Sources at `start()`: DB table `servers` (source of truth for runtime-added servers), catalog specs
  `settings.catalog_dir/servers/*.yaml` and `settings.catalog_dir/servers/*/server.yaml` (source=catalog;
  a project dir with a Dockerfile builds image `minion-mcp-<name>:latest` via `services.docker` when
  needed), `settings.local_dir/servers/...` (same formats), and builtins registered by other components
  with `add_server(spec, persist=False)` (workshop, desktop). DB entries override catalog entries with the
  same name. Disabled specs are listed with state `disabled`; missing secrets -> `needs_secret`.
* `start()` must return quickly: connect enabled servers concurrently in background tasks
  (`services.spawn`). Publish `server.status` and `tools.changed` bus events; call `on_change` callbacks.
* `qualify(server, tool)` module function: `<server>__<tool>`, characters outside `[a-zA-Z0-9_-]`
  replaced by `_`, max 64 chars (truncate + 6-char sha1 suffix), unique.
* Respect `tool_allowlist`. `list_tools()` returns tools of running servers only.
* `remove_server` deletes the DB row (catalog files are not deleted - it just disables via a DB row
  `enabled: false` when the server came from the catalog).

## RegistryClient (registry_client.py)
* Official registry `https://registry.modelcontextprotocol.io` (verify the current API - v0 or v0.1 -
  with real requests through the configured HTTPS proxy: `curl "https://registry.modelcontextprotocol.io/v0/servers?search=github&limit=3"`).
  A research report `docs/research/registry_docker.md` may appear - read it if present.
* `search`, `get`, `to_spec` per the contract. to_spec maps npm -> `npx -y pkg@version`, pypi ->
  `uvx pkg==version`, oci -> `docker run -i --rm [-e VAR ...] image`, remotes (streamable-http / sse) ->
  http/sse transport; required env vars / headers become `${secret:NAME}` placeholders and are returned
  in the "inputs needed" list (`name`, `description`, `is_secret`, `is_required`).
* Cache search results briefly (5 min). Timeouts and HTTP errors -> clear exceptions.

## Curated catalog (`catalog/servers/*.yaml`)
Add 5-8 genuinely useful, well-known servers as ServerSpec YAML with accurate, VERIFIED package names
(check the registry/npm/PyPI): e.g. filesystem (scoped to `/data/workspace`), fetch, git, time,
sequential-thinking, github (official remote or docker image; needs `${secret:GITHUB_TOKEN}`),
playwright browser automation, a web search one (e.g. Brave, needs a key). Use `enabled: false` for
anything heavy or needing a secret; enable at most the lightweight no-secret ones. Each with a good
`description` and `tags`. Add `catalog/servers/README.md` explaining the format (ServerSpec fields).

## Tests
* `tests/fixtures/echo_server.py`: a real stdio MCP server using the installed SDK's high-level server
  API: tools `echo(text)`, `add(a, b)`, `add_dynamic_tool(name)` (adds a tool at runtime so the server
  emits tools/list_changed), and `fail()` (raises).
* test_hub.py: connect to the fixture over stdio; list/call; error results; list_changed refresh;
  restart/remove/disable; needs_secret; persistence across hub restarts (same db); qualify() edge cases;
  streamable-HTTP transport against an in-process server (uvicorn on a free port, started in the test).
* test_registry.py: to_spec unit tests with canned JSON (no network) + one `@pytest.mark.network` test
  hitting the real registry that skips on network failure.
