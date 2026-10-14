# Architecture

```
┌──────────────────────── your machine ────────────────────────┐        ┌────────────── one desktop (container) ──────────────┐
│ agent ── MCP / CLI / Python / HTTP ──► minion (pure stdlib)  │        │ tini → minion_agent.session                          │
│                                          │                   │ docker │   ├─ Xvfb :0 (1280x800, no TCP, xauth cookie)        │
│ browser ◄── live view / dashboard ───────┤ minion serve      │ exec   │   ├─ dbus-daemon + AT-SPI bus (accessibility on)     │
│                                          └──────────────────►│───────►│   ├─ JWM (window manager + taskbar, ~2 MB RAM)       │
│                                                              │ stdin/ │   ├─ agent daemon: JSON-lines RPC on a UNIX socket   │
│                                                              │ stdout │   │    screen · input · windows · a11y · OCR · recorder│
└──────────────────────────────────────────────────────────────┘        │   └─ apps: Firefox, LibreOffice, terminals, …        │
                                                                        └──────────────────────────────────────────────────────┘
```

## Host side (`minion/`)

| Module | Role |
|---|---|
| `desktop.py` | The `Desktop` SDK. Every other interface is built on it |
| `cli.py` · `mcp.py` · `server.py` | The CLI, the MCP stdio server (hand-written, zero dependencies) and the HTTP API, dashboard and live view (`http.server`) |
| `backends/docker.py` | One container per desktop, created with `docker create`. Copies the agent code in with `docker cp`, then starts it. Freeze is `docker pause`, snapshot and fork use `docker commit`. Works the same with Podman and remote Docker hosts |
| `backends/local.py` | Native Xvfb sessions on Linux: one process group, home directory and display per desktop. Freeze sends SIGSTOP to the desktop's processes, which are found by an environment marker |
| `channel.py` | A multiplexed JSON-lines RPC client over `docker exec -i … bridge.py` or a UNIX socket. Many calls can be in flight, for example live-view frames while an action runs |
| `profiles/` | TOML recipes turned into Dockerfiles. Images are layered by inheritance |
| `integrations/anthropic.py` | Claude computer use: a raw `tool_use` → `tool_result` adapter plus an Anthropic SDK toolset driver |
| `reaper.py` | Freezes idle desktops in long-running processes (the MCP server and `minion serve`) |

There are no ports: the host reaches the agent through `docker exec`. The live view streams JPEG frames over
HTTP long-polling and sends a frame only when the screen or the cursor changed.

## In the desktop (`minion/agent/`, copied to `/opt/minion/minion_agent`)

| Module | Role |
|---|---|
| `session.py` | Starts and supervises Xvfb, D-Bus, the AT-SPI bus and JWM, writes the generated wallpaper and the JWM config (the menu comes from the profile's apps), runs autostart commands, then serves the agent |
| `server.py` | The RPC daemon: `hello`, `screenshot`, `see`, `find`, `act`, `open`, `run`, `clipboard`, `windows`, `window`, `frame`, `input`, `record`, `status`, `cursor` |
| `perceive.py` | `see` (windows, accessibility tree, and OCR when needed) and target resolution (`@id`, text, `x,y`) |
| `a11y.py` | Walks AT-SPI with a time budget, prunes hidden and off-screen nodes, compacts wrappers and twins, collapses browser chrome, and reads the visible cells of spreadsheets |
| `screen.py` | Capture (Pillow + XCB), encoding, scaling, change detection, and *settle* (wait until the screen is quiet) |
| `xinput.py` · `windows.py` | xdotool input with key-name normalization, and EWMH windows (wmctrl, xwininfo, xprop) |
| `ocr.py` | Tesseract with 2× upscaling and line grouping |
| `recorder.py` | The flight recorder: a step log with thumbnails, exported as HTML or GIF |

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

| Piece | Idle RAM |
|---|---|
| Xvfb (1280×800×24) | ~15 MB |
| JWM | ~2 MB |
| dbus + AT-SPI | ~6 MB |
| agent daemon (Python + Pillow) | ~25 MB |

Apps account for the rest. An idle frozen desktop uses no CPU.
