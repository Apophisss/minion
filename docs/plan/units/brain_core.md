# Unit: Brain core (LLM client, tool registry, runs, prompts, approvals, suggestions)

Files you own: `minion/brain/llm.py`, `minion/brain/tools.py`, `minion/brain/agent.py`,
`minion/brain/prompts.py`, `minion/brain/policy.py`, `minion/brain/suggestions.py`,
`tests/test_llm.py`, `tests/test_tools.py`, `tests/test_brain.py`, `tests/test_policy.py`.
NOT yours: native_tools.py, memory.py, skills.py, usage.py (another agent, same contract).

Implement ARCHITECTURE.md §5.8 exactly. Read the bundled Claude API guidance before writing LLM code:
the Claude API docs (https://platform.claude.com/docs, Python SDK: README, streaming, tool use) or the `claude-api` skill in Claude Code
and the tool-use concepts page (eager input streaming, tool search, computer use) and the research
report `docs/research/computer_toolset.md` (exact computer-toolset protocol: member names, toolset_name echo,
halt-on-failure text, screenshot limits).

## llm.py - LLMClient / FakeLLM
* `anthropic.AsyncAnthropic` (api key from `services.secrets.get("ANTHROPIC_API_KEY")` or
  `settings.anthropic_api_key`; `settings.anthropic_base_url`; re-create the client when the key
  changes - the key can be set at runtime from the setup page). No key -> raise a clear `NoApiKey` error.
* `stream_turn(...)` uses `client.beta.messages.stream(...)` + `get_final_message()`; model
  `settings.model` (Opus 5.5 default), `max_tokens=settings.max_tokens`, `thinking={"type": "adaptive",
  "display": settings.thinking_display}` (`updates` needs beta `thinking-display-updates-2026-08-18`),
  `output_config={"effort": ...}`, system with `cache_control` on the stable prefix + top-level
  `cache_control={"type":"ephemeral"}`, refusal fallbacks (`fallbacks="default"` + beta
  `server-side-fallback-2026-07-01`) when `settings.refusal_fallback`, compaction (beta
  `compact-2026-01-12`, `context_management={"edits":[{"type":"compact_20260112"}]}`) when
  `settings.compaction`, `eager_input_streaming: true` on client tools (not on server tools/toolsets).
  Verify each parameter name against the installed SDK signature (`client.beta.messages.stream`).
* Self-healing: on `anthropic.BadRequestError` whose message implicates an optional feature (fallbacks,
  display/updates, compaction/context_management, eager_input_streaming, a beta header, cache_control,
  tool search/defer_loading, a server tool type), disable that feature, persist the set in kv
  `llm.disabled_features`, log + publish `notify` (warning), and retry (bounded). Other 400s propagate.
  Rate limit / overloaded / connection errors: SDK retries + bounded extra backoff.
* Stream events -> `on_event` dicts: `{"type":"text_delta","text"}`, `{"type":"thinking","text"}`
  (thinking/progress updates), `{"type":"tool_input","id","name"}` when a tool_use starts. Python SDK
  raises `ValueError` from the stream iterator for unparseable eager-streamed JSON: re-issue the turn
  (bounded).
* Return the final message as a plain dict whose `content` blocks are passed back to the API unchanged
  later (use the SDK model's dict conversion that round-trips: check `to_dict()` vs `model_dump(mode="json",
  exclude_none=True)` and make sure thinking signatures, tool_use `toolset_name`, compaction and fallback
  blocks survive). Handle `pause_turn`. Record usage via `services.usage.record(...)` when present.
* `FakeLLM(script)`: same interface; replays scripted assistant messages (list of dicts or a callable
  receiving the request) and records requests - used by every brain test.

## tools.py - ToolRegistry / ToolContext
* Contract + `execute_all(blocks, ctx) -> list[dict]` (one tool_result per tool_use, same order): regular
  tools run concurrently; computer-toolset calls (block has `toolset_name == "computer"`) run sequentially
  in order with the halt rule (`Not executed: an earlier computer action in this turn failed.`) and echo
  `"toolset_name": "computer"` on their results only; server tools are not executed client-side.
* Before executing, ask `services.policy.decide(...)` (allow/ask/deny); `ask` -> `policy.request(...)`
  (blocks until the user decides or times out); denial -> `is_error` result telling the model the user
  declined and to try something else / ask the user.
* Validate inputs minimally against the schema (required keys + top-level types) -> `INVALID_INPUT` error
  result. Truncate long text results (`settings.tool_result_max_chars`) saying how much was cut. Hub
  `ToolCallResult` images -> image blocks. Record each call in the `tool_calls` table.
* `definitions(ctx)`: native tools (sorted by group/name) + hub tools (sorted; `input_schema` coerced to a
  valid object schema) + server tools `web_search_20260209` / `web_fetch_20260209` when
  `settings.web_tools` + `{"type": "computer_toolset_20260801"}` when `services.desktop` is present and
  Docker is available (executor ensures the desktop is running on first use). Above
  `settings.tool_search_threshold` tools, hub tools get `defer_loading: true` and
  `{"type": "tool_search_tool_bm25_20251119", "name": "tool_search_tool_bm25"}` is added. Deterministic
  output for identical state (prompt caching).

## agent.py - Brain (runs are background tasks)
* Contract §5.8 incl. `start_run`/`events`/`run`/`chat`/`cancel`/`active_runs`/sessions. Each run is an
  asyncio task (services.spawn) writing events (with increasing `seq`) to an in-memory buffer (bounded,
  kept for finished runs for 1 h) and publishing `brain.event` on the bus; `events()` replays then follows.
  Run rows in the `runs` table. One active run per session; additional messages are queued and processed
  in order.
* Transcript: append-only rows in `messages` (assistant content exactly as returned; tool results as user
  messages). Volatile context (time, budget remaining, active agents, pending approvals/suggestions) goes
  into the user turn as a leading `<context>...</context>` text block - never edit earlier messages and
  never put volatile data in the system prompt.
* Loop: until `end_turn`/`refusal`/max iterations (`settings.max_turn_iterations`) - handle `tool_use`
  (execute_all), `pause_turn` (continue), `max_tokens` with a tool_use (don't run the truncated call; tell
  the model to continue with smaller steps), `refusal` (report to the user). Errors -> `error` event with an
  actionable message (e.g. "No Anthropic API key - open Settings and paste one").
* Routing: `target` or a message starting with `@<agent-name>` -> `services.agents.send(...)`; store both
  sides in the session; unknown agent -> list the available ones.
* Sessions: create with title from the first message; `get_session` returns raw messages; `list_sessions`.

## prompts.py
Stable system prompt (cacheable) built from: persona (`settings.persona_name`, `persona_style`,
`language` - default: answer in the user's language, e.g. Hebrew when the user writes Hebrew); what Minion
is and its capabilities; operating principles (be proactive: suggest new capabilities with
`suggest_capability` and offer to build them; prefer existing open-source harnesses / MCP servers from the
registry over writing code; build missing capabilities yourself via workshop/registry/agents; verify
results; share generic capabilities to the shared catalog, keep personal ones private; never ask for
secrets in chat - use `secret_request`; risky external actions go through approvals; for big tasks
delegate to the best harness (template `best_for`); use the desktop for anything needing a real browser
or GUI; keep the user informed briefly); self-knowledge pointers (`docs/ARCHITECTURE.md`, the source dir,
`self_*` tools); the skills index (`services.skills.list()` names+descriptions, when present); top memories
(preferences + lessons, when `services.memory` present); harness catalog summary (`services.agents`).
Keep it well-written and compact. Rebuild only when those inputs change (cache key).

## policy.py, suggestions.py
Per contract (§5.8). Policy heuristics: read-only names/annotations -> allow; MCP `destructiveHint` or
names matching send/delete/remove/drop/pay/purchase/buy/order/transfer/publish/post/tweet/email/
force_push/kill/shutdown -> ask (in `smart`), every non-read tool -> ask (in `strict`), allow all (`off`);
user rules in `tool_policies` (fnmatch, most specific first) override; autonomous purposes never block
(deny + suggestion/notify). `resolve(id, decision, remember)` with `remember` writing a rule.
Approval events `approval.request` / `approval.resolved` on the bus.

## Tests (FakeLLM everywhere; no network)
Plain answer; native tool loop; hub tool via a fake hub; parallel tool results ordering; computer toolset
halt semantics with a fake desktop; approval ask -> approve and -> deny (resolve from another task);
autonomous purpose never blocks; cancellation; run continues after the consumer stops reading and
`events(after=n)` replays; queued second message; @agent routing with a fake agent manager; LLM
self-healing (monkeypatch the SDK stream call to raise a BadRequestError naming `fallbacks`, then
succeed; assert the feature is disabled and persisted); dict round-trip of content blocks; tool search
threshold; definitions deterministic.

## Parallel sub-agents (maximum parallelism, no bottleneck)
* `start_run(..., parent_run_id: str | None = None)`; child runs get `depth = parent depth + 1` and are
  refused beyond `settings.max_subagent_depth`. A global `asyncio.Semaphore(settings.max_parallel_agents)`
  bounds concurrently *executing* runs (queued runs wait for a slot; the UI shows them as queued).
* `Brain.run_parallel(tasks: list[dict], *, parent_run_id, depth, source, purpose) -> list[dict]`:
  each task `{"task": str, "target": str | None, "title": str | None}`; starts all as child runs (new
  sessions) concurrently, awaits all, returns `[{task, target, session_id, run_id, ok, result}]` in input
  order. Used by the native tool `parallel_tasks` (another agent registers it). Test it: N tasks run
  concurrently (FakeLLM with delays: total time ~ max, not sum), semaphore respected, depth limit enforced,
  one failure doesn't break the others.
