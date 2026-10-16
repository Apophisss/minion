# Answers to likely questions

Short, honest answers for comment threads. Adapt the wording to the thread, but keep the facts. Each answer names
the docs it comes from.

Answers that describe another product are marked **Check**: they are deliberately brief, and they don't come from
Minion's docs. Read that product's current docs before you post them.

## Is it safe to let an agent act on a computer?

Safer than letting it act on yours, and that's the point. Each desktop is its own unprivileged container (no
`--privileged`, default seccomp and capabilities) with no host mounts unless you add them, and nothing listens on
the network: the host reaches it through `docker exec`. `--offline` cuts network access, and `--memory` and `--cpus`
cap resources. Files the agent copies to or from your machine stay inside one folder.

It's a sandbox, not a vault. The agent has passwordless `sudo` inside the container, and anything on screen can
carry a prompt injection. Keep credentials out of desktops, hand off to a human for sign-ins and payments, and gate
consequential actions (the Claude computer-use driver takes a `confirm` callable for exactly this).

*Sources: README.md (Security), SECURITY.md, docs/agents.md.*

## What about prompt injection?

Minion doesn't solve it, and nothing on screen should be trusted: web pages, documents, window titles and the
clipboard can all carry instructions for the model. What Minion does is limit what a hijacked agent can reach: an
isolated desktop with no credentials in it, file transfers confined to one folder (so it can't copy `~/.ssh` into
an internet-connected desktop), `--offline` for untrusted documents, and a human hand-off for sign-ins.

*Sources: SECURITY.md, docs/agents.md.*

## How is this different from Anthropic's computer use?

They fit together. Computer use is Claude's tool for driving a screen, and it needs an environment: a screen to
capture and a mouse and keyboard to drive. Minion is that environment, with no Dockerfile or VNC to wire up. It
supports `computer_toolset_20260801` (all 17 actions) and the earlier `computer_20251124` and `computer_20250124`,
resizes screenshots to the model's limits and maps coordinates back. Claude can also use Minion's own tools, where
`see` gives exact text for fewer tokens than a screenshot.

*Sources: docs/computer-use.md, README.md.*

## How is it different from OpenAI Operator?

**Check:** Operator is OpenAI's agent product, and it works in a browser that OpenAI runs. Minion isn't an agent: it
is the computer, and it runs on your machine. You bring the model: OpenAI's computer-use model (Minion has an
adapter for it), ChatGPT itself through `minion share`, Claude, Gemini or a local model. And it's a whole desktop,
not only a browser.

*Minion side: README.md, docs/computer-use-openai-gemini.md, docs/remote.md.*

## How is it different from browser-use or Playwright MCP?

**Check:** both give an agent a browser. browser-use is a library for browser agents, and Playwright MCP is an MCP
server that drives a browser through structured page snapshots. If the whole task is web pages, a browser tool is
the lighter choice.

Minion drives a whole computer: browsers, office apps, terminals, IDEs, file dialogs, downloads, and anything you
can `apt-get install`. That matters once a task leaves the browser, like a downloaded spreadsheet that has to be
edited in LibreOffice, or an installer. The two combine well: in a `dev` desktop, start Chromium with
`--remote-debugging-port=9222`, run your Playwright script inside the desktop, and watch the same browser in the
live view.

*Minion side: docs/faq.md.*

## How is it different from E2B?

**Check:** E2B runs sandboxes for agents as a cloud service, including a desktop sandbox. Minion runs desktops on
your own machine or server: it's free under MIT, there's no service to sign up for, and the desktops run on
hardware you control. A hosted service makes sense when you need elastic capacity without running infrastructure.
Minion makes sense when you want local control, a text-first view of the screen and a one-step MCP setup.

*Minion side: README.md, docs/install.md.*

## What does it cost?

Minion is free and open source (MIT). You pay for your model's tokens and your own machine. Much of the design is
about the token bill: `see` instead of screenshots (a terminal is about 50–90 tokens, a 1280×800 screenshot about
1,365), diffs after the first look (about 80 tokens after typing a sentence), compact tool definitions (about 450
tokens per request instead of 3,300), code mode for loops, and macros that replay a finished task with no model at
all.

*Sources: README.md (Efficiency, measured), docs/faq.md.*

## Does it work on macOS and Windows?

Yes, with Docker Desktop, OrbStack, Colima or Podman. The desktops are Linux containers, and the `minion` command is
pure Python. Images are published for `amd64` and `arm64`, so Apple Silicon runs them natively. The exception is the
`windows` profile (Wine), which needs an x86-64 machine. On Linux you can also run desktops without Docker
(`MINION_BACKEND=local`), but those aren't isolated from your user account.

*Source: docs/faq.md.*

## How heavy is it?

An idle desktop uses 54–105 MB of RAM. Apps add their usual footprint: Firefox and LibreOffice need a few hundred MB
each while open. Every profile is ready in 1.2–1.8 s, and three desktops start in parallel in 3.0 s, measured on a
2-vCPU VM (`python scripts/bench.py` reproduces it). Idle desktops are frozen (0% CPU) and wake in about 0.2 s.
Images are 199–717 MB per profile and share layers. Cap each desktop with `--memory` and `--cpus`.

