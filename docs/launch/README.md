# Minion launch kit

Copy for announcing Minion 1.0, one file per channel, plus the facts the copy is allowed to use and the images to
post with it. Everything here is drafted from the repository's own docs. Nothing has been posted yet.

| File | Channel | Language |
|---|---|---|
| [show-hn.md](show-hn.md) | Hacker News (Show HN): title and the author's first comment | English |
| [product-hunt.md](product-hunt.md) | Product Hunt: name, tagline, description, topics, gallery, maker's comment | English |
| [reddit.md](reddit.md) | r/LocalLLaMA, r/ClaudeAI, r/selfhosted, r/opensource | English |
| [x-thread.md](x-thread.md) | X: an 8-post thread | English |
| [linkedin.md](linkedin.md) | LinkedIn | English |
| [hebrew.md](hebrew.md) | Israeli tech communities and LinkedIn | Hebrew |
| [chinese.md](chinese.md) | V2EX, Juejin, Zhihu | Simplified Chinese |
| [faq-responses.md](faq-responses.md) | Short answers to likely objections, for any thread | English |

The README is translated at the repository root: [简体中文](../../README.zh-CN.md) (mainland China, Singapore),
[繁體中文](../../README.zh-TW.md) (Taiwan, Hong Kong), [한국어](../../README.ko.md), [日本語](../../README.ja.md) and
[עברית](../../README.he.md). Link the matching one in posts for those communities.

## Describe Minion

**In one sentence**

> Minion gives every AI agent its own computer: featherweight, disposable Linux desktops in Docker that agents read
> as text and control over MCP, function calling, HTTP, a CLI or Python.

**In one paragraph**

> Minion is open-source (MIT) software that gives an AI agent a computer of its own instead of yours. Each desktop
> is a real Linux desktop in a small, unprivileged container on your machine: browsers, LibreOffice, IDEs,
> terminals, file dialogs, and Windows programs through Wine. Agents read the screen as text (a compact list of
> controls with stable `@ids` from the accessibility tree, with OCR as a fallback), act in batches or in Python
> that runs inside the desktop, and every action reports what changed. Desktops are ready in about 1.5 s, use
> 54–105 MB of RAM when idle and freeze to 0% CPU. Minion is MCP-first, with one-click installs for Claude Desktop,
> VS Code, Cursor and others and `minion connect` for every agent app on the machine, and the same tools work
> through function calling, HTTP, a CLI, Python and TypeScript, and Claude, OpenAI and Gemini computer use.

## Positioning

The angles below come from the market-research brief (Google Trends, worldwide, October 2026). The trend data is
context for choosing angles and channels. Don't quote it in public copy.

- Interest in "AI agent" grew about 38x from 2024 to 2026. "MCP server" went from no searches (December 2024) to a
  peak in June 2026. "computer use", "AI browser" and "browser use" rose sharply. Rising searches include OpenClaw,
  Claude Code, Codex, opencode, "ai agent builder/platform" and "playwright mcp".
- The highest relative interest in "AI agent" is in China, Singapore, South Korea, Taiwan, the Netherlands,
  Hong Kong, the USA, Israel (9th) and Australia. That is why the README has Chinese, Korean, Japanese and Hebrew
  versions, and why there are Hebrew and Chinese posts.

What follows for the copy:

