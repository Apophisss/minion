# Architecture

```
┌──────────────────────── your machine ────────────────────────┐        ┌────────────── one desktop (container) ──────────────┐
│ agent ── MCP / CLI / Python / HTTP ──► minion (pure stdlib)  │        │ tini → minion_agent.session                          │
│                                          │                   │ docker │   ├─ Xvfb :0 (1280x800, no TCP, xauth cookie)        │
│ browser ◄── live view / dashboard ───────┤ minion serve      │ exec   │   ├─ dbus-daemon + AT-SPI bus (accessibility on)     │
│                                          └──────────────────►│───────►│   ├─ JWM (window manager + taskbar)                  │
│                                                              │ stdin/ │   ├─ agent daemon: JSON-lines RPC on a UNIX socket   │
│                                                              │ stdout │   │    screen · input · windows · a11y · OCR · recorder│
└──────────────────────────────────────────────────────────────┘        │   └─ apps: Firefox, LibreOffice, terminals, …        │
                                                                        └──────────────────────────────────────────────────────┘
```

## Host side (`minion/`)

| Module | Role |
|---|---|
| `desktop.py` | The `Desktop` SDK. Every other interface is built on it |
| `tools.py` | The agent toolset, defined once: 9 tools (or one compact `computer` tool), exported as MCP, OpenAI, Responses, Anthropic and Gemini definitions, with `run_calls()` and OpenAPI. MCP, HTTP and function calling all go through it |
| `cli.py` · `mcp.py` · `server.py` | The CLI, the MCP stdio server (hand-written, zero dependencies) and the HTTP API, dashboard and live view (`http.server`) |
| `skill/SKILL.md` | The Agent Skill that teaches shell agents the CLI (`minion skill`). `plugins/minion` packages it with the MCP server as a Claude Code plugin |
| `backends/docker.py` | One container per desktop, created with `docker create`. Copies the agent code in with `docker cp`, then starts it. Freeze is `docker pause`, snapshot and fork use `docker commit`. Works the same with Podman and remote Docker hosts |
| `backends/local.py` | Native Xvfb sessions on Linux: one process group, home directory and display per desktop. Freeze sends SIGSTOP to the desktop's processes, which are found by an environment marker |
| `channel.py` | A multiplexed JSON-lines RPC client over `docker exec -i … bridge.py` or a UNIX socket. Many calls can be in flight, for example live-view frames while an action runs |
| `profiles/` | TOML recipes turned into Dockerfiles. Images are layered by inheritance |
| `integrations/anthropic.py` | Claude computer use: a raw `tool_use` → `tool_result` adapter plus an Anthropic SDK toolset driver |
| `integrations/openai.py` · `integrations/gemini.py` | OpenAI and Gemini computer use: their actions and coordinate systems mapped onto `act`, with screenshots in each API's result shape |
| `reaper.py` | Freezes idle desktops in long-running processes (the MCP server and `minion serve`) |

There are no ports: the host reaches the agent through `docker exec`. The live view streams JPEG frames over
HTTP long-polling and sends a frame only when the screen or the cursor changed.

## In the desktop (`minion/agent/`, copied to `/opt/minion/minion_agent`)

| Module | Role |
|---|---|
| `session.py` | Starts and supervises Xvfb, D-Bus, the AT-SPI bus and JWM, writes the generated wallpaper and the JWM config (the menu comes from the profile's apps), runs autostart commands, then serves the agent |
| `server.py` | The RPC daemon: `hello`, `screenshot`, `see`, `find`, `act`, `open`, `run`, `script`, `clipboard`, `windows`, `window`, `frame`, `input`, `record`, `status`, `cursor` |
| `client.py` | The API that `script` code runs with (`see`, `cells`, `click`, `write`, `key`, `fill`, `wait_for`, `launch`, `run`, …), talking to the daemon over its socket |
| `install.py` | `minion-install`: apt packages, `.deb` / `.AppImage` / archive URLs, `pip:` and `npm:` packages |
| `perceive.py` | `see` (windows, accessibility tree, and OCR when needed) and target resolution (`@id`, text, `x,y`) |
| `a11y.py` | Walks AT-SPI with a time budget, prunes hidden and off-screen nodes, compacts wrappers and twins, collapses browser chrome, and reads the visible cells of spreadsheets |
| `screen.py` | Capture (Pillow + XCB), encoding, scaling, change detection, and *settle* (wait until the screen is quiet) |
| `xinput.py` · `windows.py` | xdotool input with key-name normalization, and EWMH windows (wmctrl, xwininfo, xprop) |
| `ocr.py` | Tesseract with 2× upscaling and line grouping |
| `recorder.py` | The flight recorder: a step log with thumbnails, exported as HTML or GIF, plus the portable action log that `macro` turns into a replayable script |

### Why accessibility first

Screenshots are expensive and imprecise for text. Most desktop apps publish their UI through AT-SPI
for screen readers: GTK, Qt, Firefox, Chromium (`--force-renderer-accessibility`) and LibreOffice (gtk3 VCL).
Minion turns that tree into a compact listing with `@ids`. Clicking `@12` re-reads the element's current position,
so moved elements still work, and elements that are off-screen are scrolled into view first. If an app has no tree
(canvas apps, games, remote screens), `see` falls back to OCR.

### Settling

After actions, the agent polls 1/16-size grayscale fingerprints of the screen every ~70 ms until nothing has
changed for 300 ms (2.5 s at most). Then it reports the changed fraction, its bounding box, and which windows
opened, closed or took focus. Animations, smooth scrolling, overlay scrollbars and caret blinking are disabled
in every profile, so "nothing changed" really means the UI is done.

## Resource budget

Measured in an idle `base` desktop (RSS includes shared libraries, so the sum is higher than the container's
~60 MB memory use):

| Piece | RSS |
|---|---|
| agent daemon (Python + Pillow; AT-SPI loads on first `see`) | ~43 MB |
| JWM (window manager + taskbar) | ~21 MB |
| Xvfb (1280×800×24) | ~20 MB |
| D-Bus + AT-SPI bus | ~22 MB |

Apps account for the rest. A frozen desktop uses no CPU.