*Sources: README.md (Efficiency, measured), docs/faq.md, docs/install.md.*

## What leaves my machine?

Minion is software you run, not a hosted service. What leaves your machine:

- What your agent sends its model provider, including the screen text and screenshots it reads.
- What the desktops browse. They browse from your network, so pages see your IP address, and desktops can reach
  your local network.
- Downloads: the package from PyPI and the desktop images from GHCR.
- With `minion share`: Cloudflare terminates TLS for the quick tunnel and could see the requests. Tailscale Funnel
  or your own server avoid that.

The host side has no network listeners by default, and `minion serve` binds to `127.0.0.1` with a token.
There is no telemetry: Minion never reports anything anywhere. Its only network traffic is what you ask for
(pulling desktop images, installing apps inside a desktop, `minion share`).

*Sources: docs/design.md, docs/remote.md, docs/profiles.md, README.md (Security).*

## Why not a VM or a VNC desktop image?

Minion is built for agents rather than people: a text view of the screen with clickable ids, actions that wait for
the UI to settle and report what changed, desktops tuned to avoid pop-ups, snapshots and forks, idle freezing, and
MCP, SDK and HTTP interfaces. There is no VNC server and no desktop environment, so each desktop starts quickly and
stays small.

*Source: docs/faq.md.*

## Does it work with local models?

Yes. `see` and `act` are text, so text-only models work, and vision models can also take screenshots. Use any
OpenAI-compatible API (Ollama, vLLM, LM Studio and others) with `Toolkit().definitions("openai")`, or connect
LM Studio over MCP. Small and local models do best with the compact `computer` tool (`minion mcp --compact` or
`definitions(..., compact=True)`), which cuts the tool definitions to about 450 tokens. There are no published
results for specific local models yet.

*Sources: docs/faq.md, docs/agents.md, docs/install.md.*

## Can it use a GPU?

Not yet. Rendering is software-only (llvmpipe/SwiftShader), which is fine for office work, browsing and development.

*Source: docs/faq.md.*

## Can agents use Windows programs?

Many of them, through Wine, in the `windows` profile on x86-64 hosts. Wine has no accessibility tree, so `see` reads
Wine windows with OCR, which can misread some glyphs and skips icons. Anti-cheat and DRM that need kernel drivers,
apps that need a GPU, Store apps, 16-bit programs, sound and printing won't work.

*Sources: docs/faq.md, docs/windows-apps.md.*

## Can my team share one server?

Yes. `minion serve` runs the HTTP API, the dashboard, the live view and MCP at `/mcp` behind one token. Keep it on
`127.0.0.1` and put HTTPS in front (the docs cover Caddy, nginx and Tailscale). Whoever has the token controls every
desktop on that server, so treat it like a password.

*Source: docs/remote.md.*

## How do I see what the agent did?

`minion view` shows a desktop live, and you can take control from there. `minion replay -o run.html` (or `.gif`)
exports the flight recorder, and `desktop(action="macro")` turns the session into a Python script that replays it
with no model.

*Sources: docs/faq.md, README.md.*

## Is it production-ready? Who uses it?

It's new: 1.0.0 is the first release. Before it, Claude agents used Minion for real office, web, development and
MCP tasks, and every issue they found was fixed. Then AI agents did 93 everyday tasks with it, every call logged,
and the fixes their notes led to were measured on the same tasks: 31% fewer calls, half the failed calls, 36% fewer
tokens of output. The agent framework recipes were verified up to loading the tools,
not with a model. There are no user numbers or case studies to point to, so don't imply any.

*Sources: CHANGELOG.md, docs/design.md, docs/integrations.md, docs/scenarios.md.*

## Was it written with AI?

[Maker: answer in your own words, and be specific about how you reviewed and tested the code.]

Facts you can point to: the git history shows most commits authored by Claude, with co-author lines. CI runs lint,
unit tests on Python 3.11–3.14 on Linux, macOS and Windows, integration tests on local and Docker desktops, and an
image build, and the Install workflow installs Minion on clean macOS, Windows and Linux machines. AI agents did 93
everyday tasks with it before 1.0, and the tasks, the method and the results are in the repository. The framework
recipes are verified up to loading the tools.

A draft to start from (keep only what is true for you):

```text
Yes, most of the code was written with Claude, and the git history says so. [What you did yourself: the idea, the
design decisions, reviewing, testing.] Rather than ask you to trust that, I tried to make it checkable: CI on
Linux, macOS and Windows, installs tested on clean machines, and 93 everyday tasks done by AI agents with every
call logged, before and after the fixes, all in the repo. Bug reports with a replay (minion replay -o bug.html)
are the most useful thing you can send.
```

*Sources: the git log, CONTRIBUTING.md, docs/design.md, docs/integrations.md, docs/scenarios.md,
.github/workflows/.*
