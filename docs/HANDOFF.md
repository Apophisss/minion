# Continuing Minion development on your own computer

## 1. Install Claude Code
Source: https://code.claude.com/docs/en/setup.md

| OS | Command |
|---|---|
| macOS / Linux / WSL (recommended) | `curl -fsSL https://claude.ai/install.sh \| bash` |
| Windows PowerShell | `irm https://claude.ai/install.ps1 \| iex` |
| macOS (Homebrew) | `brew install --cask claude-code` |
| Windows (WinGet) | `winget install Anthropic.ClaudeCode` |
| Any (npm, Node.js 22+, no sudo) | `npm install -g @anthropic-ai/claude-code` |

Check with `claude --version` and `claude doctor`. Log in by running `claude` (browser prompt) or `/login`
inside a session - use your claude.ai subscription account (Pro/Max/Team/Enterprise); an API key also
works for local use (`ANTHROPIC_API_KEY`) but teleport needs the subscription login.

## 2. Get the code
```bash
git clone https://github.com/Apophisss/minion.git
cd minion
git checkout claude/blissful-mendel-5iraxj      # the branch with all the work (draft PR -> main)
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q                  # foundation tests should pass
```
Install Docker (Docker Desktop on macOS/Windows, Docker Engine on Linux) - Minion and its tests use it.

## 3a. Continue THIS conversation locally (teleport)
Source: https://code.claude.com/docs/en/claude-code-on-the-web.md

Inside the repo checkout (clean git state, same GitHub account as the web session):
```bash
claude --teleport            # pick the cloud session from the list
# or: claude --teleport <session-id>   (the claude.ai/code session menu "Open in > Terminal" copies it)
```
You get the branch checked out plus the full conversation history. Requirements: no uncommitted changes,
a checkout of the same repo (not a fork), the branch pushed, the same claude.ai account, and `git fetch`
must work without prompting (load your SSH key / credentials first). The local copy is independent from
the cloud session afterwards.

## 3b. Or start fresh locally
```bash
cd minion && claude
```
and give it this prompt:

> Read docs/plan/README.md, docs/ARCHITECTURE.md and docs/ROADMAP.md. Then implement the units in
> docs/plan/units/ in parallel (one workflow/agent per unit, all at once, following units/COMMON.md),
> write the missing `desktop` and `harnesses` unit specs from the outlines in docs/plan/README.md and
> implement them too, integrate everything, run the full test suite and a real `docker compose up`
> end-to-end check, run an adversarial review and fix the findings, then write the README and screenshots.

Later sessions: `claude --continue` (latest conversation in this folder) or `claude --resume` (picker).

## 4. Where things are
| What | Where |
|---|---|
| Architecture + contracts | `docs/ARCHITECTURE.md` |
| Build plan + status + unit specs | `docs/plan/` |
| Future roadmap + open decisions | `docs/ROADMAP.md` |
| Research (verified) | `docs/research/*.md` |
| Research drafts (unverified: MCP SDK 2.x snippets, desktop image, registry API) | `docs/research/drafts/` |
| Foundation code | `minion/{config,db,events,secrets,models,context,supervisor}.py` |
