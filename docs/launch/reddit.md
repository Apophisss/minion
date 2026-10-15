# Reddit

Four posts, each written for its subreddit. They lead with something useful to that community and say in the
first line that you made Minion.

**Before you post**

- Read the subreddit's rules on the day. Some limit self-promotion or project announcements to certain days or
  threads, and some require a flair. Many still expect most of your activity there to be something other than
  your own links.
- Switch the editor to **Markdown mode** before pasting: the posts below are Markdown.
- Space the posts out over several days instead of posting all four at once, and don't cross-post the same text.
- Stay to answer comments. If someone asks whether the code was written with AI, answer plainly
  (see the last answer in [faq-responses.md](faq-responses.md)).

---

## r/LocalLLaMA

**Title:** Letting a local model use a whole Linux desktop as text: no vision model needed, ~230 tokens of tool
definitions (open source)

````markdown
**Disclosure: I'm the author.** Minion is free and open source (MIT).

If you want a local model to operate a desktop, two things usually get in the way: screenshots need a vision model (and a 1280×800 one costs about 1,365 tokens), and tool definitions eat context on every request. Minion tries to fix both.

- **The screen as text.** `see` turns the focused window into a short list of controls with stable `@ids`, taken from the accessibility tree, with OCR as a fallback: `@12 button "Save" (210,62)`. The model then clicks `@12`. Text-only models work; vision models can also take screenshots.
- **Small tool definitions.** Compact mode is one `computer` tool with CLI-style commands (`see`, `click @12`, `type 'hi'`, `run ls`): about 230 tokens of definitions instead of about 2,100 for the full nine tools. The docs recommend it for small and local models.
- **Diffs instead of re-reads.** After typing a sentence, `see(changes=true)` returns about 60 tokens instead of about 900.
- **Loops in one call.** `script` runs Python *inside* the desktop (`click`, `write`, `key`, `see`, `cells`, …), so twenty rows of data entry are one tool call, and only what the code prints comes back.

Each desktop is a small Docker container (Xvfb, a minimal window manager, a small agent; no VNC). It's ready in about 1.5 s, uses 54–105 MB when idle, and idle desktops freeze to 0% CPU. Profiles: `browser`, `office` (LibreOffice), `dev`, `research`, `data`, `windows` (Wine) and `base`.

A complete agent loop with Ollama (vLLM, LM Studio and other OpenAI-compatible APIs work the same way), after `pip install minion-desktop openai` and with Docker running:

```python
from openai import OpenAI
from minion.tools import Toolkit

tk = Toolkit()
client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
messages = [{"role": "user", "content": "On a research desktop, find the population of Iceland on Wikipedia."}]
while True:
    msg = (
        client.chat.completions.create(
            model="YOUR-MODEL", messages=messages, tools=tk.definitions("openai", compact=True)
        )
        .choices[0]
        .message
    )
    messages.append(msg)
    if not msg.tool_calls:
        break
    messages += tk.run_calls(msg.tool_calls)  # runs every call, returns the messages to send back
print(msg.content)
```

In LM Studio there's an install button, or `minion connect lmstudio`; add `"--compact"` to the server's `args` for the single tool.

The docs don't have results for local models yet, so the most useful feedback would be reports: which model and quantization, what task, and where it went wrong.

Repo: https://github.com/apophisss/minion · Function calling docs: https://github.com/apophisss/minion/blob/main/docs/agents.md
````

---

## r/ClaudeAI

**Title:** Give Claude its own Linux desktop: a one-click extension for Claude Desktop and a plugin for Claude Code
(open source)

Use the subreddit's project or showcase flair, if it has one.

````markdown
**Disclosure: I made this.** It's free and open source (MIT).

Minion gives Claude a separate computer to work on: a disposable Linux desktop in a container on your machine, with Firefox, LibreOffice, an IDE, a terminal, or Windows programs through Wine. Claude reads the screen as text (controls with stable `@ids` from the accessibility tree) and clicks, types, or runs Python inside the desktop. Before 1.0, Claude agents used it for real office, web, development and MCP tasks, and every issue they found was fixed.

**Setup** (Docker, OrbStack or Podman must be running)

