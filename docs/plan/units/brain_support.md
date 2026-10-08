# Unit: Brain support (native tools, memory, skills, usage) + seed skills

Files you own: `minion/brain/native_tools.py`, `minion/brain/memory.py`, `minion/brain/skills.py`,
`minion/brain/usage.py`, `catalog/skills/*.md`, `tests/test_native_tools.py`, `tests/test_memory.py`,
`tests/test_skills.py`, `tests/test_usage.py`.
NOT yours: llm.py, tools.py, agent.py, prompts.py, policy.py, suggestions.py (another agent).

Implement ARCHITECTURE.md §5.8 (memory/skills/usage/native_tools) exactly. The ToolRegistry API you
register into: `registry.register(name, description, input_schema, handler, *, group="system",
dangerous=False)`; handler signature `async def handler(args: dict, ctx) -> str | dict | list` where `ctx`
has `session_id`, `source`, `purpose`, `depth`. Write a tiny fake registry in your tests.

## native_tools.py - `register_native_tools(registry, services)`
Register the complete system tool set with precise descriptions (they are the brain's manual - say when
to use each tool, what it returns, and pitfalls) and strict JSON schemas (`additionalProperties: false`,
`required`). Groups and tools (handlers call peers per their contracts; when a peer is missing return a
clear message like "Docker is not available on this host" instead of raising):
* mcp: `mcp_list_servers`, `mcp_list_tools`, `mcp_add_server` (ServerSpec fields), `mcp_remove_server`,
  `mcp_set_enabled`, `mcp_restart_server`, `mcp_registry_search`, `mcp_install_from_registry` (registry
  entry -> spec -> add; report inputs/secrets still needed and use `secret_request` guidance).
* workshop: `workshop_list`, `workshop_read`, `workshop_write_tool` (file name, code, scope
  shared|private, optional test call, share), `workshop_delete_tool`, `workshop_test_tool`,
  `workshop_scaffold_server`. Include the tool-authoring guide (from `minion.workshop.sdk` docstring if
  importable, else a built-in summary) in `workshop_write_tool`'s description.
* docker: `docker_list`, `docker_run` (ContainerSpec subset), `docker_stop`, `docker_remove`,
  `docker_logs`, `docker_exec`, `docker_build` (context dir inside the source tree or workspace).
* agents (harnesses): `agent_list_templates` (with best_for), `agent_list`, `agent_deploy`, `agent_send`
  (delegate a task; the main way to use OpenClaw/Hermes/opencode/...), `agent_stop`, `agent_remove`,
  `agent_logs`, `agent_upgrade`, `agent_write_template`.
* desktop: `desktop_start`, `desktop_status`, `desktop_stop`, `desktop_bash` (shell inside the desktop
  container - the brain's general-purpose sandbox), `desktop_open` (URL or app).
* knowledge: `memory_save`, `memory_search`, `memory_delete`, `skill_list`, `skill_read`, `skill_write`.
* secrets: `secret_list` (names only), `secret_request` (ask the user to add a secret: publishes a
  `notify` + creates a suggestion of kind `secret` explaining where to paste it - Settings > Secrets -
  never accepts the value itself).
* automation: `schedule_list`, `schedule_add` (name, 5-field cron, prompt), `schedule_remove`,
  `schedule_set_enabled`, `schedule_run_now`; `goal_list`, `goal_add`, `goal_update`.
* proactivity: `suggest_capability` (title, description, kind, payload) -> `services.suggestions.add`,
  `suggestion_list`, `suggestion_update`.
* self-evolution: `self_begin`, `self_read_file`, `self_write_file`, `self_edit_file`, `self_list_files`,
  `self_grep`, `self_diff`, `self_run_checks`, `self_finish`, `self_abort`, `self_history`,
  `self_rollback`, `self_status` (reads `<run_dir>/supervisor.json`, `rollback.json`, last rollbacks).
  Reading files of the live source tree is allowed without a workspace (`self_read_file` with no ws).
* updates & sharing: `update_check`, `update_apply`, `contribute` (share committed catalog paths).
* misc: `usage_report`, `notify_user` (title, message, level), `system_status`.
Mark write/destructive tools `dangerous=True` where appropriate (policy uses it).

## memory.py, skills.py, usage.py
* MemoryStore over the `memories` table + FTS5 (`memories_fts`); sanitize FTS queries (quote terms,
  fall back to LIKE on syntax errors); `top(kind, limit)` helper for the prompt builder.
* SkillLibrary: markdown files with YAML front matter (`name`, `description`, optional `tags`) in
  `settings.catalog_dir/skills` (shared) and `settings.local_dir/skills` (private; overrides shared on name
  clash). `write` validates name `[a-z0-9-]+`, writes, commits + shares through `services.contrib` when
  shared and `share=True`.
* UsageTracker: `record(model, usage, purpose="chat", session_id=None)` accepts the SDK usage object or
  dict (input/output/cache_read/cache_creation tokens) -> cost via a price table (per 1M tokens, input /
  output / cache read; cache writes = 1.25x input): claude-opus-5-5 4/20/0.20, claude-sonnet-5-5 2/10/0.20,
  claude-haiku-5-5 0.10/0.50/0.01, claude-fable-5-1 10/50/0.25, claude-opus-5 5/25/0.50; unknown models
  -> opus-5-5 prices; overridable via kv `usage.prices`. `summary(period)` -> tokens, cost, by purpose,
  by day, budget (`settings.monthly_budget_usd`), remaining, pace (expected spend at this point of the
  month vs actual). `autonomy_factor()` -> 0 when autonomy is off or budget exhausted; otherwise base
  (low 0.5, medium 1, high 2) scaled up (max x2) when spend is well below pace near month end ("use it or
  lose it") and down when above pace.

## Seed skills (`catalog/skills/*.md`, front matter + concise, practical playbooks)
add-mcp-server (registry search -> install -> secrets -> verify), build-a-tool (workshop flow, testing,
shared vs private), delegate-to-harness (which harness for what, how to phrase tasks, checking results),
use-the-desktop (computer use tips: screenshot first, keyboard shortcuts, wait for loads, verify),
self-improve-safely (evolve flow: small changes, run checks, describe, rollback), create-automation
(cron examples, idempotent prompts, budget awareness), propose-capabilities (when and how to suggest and
build new capabilities), handle-secrets. Plus `catalog/skills/README.md` describing the format.

## Tests
Every native tool callable with fakes for peers (table-driven: a fake services object with fake hub,
workshop, docker, agents, desktop, evolver, updater, contrib, scheduler, suggestions, skills, memory);
schemas are valid JSON Schema objects; missing-peer messages; memory FTS search incl. Hebrew text;
skills front matter + local override + share call; usage cost math, summary, autonomy factor.

## Parallelism
* Native tool `parallel_tasks` (group `agents`): input `{"tasks": [{"task": str, "target": str?, "title": str?}], 
  "max_items": <=32}` -> `services.brain.run_parallel(tasks, parent_run_id=ctx.run_id, depth=ctx.depth, ...)`
  and returns a compact JSON list of results. Description must teach the brain to fan out independent work
  (research several things, build several tools, run several harnesses on sub-problems) instead of doing it
  sequentially. `ctx` also has `run_id` (may be None).
