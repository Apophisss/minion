# Unit: Web UI (the face of the project - make it beautiful)

Files you own: `minion/web/**` (index.html, app.js, style.css, manifest.webmanifest, icon.svg, i18n),
`tests/test_web.py`, `docs/screenshots/*.png`, and a dev-only stub server `tests/fixtures/web_stub.py`.

A single-page app, no build step, no external CDNs (self-hosted, offline-friendly), vanilla JS (ES modules
OK), served by FastAPI at `/`. It talks ONLY to the REST contract in ARCHITECTURE.md §5.11 (SSE for live
updates). It is the first thing people see when the project goes public: modern, clean, delightful
(think Linear/Arc/Raycast polish), dark + light themes, smooth micro-interactions, responsive down to
phones (PWA manifest + icon so it can be installed on a phone home screen).

Screens / features:
* Login (paste admin token; stored as cookie via `POST /api/login`) and first-run Setup (paste the
  Anthropic API key when `/api/setup/status` says `needs_api_key`).
* Chat (home): session list, message stream with markdown rendering (implement a small safe renderer:
  escape HTML first; code blocks with copy button, inline code, bold/italic, links, lists, tables),
  `dir="auto"` per message (Hebrew/RTL works naturally), live run cards (thinking/progress updates, tool
  calls collapsible with inputs/results, queued state), approval cards (Approve / Deny / Always allow),
  suggestion chips with "Build it", cancel button, feedback 👍/👎 on answers, agent picker
  (Minion or a specific harness via `target`), attach images (paste/drag -> data URL in the message
  content). Re-attaching to a running run after reload (runs keep going server-side).
* Voice: mic button using the Web Speech API (SpeechRecognition, language from the UI language: he-IL /
  en-US, interim results), read-aloud via speechSynthesis, and a hands-free "voice mode" (listen -> send ->
  speak the answer -> listen again) with a clear visual state. Gracefully hidden when unsupported.
* Desktop: live noVNC viewer in an iframe (`/desktop/vnc/vnc.html?autoconnect=1&resize=scale&path=desktop/vnc/websockify`),
  start/stop, screenshot fallback, "take over"/"view only" toggle (noVNC `view_only` param).
* Capabilities: MCP servers (status, tools count, enable/disable/restart, add form, registry search with
  one-click install), Tools (all tools incl. workshop; a code editor textarea with line numbers for workshop
  tools; test-call form), Agents/Harnesses (templates with best_for, deploy, logs, upgrade, send),
  Skills & Memory.
* Automations (schedules CRUD + run now), Goals, Suggestions inbox.
* Evolution: history timeline (evolve/update/rollback/contribute), proposals (approve/reject with diff
  view), update status (check/apply), contributions list.
* Usage & budget (cost this month vs budget, pace bar, by purpose), Settings (persona name/style,
  language, model, effort, autonomy, budget, approvals, evolve/update/contribute modes, secrets
  management with values write-only).
* Global: live notification toasts from `/api/events`, status indicators (brain/docker/desktop/agents),
  keyboard shortcuts (Ctrl/Cmd+K command palette to jump between screens and run quick actions),
  i18n English + Hebrew (full RTL layout when Hebrew is selected; default from navigator.language).

Testing & screenshots:
* `tests/fixtures/web_stub.py`: a FastAPI app serving `minion/web` plus stub implementations of the
  endpoints with realistic sample data (sessions with a Hebrew + English conversation, tool cards, an
  approval card, suggestions, servers, agents, usage) so the UI can be exercised without the real backend.
* `tests/test_web.py`: static files exist, index references assets, no external URLs, JS has no syntax
  errors (`node --check` on each .js file when node is available).
* Screenshots for the README: install Playwright for Python into the venv WITHOUT downloading browsers
  (`PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 $V/bin/pip install playwright`), launch Chromium with
  `executable_path` from `/opt/pw-browsers` (find the chrome binary there), run the stub server with uvicorn,
  and save `docs/screenshots/{chat,chat-he,desktop,capabilities,evolution,mobile}.png` (1440x900, mobile
  390x844). Look at the screenshots yourself (Read tool) and iterate on the design until it looks great.