1. **A disposable computer for your agent.** An agent that operates a computer shouldn't operate yours. Say
   "isolated", "disposable" and "safer than your own machine". Don't say "secure" or "safe" without a
   qualifier: the docs call a desktop "a sandbox, not a vault" ([agents.md](../agents.md#security-notes),
   [faq.md](../faq.md), [computer-use.md](../computer-use.md)).
2. **MCP-first.** Lead with one click in the agent app, or `minion connect`. Mention the MCP Registry entry.
3. **Works with the agents people already use.** Claude Code, Codex, Cursor, VS Code, Gemini CLI, and any MCP
   client.
4. **Beyond the browser.** Office documents, IDEs, terminals, file dialogs, installers and Windows programs, not
   only web pages.

Don't claim:

- Support for OpenClaw, opencode or any other agent that the docs don't name. "Any MCP client" is accurate.
  Test a specific agent before naming it.
- Benchmarks other than the ones in the table below, user numbers, testimonials or comparisons with "the
  fastest" or "the best".
- GPU support. Rendering is software-only ([faq.md](../faq.md)).

## Key facts and their sources

Use these numbers as written. If the README changes, the README wins.

| Fact | Say | Source |
|---|---|---|
| What it is | Featherweight Linux desktops that any AI agent can use; agents read the screen as text, act in batches or in code, and use any program or website | [README.md](../../README.md), [index.html](../index.html) |
| Task cost | Five real tasks: 4,356 tokens with Minion vs. 50,505 with screenshots (11.6× fewer). The lead for any post about cost: the "Computer Use is 45x more expensive" HN thread (495 points) shows people care | [benchmarks.md](../benchmarks.md) |
| Startup | Ready in about 1.5 s (1.2–1.8 s for every profile) | [README.md](../../README.md#efficiency-measured), [design.md](../design.md) |
| Idle memory | 54–105 MB per desktop, about 60 MB typical. Firefox and LibreOffice add their own when open (a few hundred MB each) | [README.md](../../README.md#efficiency-measured), [faq.md](../faq.md) |
| Freezing | Idle desktops freeze to 0% CPU and thaw in about 0.2 s | [README.md](../../README.md), [design.md](../design.md) |
| Parallel | 3 desktops in parallel: 3.0 s | [README.md](../../README.md#efficiency-measured) |
| Where measured | A 2-vCPU VM; `python scripts/bench.py` reproduces them | [README.md](../../README.md#efficiency-measured) |
| Screenshot cost | 1280×800: about 1,365 tokens; `detail="low"`: about 341; `observe="crop"`: about 200 | [README.md](../../README.md#efficiency-measured) |
| Text view | `see` of a LibreOffice window: about 920 tokens; of a terminal: about 50–90 | [README.md](../../README.md#efficiency-measured) |
| Diffs | `see(changes=true)` after typing a sentence: about 60 tokens instead of about 900 | [README.md](../../README.md), [design.md](../design.md) |
| Tool definitions | About 2,100 tokens for the 9 tools; about 230 in compact mode (one `computer` tool) | [README.md](../../README.md), [agents.md](../agents.md) |
| Agent Skill | About 100 tokens until the agent uses it, then about 1,100 | [agents.md](../agents.md#shell-agents-and-agent-skills) |
| Code mode | A 50-step GUI loop in one tool call; only what the code prints comes back | [README.md](../../README.md), [design.md](../design.md) |
| Profiles | `browser`, `office`, `dev`, `research`, `data`, `windows` (Wine), `base`; images of 187–707 MB that share layers; your own profile is a short TOML file | [README.md](../../README.md#profiles), [install.md](../install.md) |
| `minion connect` | Claude Desktop, Claude Code, Cursor, VS Code (and GitHub Copilot CLI), Devin Desktop/Windsurf, Gemini CLI, Codex, LM Studio, Cline, Kiro, Zed. One entry, a backup first, idempotent, reversible | [connect.md](../connect.md), [install.md](../install.md#minion-connect) |
| One click | A Claude Desktop extension (`minion.mcpb`, needs only Docker), buttons for VS Code, Visual Studio, Cursor, LM Studio, Goose and Kiro, a Claude Code plugin, and the MCP Registry entry `io.github.Apophisss/minion` | [README.md](../../README.md#get-started), [install.md](../install.md), [design.md](../design.md) |
| One line | `install.sh` / `install.ps1` install uv and Minion, then `minion setup` checks Docker, prepares a desktop and runs `minion connect` | [install.md](../install.md), [design.md](../design.md) |
| Web chat apps | ChatGPT, Claude.ai and Le Chat through `minion share`: a public HTTPS MCP URL (Cloudflare quick tunnel) with a fresh token; Ctrl+C stops it | [README.md](../../README.md), [install.md](../install.md#chatgpt-and-claudeai-on-the-web), [CHANGELOG.md](../../CHANGELOG.md) |
| Interfaces | MCP over stdio or Streamable HTTP, function calling (OpenAI Chat Completions and Responses, Anthropic, Gemini), HTTP with OpenAPI, a CLI and an Agent Skill, a Python SDK and a TypeScript client | [CHANGELOG.md](../../CHANGELOG.md), [design.md](../design.md) |
| Local models | Through OpenAI-compatible APIs such as Ollama, vLLM and LM Studio; small and local models do best with compact mode | [agents.md](../agents.md), [faq.md](../faq.md), [install.md](../install.md#lm-studio) |
| Frameworks | Recipes for the OpenAI Agents SDK, LangChain/LangGraph, LlamaIndex, CrewAI, smolagents, Pydantic AI, Google ADK and AutoGen. Verified up to loading the tools; the model side of the recipes was not run | [README.md](../../README.md), [integrations.md](../integrations.md) |
| Computer use | Claude's `computer_toolset_20260801` (all 17 actions) and the earlier `computer_20251124`; OpenAI and Gemini computer use | [README.md](../../README.md), [computer-use.md](../computer-use.md) |
| Hosts | macOS, Windows and Linux with Docker Desktop, OrbStack, Colima or Podman; images for `amd64` and `arm64` (Apple Silicon runs them natively); `windows` profile `amd64` only; Linux can run desktops without Docker, but not isolated | [faq.md](../faq.md) |
| Footprint | Zero dependencies: the host side is pure Python standard library (3.11+), about 10k lines | [README.md](../../README.md), [design.md](../design.md) |
| Isolation | One unprivileged container per desktop, no host mounts by default, no open ports (the host uses `docker exec`), `--offline`, `--memory`, `--cpus`. Passwordless `sudo` inside the container | [README.md](../../README.md#security), [index.html](../index.html), [SECURITY.md](../../SECURITY.md) |
| Humans | Live view with *Take control*, hand-off ("Please sign in") that waits for *Done*, a dashboard, and a flight recorder (HTML, GIF, or a Python script that replays the session with no model) | [README.md](../../README.md), [CHANGELOG.md](../../CHANGELOG.md) |
| Dogfooding | Claude agents used Minion for real office, web, development and MCP tasks, and every issue they found was fixed before 1.0 | [design.md](../design.md) |
| Release | 1.0.0, the first release; MIT license; `pip install minion-desktop` | [CHANGELOG.md](../../CHANGELOG.md), [README.md](../../README.md) |

## Links

| | |
|---|---|
| Repository | https://github.com/apophisss/minion |
| Website | https://apophisss.github.io/minion/ |
| Install guide | https://github.com/apophisss/minion/blob/main/docs/install.md |
| PyPI | https://pypi.org/project/minion-desktop/ |
| Claude Desktop extension | https://github.com/apophisss/minion/releases/latest/download/minion.mcpb |
| MCP Registry | https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.Apophisss/minion |
| Changelog | https://github.com/apophisss/minion/blob/main/CHANGELOG.md |
| Security model | https://github.com/apophisss/minion/blob/main/SECURITY.md |
| One-line install | `curl -fsSL https://raw.githubusercontent.com/apophisss/minion/main/install.sh \| sh` (macOS, Linux) · `irm https://raw.githubusercontent.com/apophisss/minion/main/install.ps1 \| iex` (Windows) |

## Images

The two main images are 1280×640 (2:1), the size the landing page declares for its link card (`og:image`).

| File | Size | What it shows | Use it for |
|---|---|---|---|
| [hero.png](../assets/hero.png) | 1280×640 | The logo, "Instant desktops for AI agents", Firefox, LibreOffice Writer and Geany windows, "Ready in ~1.5 s · 0% CPU when frozen", "MCP · CLI · Python · HTTP · Claude computer use" | The first Product Hunt gallery image, the LinkedIn post, the first post of the X thread, articles |
| [social-preview.png](../assets/social-preview.png) | 1280×640 | "Give every AI agent its own computer.", the three numbers (~1.5 s ready, 54–105 MB idle, 0% CPU frozen), and a Writer window next to its `minion see` output | The GitHub social preview (Settings → Social preview) and the landing page's link card; the second image anywhere |

Other images in [docs/assets](../assets/):

| File | Size | What it shows |
|---|---|---|
| [demo.gif](../assets/demo.gif) | 720×480 | An agent on a `research` desktop searching Wikipedia, made by `minion replay -o demo.gif` |
| [marks.png](../assets/marks.png) | 1280×800 | A Wikipedia page with an `@id` drawn on every clickable element (`screenshot --marks`) |
| [live-view.png](../assets/live-view.png) | 1440×784 | The live view of an `office` desktop, with *Take control*, Paste, Screenshot, Replay and Freeze |
| [dashboard.png](../assets/dashboard.png) | 1440×784 | The `minion serve` dashboard with four live desktops. |
| [office.png](../assets/office.png), [research.png](../assets/research.png), [dev.png](../assets/dev.png) | 1280×800 | Full-size desktops: a Writer document, Wikipedia in Firefox, Geany with a Minion script |
| [packaging/mcpb/icon.png](../../packaging/mcpb/icon.png) | 512×512 | The square icon, for the Product Hunt thumbnail and avatars |

## Before you post

- [ ] Check the numbers against the README on the day, and fill in the placeholders in square brackets.
- [ ] Try the one-line installer, the Claude Desktop extension and `uvx minion-desktop mcp` on a clean machine.
- [ ] Set [social-preview.png](../assets/social-preview.png) as the repository's social preview on GitHub.
- [ ] Decide how to talk about AI-assisted development. The git history shows most commits authored by Claude,
      and people will ask. There is a draft answer to fill in at the end of [faq-responses.md](faq-responses.md).
- [ ] Post one channel at a time and stay to answer comments. Don't ask anyone for upvotes: Hacker News, Product
      Hunt and Reddit all treat that as manipulation.
- [ ] The posts are written in the first person, for the maker. Change "I" to "we" if you post as a team.
