# Unit: Self-evolution, self-update, sharing (git, evolver, contrib, updater, helper) + supervisor tests

Files you own: `minion/evolve/git.py`, `minion/evolve/evolver.py`, `minion/evolve/contrib.py`,
`minion/evolve/updater.py`, `minion/evolve/helper.py`, `tests/test_git.py`, `tests/test_evolver.py`,
`tests/test_contrib.py`, `tests/test_updater.py`, `tests/test_supervisor.py`.
You may fix real bugs in `minion/supervisor.py` (report each fix); don't change its design.

Implement ARCHITECTURE.md §2 and §5.9 (git, evolver, updater, helper, contrib) exactly. All repo-mutating
operations hold `services.git_lock`.

* `git.py`: async git CLI wrapper (env `GIT_TERMINAL_PROMPT=0`, no pager, `-c safe.directory=*`), raising
  `GitError` with stderr. Methods per contract plus helpers you need (`merge_base`, `is_ancestor`,
  `rev_parse`, `checkout`, `cherry_pick`, `branch_delete`).
* `evolver.py`: worktrees at `<data_dir>/evolve/<id>` on branch `evolve/<id>` from `main` (or the current
  branch of the source repo); path safety (resolve, must stay inside the worktree, no `.git`); `edit_file`
  requires exactly one match of `old` (else explain); `run_checks` = `python -m compileall -q minion`,
  import smoke test (`python -c "import minion.app"` with PYTHONPATH=worktree; skip gracefully if
  `minion/app.py` does not exist yet), `python -m pytest -q -x -m "not network and not slow and not docker"`
  with `MINION_SKIP_DOCKER_TESTS=1` (timeout `settings.check_timeout_s`); commands overridable via
  constructor arg for tests. `finish`: commit, checks, approve-mode -> `proposals` row (with diff + check
  output) + `notify`; auto-mode -> merge into the source repo's branch (fast-forward when possible, else
  merge commit; conflicts -> abort and report), `db.log_change("evolve", ...)`, `services.request_restart`,
  optional `services.contrib.share(...)`, remove worktree. `approve(id)` applies a pending proposal the same
  way. `rollback(commit=None)` -> `git reset --hard` to `<run_dir>/last_good` (or commit) + restart.
  `history` merges `evolve_log` rows with `<run_dir>/rollbacks.jsonl` entries. Publish `evolve.*` events.
* `contrib.py`: `commit_paths(paths, message) -> sha` (only those paths; no-op if unchanged);
  `share(sha, title, body, paths)` per contract incl. the fork flow for public repos via GitHub REST API
  (`httpx`, `Authorization: Bearer <token>` from `services.secrets.get("GITHUB_TOKEN")` or
  `settings.github_token`; check push permission via `GET /repos/{o}/{r}` -> `permissions.push`; fork via
  `POST /repos/{o}/{r}/forks` and wait until it exists; push via `git -c http.extraheader="AUTHORIZATION:
  basic <base64(x-access-token:TOKEN)>" push <url> <sha>:refs/heads/<branch>`; PR via `POST /pulls` with
  `head` = `owner:branch` for forks). PR mode builds the branch on top of `origin/<branch>` by
  cherry-picking the commit in a temporary worktree so the PR contains only that change. Record rows in
  `contributions`; publish `contrib.*` events. Never write the token into git config or logs.
  `install_id` from settings or kv (generate once).
* `updater.py`: periodic loop (`update_interval_minutes`, first check ~60 s after start) + `check()` +
  `apply(force=False)` per contract; persist status in kv `update.status` (`{checked_at, behind, ahead,
  commits:[{sha, subject}], state, error}`); `update_mode` auto/notify/off; image-level classification
  patterns (Dockerfile, .dockerignore, `images/**`, `docker-compose.yml`, `requirements.txt`,
  `pyproject.toml`, `minion/supervisor.py`); code-only -> merge + checks + restart; image-level -> merge +
  checks, then `spawn_host_update()` (ContainerSpec kind `helper`, image = `services.docker.self_container()`
  image (fallback `minion-core:latest`), command `python -m minion.evolve.helper --host-dir <settings.host_dir>
  --project <settings.compose_project> --service minion --health-url <core_url>/health`, volumes
  `/var/run/docker.sock` + host_dir at the same path, user `host_uid:host_gid` when known, network
  `settings.docker_network`, restart "no"); if `host_dir` is unset report that image-level updates need
  `MINION_HOST_DIR` (set by the installer). Also `verify_github_signature(secret, body: bytes, header) ->
  bool` and `handle_webhook(event, payload)` (push to the tracked branch -> background check+apply).
* `helper.py`: stdlib-only script (argparse): `git -C host_dir pull --ff-only` (if a git checkout; record
  previous HEAD), `docker compose -p <project> up -d --build <service>`, wait for health; on failure
  `git reset --hard <prev>` and `docker compose up -d --build` again; clear stdout logging; exit codes.
* Tests (real git in tmp dirs; no network): Git wrapper; evolve begin/edit/checks(fake commands)/finish in
  auto mode (merged + restart requested via a monkeypatched `services.request_restart`) and approve mode
  (proposal then approve); path traversal refused; rollback; contrib push mode against a local bare repo,
  PR + fork flow against a mocked GitHub API (httpx MockTransport) and a local bare "fork"; updater check
  & apply with a local bare upstream (code-only change -> restart requested; image-level change -> helper
  spawn requested on a fake docker); webhook signature; helper argument parsing/dry-run;
  supervisor: bootstrap clone from a fake APP_DIR git repo, origin URL, requirements hash, mark_good,
  rollback() with a bad commit, merge_image_into_source, and a short end-to-end run of `Supervisor` with a
  fake `minion/server.py` child (tiny HTTP /health server) covering: healthy -> marked good; exit 75 ->
  restart; broken commit -> rollback (monkeypatch module constants such as APP_DIR/SRC_DIR/RUN_DIR/
  HEALTH_URL/HEALTH_TIMEOUT; keep it under ~30 s).
