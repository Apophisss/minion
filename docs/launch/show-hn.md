# Show HN

## Title

Hacker News titles can be up to 80 characters. Keep it plain: no superlatives, no exclamation marks.

| | Title | Characters |
|---|---|---|
| **Use this** | Show HN: Minion – Disposable Linux desktops that AI agents read as text | 71 |
| Alternative | Show HN: Minion – Give your AI agent its own computer, not yours | 64 |
| Alternative | Show HN: Minion – Linux desktops for AI agents, controlled over MCP | 67 |

**URL:** `https://github.com/apophisss/minion`

Submit the URL, then post the comment below as the first comment, right away. A Show HN has to be something people
can try, and this one can be installed in a minute.

## First comment

Paste it as-is. Hacker News keeps paragraphs that are separated by blank lines, joins single line breaks, and shows
lines indented by two spaces as code. That is why every bullet has a blank line before it, and why there are no
asterisks (they turn into italics) or backticks (they show up literally).

```text
Hi HN, I made Minion. It gives an AI agent its own Linux desktop, in a container on your machine, so the agent works on a computer that isn't yours.

Why: agents increasingly need more than a browser: spreadsheets, word processors, IDEs, terminals, file dialogs, installers. The usual approach is screenshots plus coordinate guessing, which is expensive (a 1280x800 screenshot is about 1,365 tokens) and unreliable. I wanted the cheapest, most reliable way to give any agent a whole computer, without handing it mine.

How it works:

- Each desktop is one small container: Xvfb, a minimal window manager (JWM) and taskbar, D-Bus/AT-SPI, and a small Python agent. No VNC and no desktop environment. The host reaches the agent through docker exec, so nothing listens on a port.

- "see" reads the screen the way a screen reader does. The accessibility tree (GTK, Qt, Firefox, Chromium, LibreOffice) becomes a compact list of controls with stable ids, like @12 button "Save" (210,62). Tesseract OCR covers canvases and apps without an accessibility tree, such as Wine. Spreadsheets come out as A1: value.

- After an action you can ask for a diff instead of a re-read: about 60 tokens after typing a sentence, versus about 900 for a full look at a LibreOffice window.

- Every action waits for the screen to settle (and for pages to load) and reports what changed. Text targets are strict: clicking "Delete" never clicks "Delete all", and a miss fails with the closest candidates instead of clicking something else.

- Code mode: "script" runs Python inside the desktop with click/write/key/see/cells, so a 50-step GUI loop is one tool call and only what the code prints comes back.

- Idle desktops are paused with the cgroup freezer (0% CPU) and thaw in about 0.2 s on the next call.

- A person can watch any desktop live in the browser (JPEG frames over HTTP long-polling, no VNC) and take control, and the agent can hand off ("please sign in") and wait until they press Done.

On a 2-vCPU VM, every profile is ready in 1.2-1.8 s, an idle desktop uses 54-105 MB, and 3 desktops start in parallel in 3.0 s (python scripts/bench.py reproduces this). The 9 tool definitions cost about 2,100 tokens per request, or about 230 in compact mode (one "computer" tool with CLI-style commands), which suits small local models.

It's MCP-first, over stdio or Streamable HTTP, and "minion share" gives web apps like ChatGPT and Claude.ai an HTTPS URL through a Cloudflare quick tunnel. The same tools are also function-calling definitions for OpenAI, Anthropic and Gemini, an HTTP API with OpenAPI, a CLI with an Agent Skill, Python and TypeScript SDKs, and adapters for Claude, OpenAI and Gemini computer use. It's about 10k lines of Python, and the host side is pure standard library with zero dependencies. Claude agents used it for real office, web, development and MCP tasks before 1.0, and the issues they hit were fixed.

To try it, with Docker, OrbStack or Podman running:

  curl -fsSL https://raw.githubusercontent.com/apophisss/minion/main/install.sh | sh

That installs the minion command and runs "minion setup", which checks Docker, downloads a desktop image and adds Minion to the agent apps it finds (Claude Code, Codex, Cursor, VS Code, Gemini CLI and others). With uv you can also run the MCP server straight from PyPI: uvx minion-desktop mcp

Limitations:

- macOS and Windows need a container engine. Linux can run desktops natively on Xvfb, but those aren't isolated from your user account.

- No GPU. Rendering is software-only, which is fine for office work, browsing and development.

- Windows programs run through Wine, on x86-64 hosts only, and are read with OCR because Wine has no accessibility tree. OCR misreads some glyphs and skips icons.

- A desktop is a sandbox, not a vault. The agent has passwordless sudo inside the container, and anything on screen can carry a prompt injection. Keep credentials out and hand off to a human for sign-ins.

- The framework recipes (LangChain, CrewAI, LlamaIndex and others) were verified up to loading the tools. I haven't run the model side of each one.

Feedback I'd most like:

- Apps where see gives poor or bloated output. That output decides most of the token cost.

- Agents or clients where setup wasn't one step.

- Whether the isolation defaults match what you'd want before letting an agent loose on a desktop.

Repo (MIT): https://github.com/apophisss/minion

Docs: https://apophisss.github.io/minion/
```

## In the thread

- Answer every question, including the critical ones. [faq-responses.md](faq-responses.md) has short, honest answers
  to the usual objections (security, computer use, Operator, browser-use, Playwright MCP, E2B, cost, hosts).
- When someone reports a problem, ask for `minion doctor` output, or a `minion replay -o bug.html` timeline.
- Don't ask anyone to upvote or comment, and don't post the link where people will be asked to vote.