- **Claude Desktop:** download [`minion.mcpb`](https://github.com/apophisss/minion/releases/latest/download/minion.mcpb) and double-click it. The extension carries Minion itself, so you don't install Python, uv or the `minion` command.
- **Claude Code:** `claude plugin marketplace add apophisss/minion && claude plugin install minion@minion`. That's the MCP tools plus a skill that teaches Claude to use them efficiently. For the server alone: `claude mcp add --scope user minion -- uvx minion-desktop mcp`.
- **Claude.ai in the browser:** run `minion share` and add the URL it prints as a custom connector ([steps](https://github.com/apophisss/minion/blob/main/docs/remote.md#claude-claudeai-desktop-and-mobile)). The URL works like a password, and Ctrl+C revokes it.

Then ask something like: *"Create an office desktop, write a one-page brief about our Q3 numbers in Writer and save it as brief.docx."*

**Details that matter with Claude**

- **Tokens.** After typing a sentence, `see(changes=true)` costs about 60 tokens instead of about 900 for a full read. Compact mode cuts the tool definitions from about 2,100 tokens to about 230. The Claude Code skill costs about 100 tokens until Claude needs a desktop.
- **Computer use.** If you build on the API, Minion is a ready environment for `computer_toolset_20260801` (all 17 actions) and the earlier `computer_20251124`, with screenshot scaling and coordinate mapping handled for you. `MinionComputer` plugs into the Anthropic SDK's tool runner ([docs](https://github.com/apophisss/minion/blob/main/docs/computer-use.md)).
- **You stay in the loop.** `minion view` opens a live view where you can take control. Claude can hand off ("Please sign in") and wait until you press Done. Every step is recorded: `minion replay -o run.html`.

**Safety.** Each desktop is an unprivileged container with no host mounts by default. Treat what's on screen as untrusted input (prompt injection), keep credentials out of desktops, and keep tool approval on for tools that change things.

Feedback welcome, especially about apps where `see` gives poor output.

Repo: https://github.com/apophisss/minion
````

---

## r/selfhosted

**Title:** Minion: Linux desktops for AI agents that run on your own hardware (Docker, MIT)

````markdown
**Disclosure: I'm the author.** Free and open source (MIT).

Minion runs disposable Linux desktops for AI agents on your own machine or server: one small, unprivileged container per desktop (Xvfb, the JWM window manager, a small Python agent; no VNC and no desktop environment). Agents read the screen as text and control it over MCP, HTTP or a CLI.

What I'd want to know as a self-hoster:

- **Resources.** Ready in about 1.5 s; 54–105 MB of RAM per idle desktop, plus whatever its apps use (Firefox and LibreOffice need a few hundred MB each while open). Idle desktops are paused with the cgroup freezer (0% CPU) and wake in about 0.2 s. Images are 187–707 MB per profile and share layers. For an always-on server, the docs suggest Linux with Docker and 2 GB of RAM or more.
- **Images.** Built in CI from `debian:trixie-slim` and published to GHCR for amd64 and arm64 (the Wine profile is amd64 only). You can build them yourself with `minion build --all`.
- **Exposure.** Nothing listens inside a desktop: the host talks to it through `docker exec`. `minion serve` (HTTP API, dashboard, live view, and MCP at `/mcp`) binds to 127.0.0.1, requires a random token, and refuses cross-site and DNS-rebinding requests. Put HTTPS in front of it and set `MINION_ALLOWED_HOSTS` to your domain.
- **Isolation.** No host mounts by default; `--offline`, `--memory` and `--cpus` per desktop. The agent has passwordless `sudo` *inside* the container, so it can install software there.
- **Your network.** Desktops browse from your network: pages see your IP, and desktops can reach your LAN. Keep that in mind before you share access.

On a server, as a dedicated user in the `docker` group (that group is root-equivalent on the host):

```bash
pipx install minion-desktop
minion pull browser office                     # download the images before anyone waits for them
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > ~/.minion-token && chmod 600 ~/.minion-token
minion serve --port 4747 --token "$(cat ~/.minion-token)"
```

Then put Caddy, nginx or Tailscale in front of `127.0.0.1:4747`. The full guide, with a systemd unit and each proxy's settings: https://github.com/apophisss/minion/blob/main/docs/remote.md#your-own-server-vps-or-home-server

The dashboard shows live thumbnails of every desktop, and you can watch any of them and take control from the browser.

I'd like to hear how you'd run this at home, and what's missing for that.

Repo: https://github.com/apophisss/minion
````

---

## r/opensource

**Title:** Minion: an MIT-licensed, zero-dependency way to give AI agents their own Linux desktop

````markdown
**Disclosure: I'm the author.**

Minion gives AI agents a computer of their own: a Linux desktop in a container, which agents read as text and control through MCP, function calling, HTTP, a CLI, or Python and TypeScript. It's MIT-licensed, and 1.0 is the first release.

Some choices that might interest this sub:

- **Zero dependencies.** The host side is pure Python standard library, and the contributing guide keeps it that way ("no dependencies, ever"). It's about 10k lines of Python.
- **Built on open-source parts:** Debian, Xvfb, the JWM window manager, AT-SPI for the accessibility tree, Tesseract OCR, Firefox, LibreOffice and Wine, each under its own license.
- **Upgrades don't need new images.** The in-desktop agent is copied into each desktop when it's created, so the host and the desktops always agree.
- **Profiles are small TOML files** that extend each other (`base → browser → office → data`), so images share layers on disk.
- **One toolset, many front ends.** The tools are defined once (`minion/tools.py`) and served as an MCP server, function-calling definitions for OpenAI, Anthropic and Gemini, HTTP with OpenAPI, and a CLI.

Where help would be most welcome:

- **Profiles** for a job (design, video, GIS, accounting, …). Often a 15-line TOML file.
- **Better `see` output for a specific app**, so its UI comes out clearer or in fewer tokens (`minion/agent/a11y.py`).
- **Tested setup recipes** for more agent clients.
- **Bugs with a repro:** run `minion replay -o bug.html` and attach the timeline.

Repo: https://github.com/apophisss/minion · Contributing: https://github.com/apophisss/minion/blob/main/CONTRIBUTING.md

Questions and criticism are welcome.
````
