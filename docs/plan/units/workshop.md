# Unit: Workshop (user/AI-written tools)

Files you own: `minion/workshop/sdk.py`, `minion/workshop/server.py`, `minion/workshop/validator.py`,
`minion/workshop/manager.py`, `minion/workshop/templates/**` (MCP server project template),
`catalog/tools/*.py` (starter tools) + `catalog/tools/README.md`, `tests/test_workshop.py`.

Implement ARCHITECTURE.md §5.5 exactly.

* `sdk.py`: `tool` decorator usable as `@tool` and `@tool(name=..., description=...)`; works for sync and
  async functions; records into a per-module registry the server reads. Keep it dependency-free so tool
  files can also be imported standalone. Document the format in the module docstring (it is shown to the
  brain as the authoring guide).
* `server.py`: `python -m minion.workshop.server --dir A [--dir B ...]` stdio MCP server using the
  installed SDK's high-level server (verify the 2.x API name, e.g. FastMCP / MCPServer, and how to add
  tools programmatically with typed-signature schemas). Loads each `*.py` in isolation (importlib with
  unique module names); a broken file must not break the others - expose a `workshop_status` tool listing
  loaded files/tools and load errors. Duplicate tool names: later ones get a `_<file>` suffix.
* `validator.py`: `python -m minion.workshop.validator FILE [--call NAME --args JSON]` -> prints one JSON
  report `{ok, tools: [{name, description, input_schema}], error, call_result}`; timeouts enforced by the
  caller.
* `# requirements: a, b>=1` header parsing; install into `<data_dir>/workshop/venv` (created lazily with
  `--system-site-packages`; if venv creation fails fall back to `sys.executable` and say so); the workshop
  server is registered in the hub as builtin `ServerSpec(name="workshop", source="builtin",
  command=<venv python>, args=["-m", "minion.workshop.server", "--dir", <catalog tools>, "--dir", <local tools>],
  env={"PYTHONPATH": <source dir>})`.
* `Workshop.write_tool`: validate file name (`[a-z0-9_]+\.py`), stage in a temp dir, validate in a
  subprocess (timeout 60 s), install requirements, optional `test_call` via validator, move into place
  (`shared` -> `settings.catalog_dir/tools`, `private` -> `settings.local_dir/tools`), restart the hub's
  `workshop` server, and for shared tools with `share=True` call `services.contrib.commit_paths([...], msg)`
  then `services.contrib.share(sha, title, body, paths)` when `services.contrib` exists (contract §5.9).
  Refuse code that contains literal secrets matching common key patterns (sk-ant-, ghp_, xox[bp]-, AKIA...)
  and tell the caller to use secrets instead (tools read secrets from env vars injected by the hub: document
  `env` usage). Return a structured dict.
* `scaffold_server`: create `catalog/servers/<name>/` from `templates/python/` (Dockerfile, server.py using
  the high-level SDK, requirements.txt, server.yaml with `transport: stdio`, `command: docker`,
  `args: [run, -i, --rm, minion-mcp-<name>:latest]`, `source: catalog`), insert provided tool code, build the
  image via `services.docker.build_image` (when available), register via `services.hub.add_server`, commit
  + share. Return details incl. build errors (actionable).
* Starter tools in `catalog/tools/` (no secrets, small, genuinely useful, tested): e.g. date/time &
  timezone conversion, unit/currency-free calculations, text utilities (slugify, word count, regex
  extract), JSON/CSV conversion, QR code generation (demonstrates `# requirements:`).
* Tests (never write into the real repo: build a tmp source dir with `catalog/tools` and set
  `settings.src_dir` to it): sdk decorator; validator on good/bad files; write_tool happy path + secret
  refusal + syntax error; private vs shared placement; server.py over stdio with the SDK client (list + call
  + broken-file isolation + workshop_status); requirements header parsing; contrib called for shared tools
  (fake contrib); hub restart called (fake hub).
