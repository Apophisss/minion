# Unit: Docker manager + agent (harness) runtime

Files you own: `minion/runtime/docker_manager.py`, `minion/runtime/agents.py`,
`tests/test_docker_manager.py`, `tests/test_agents.py` (and test fixture dirs under `tests/fixtures/agents/`).
NOT yours: `catalog/agents/**` (another agent writes the real harness templates later).

Implement ARCHITECTURE.md §5.1 and §5.6 exactly. Extension to the §5.1 contract (you own it, document it in
your module): `run(spec, replace=True, pull_missing=True, files: dict[str, bytes | str] | None = None,
start=True)` - `files` (container path -> content) are written with put_archive after create and before start.

## DockerManager
* docker SDK 7.x (`docker.from_env()` / `DOCKER_HOST`; sync - wrap with `asyncio.to_thread`). `available`
  False (and every method raising a clear `DockerUnavailable` error) when the daemon is unreachable -
  Minion must still run without Docker.
* Labels `minion.managed=true`, `minion.kind`, `minion.name`; names prefixed `minion-` when missing.
* `run` resolves `${secret:..}` in env via `services.secrets.resolve`, builds when `build_context` is set
  and the image is missing (context relative to `settings.source_dir`), pulls missing images, replaces an
  existing container of the same name (when `replace`), attaches to `settings.docker_network` (create if
  missing) with aliases, sets restart policy/mem/cpus/shm/ports/volumes/user/workdir, waits for
  `healthcheck_url` when given.
* `build_image` streams build log lines to `on_log` and publishes `container.build` bus events; raises with
  the last 50 log lines on failure.
* `exec` with timeout (run in thread, demux stdout/stderr). `logs` decoded utf-8 (errors replaced).
* `self_container()`: detect the container Minion runs in (hostname / cgroup / `/.dockerenv`) - returns
  None on a plain host.
* `wait_http(url, timeout)` polls with httpx.
* Networking helper `endpoint(container_name, port) -> str`: when Minion itself runs in a container on the
  same network return `http://<name>:<port>`; on a plain host return `http://<container-ip-on-network>:<port>`
  (Linux) or the published host port if any.

## AgentManager
* Templates: YAML `template.yaml` in `settings.catalog_dir/agents/*/` and `settings.local_dir/agents/*/`
  parsed into `AgentTemplate` (set `dir`). Bad templates are logged and listed with an error, not fatal.
* Instances persisted in the `agents` table (AgentInstance JSON). Container `minion-agent-<name>`, data
  volume `minion-agent-<name>-data` mounted at `data_path`.
* Rendering: `{{var}}` substitution (regex) in env values, command, config file templates, exec_cmd,
  auth_header/extra_headers. Vars: `name, gateway_url, gateway_token, core_url, model, fast_model,
  anthropic_api_key, agent_token, persona_name` + `overrides`. Unknown variables -> error naming them.
  `${secret:...}` placeholders are resolved by DockerManager.run. Never log rendered secrets.
* `deploy`: missing required secrets -> clear error listing them (the brain will ask the user); build
  image if needed (`build_context` relative to template dir) or pull; generate `agent_token`; create +
  write config files + start; wait for health (`healthcheck_path` on interface port, or running state);
  state transitions published as `agent.status` bus events. Autostart (settings.autostart, except
  "desktop") in a background task at `start()` - "all" means every non-optional agent-category template.
* `send`: `openai_http` -> POST `{endpoint}{path}` with `{"model": interface.model, "messages":
  [{"role":"user","content": message}], "stream": false}` + auth/extra headers (session id available as
  `{{session}}`), return `choices[0].message.content`; `exec_cli` -> `docker exec` argv (no shell) with
  `{{message}}`/`{{session}}` substituted, use `exec_cmd_continue` when a session is given and the
  template defines it; strip ANSI; non-zero exit -> error with stderr tail. Timeouts from the interface.
* `upgrade(name)`: strategy `pull` -> pull the tag; `rebuild` -> tag current image `<image>-previous`,
  rebuild with `pull=True, nocache=True`; then redeploy with the same overrides; if health fails, retag
  `-previous` back and redeploy; log to `evolve_log` (kind `upgrade`). `upgrade_all()` for every deployed
  instance (sequential).
* `write_template(name, files, share=True)`: writes `catalog/agents/<name>/...` (or local), validates
  template.yaml parses, commits + shares via `services.contrib` when present (§5.9).
* Tests: unit tests for rendering/template loading (tmp dirs) + docker tests (`docker_ok`): DockerManager
  run/list/inspect/logs/exec/put_file/build/remove with labels on tiny images (build FROM
  `python:3.12-slim`, already present locally); AgentManager end-to-end with a tiny fake harness template
  in `tests/fixtures/agents/echo/` (a ~20-line Python OpenAI-compatible HTTP echo server + exec CLI) on a
  test network: deploy -> send via openai_http -> send via exec_cli -> logs -> upgrade -> remove. When the
  tests run on a plain host, reach containers via their network IP. Clean up everything.
