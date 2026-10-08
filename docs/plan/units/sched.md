# Unit: Scheduler (automations) + Improver (self-improvement & frontier scout)

Files you own: `minion/evolve/scheduler.py`, `minion/evolve/improver.py`, `tests/test_scheduler.py`,
`tests/test_improver.py`.

Implement ARCHITECTURE.md §5.9 (scheduler, improver) exactly.

* Scheduler: `schedules` table; 5-field cron via `croniter` (validate; clear errors); tick loop every
  ~20 s computing due jobs (`next_run_at`), running each as `services.brain.start_run(session_id,
  prompt, source="automation", purpose="automation", title=name)` (reusing the schedule's session so it
  keeps context), recording `last_run_at`, `last_status`, `next_run_at`; publish `schedule.run`. Never run
  the same schedule concurrently. `add/list/remove/set_enabled/run_now` per contract. Built-in jobs
  (kind `builtin`, created/updated at start from settings, ids `builtin:improve`, `builtin:scout`,
  `builtin:agent-upgrades`): self-improvement every `improve_interval_hours` (0 disables), frontier scout
  every `scout_interval_hours`, harness upgrades on `settings.agent_upgrade_cron` (calls
  `services.agents.upgrade_all()` directly, no LLM). Builtins call `services.improver.improve()` /
  `.scout()`. Autonomous LLM jobs are skipped (status `skipped: budget`) when
  `services.usage.autonomy_factor()` is 0; with a factor > 1 the improve/scout cadence may run more often
  (e.g. interval / factor) - keep it simple and documented.
* Improver: `improve()` gathers signals - failed tool calls (last 7 days, grouped by tool with counts and
  latest error), negative feedback + comments, rollbacks (`<run_dir>/rollbacks.jsonl`), failed evolve/update
  log rows, open goals, recent ERROR lines from `<data_dir>/logs/core.log`, pending suggestions - and
  starts ONE brain run (purpose `improve`, session titled "Self-improvement <date>") with a focused brief:
  pick the single most valuable improvement, implement it via the right mechanism (skill/memory lesson,
  workshop tool, MCP server, harness config, or code change through `self_*` tools with checks), verify,
  record a lesson, mark goals, and report. If there are no signals, work on the highest-value open goal or
  suggestion, or do nothing (don't burn tokens pointlessly). `scout()` starts a run (purpose `scout`) that
  keeps the installation at the frontier: check the MCP registry for notable new/popular servers relevant
  to the user's memories/usage, check the installed harnesses for newer versions / notable new open-source
  harnesses, web-search recent AI tooling news, then create suggestions (`suggest_capability`) for the best
  2-5 items and auto-install only low-risk, no-secret items when autonomy is high; write a short digest as a
  memory note. Both return `{run_id, session_id}` or `{skipped: reason}`. Also `signals()` (the raw
  gathered data, used by the API/UI) and `build_brief()` (pure function, unit-tested).
* Tests: cron validation and next-run computation; tick runs due jobs exactly once (fake brain with
  start_run recorder); disabled jobs skipped; run_now; builtins created from settings and updated when
  settings change; budget skip; agent-upgrades builtin calls the fake agents manager; improver signal
  gathering from a seeded db + temp log/rollback files; brief contents; scout prompt; no-signal behaviour.
