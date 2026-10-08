# Minion roadmap

**Vision:** a self-hosted, open-source, always-on AI agent that turns an Anthropic API budget into a
working team: one chat that drives the best open-source agent harnesses, every MCP server, its own
computer, and its own code, and that keeps getting better by itself and through its community.
Think Meta Muse / OpenAI Dots, but yours, open, and self-improving.

## Design principles

1. **Reuse, don't reinvent.** Wrap the best open-source harnesses (OpenClaw, Hermes, opencode, Goose,
   Aider, ...) and MCP servers; upgrade them automatically as upstream improves.
2. **One conversation.** Every capability is reachable from one chat (web, voice, phone, Telegram,
   WhatsApp via OpenClaw, any OpenAI-compatible app).
3. **Self-improving, safely.** Every change to itself goes through a worktree, tests, a health-checked
   restart and automatic rollback; humans can require approval at any level.
4. **Shared by default, private when personal.** New generic capabilities flow back to the repo as PRs
   so every installation gets them; personal ones never leave the machine; secrets are never in code.
5. **Use the budget well.** Track spend, pace autonomous work to the monthly budget, and never burn tokens
   pointlessly.
6. **Easy.** One command to install, a browser to configure, zero manual upkeep.

## Phase 0 - Foundation ✅
Architecture & contracts, foundation modules, supervisor with rollback, research, unit specs
(`docs/plan/`).

## Phase 1 - "It works" (MVP)
- [ ] MCP hub (stdio / docker / streamable HTTP / SSE), registry search + one-click install, curated catalog
- [ ] MCP gateway at `/mcp` so every harness sees every tool
- [ ] Workshop: tools written by the user or by Minion, validated, hot-loaded
- [ ] Brain: Claude Opus 5.5 agent loop, native system tools, background runs, approvals, suggestions,
      parallel sub-agents, memory, skills, usage tracking
- [ ] Harnesses: OpenClaw + Hermes deployed and wired to the gateway; delegation from chat (`@openclaw ...`)
- [ ] Built-in desktop (Xvfb + noVNC + browser) driven by Claude computer use, watchable live
- [ ] Web UI (chat, voice, desktop, capabilities, evolution, settings), CLI
- [ ] Self-evolution with health-checked rollback; self-update from the repo; sharing as PRs
- [ ] One-line installer, `minionctl`, Docker Compose, CI

## Phase 2 - Muse/Dots parity
- [ ] More harnesses: opencode, Goose, Aider, Claude Code (optional), OpenHands (optional), weekly auto-upgrades
- [ ] Open WebUI as a rich chat front-end; hands-free voice mode; PWA for phones
- [ ] Telegram channel with approval buttons; WhatsApp/Slack/Discord through OpenClaw's channels
- [ ] Automations in natural language ("every morning ..."), goals backlog
- [ ] Frontier scout: discovers new MCP servers / harness versions / AI tools and proposes or installs them
- [ ] Self-improvement loop driven by failures, feedback and rollbacks
- [ ] Budget pacing ("use it or lose it" before the month ends)

## Phase 3 - Community flywheel
- [ ] CI validation of catalog contributions (tools, servers, agents, skills) + automatic smoke tests
- [ ] Contribution provenance: signed commits from installations, contributor reputation, review bots
- [ ] Catalog website (GitHub Pages) with search and one-click "add to my Minion"
- [ ] Prebuilt multi-arch images on GHCR; reproducible releases; changelog generated from catalog PRs
- [ ] Docs site, tutorials, demo videos, "Minion of the week" showcase

## Phase 4 - Safety and scale
- [ ] Docker socket proxy with an allowlist instead of the raw socket; optional rootless Docker / gVisor / Sysbox
- [ ] Secrets encrypted at rest; per-tool secret scoping; OAuth flows for MCP servers
- [ ] Prompt-injection defences: quarantine untrusted tool output, stricter policy for open-world tools
- [ ] Evals gate for self-evolution (regression suite of real tasks before merging a change)
- [ ] Per-task token budgets (task budgets API), cost dashboards per automation
- [ ] Multi-user with roles, audit log, SSO
- [ ] Kubernetes / Helm deployment, remote Docker hosts, GPU nodes for local tools

## Phase 5 - Personal OS
- [ ] Many minions: several personas, each with its own computer and harness team, collaborating
- [ ] Phone calls (SIP/Twilio voice), email & calendar out of the box
- [ ] Long-term memory graph, personal knowledge base, document workspace
- [ ] Federation: share capabilities between trusted instances; team mode
- [ ] Plugin SDK for third-party channels, UIs and harness adapters

## Open decisions for the maintainer
- **Name & branding:** "Minions" is a well-known film franchise trademark. Keep the name generic and never
  use its characters or visual style; consider a distinct logo early.
- **License:** MIT is assumed (`pyproject.toml`); confirm before publishing.
- **Contribution mode default:** `pr` (human review before code reaches every installation). `push` is
  only for maintainers.
- **Auto-update default:** `auto` for code-level changes; image-level updates need `MINION_HOST_DIR`
  (set by the installer).
