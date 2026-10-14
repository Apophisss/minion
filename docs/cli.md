# CLI reference

`minion` is built for people and for agents with a shell. Every command accepts `-d NAME` (which desktop)
and `--json` (machine-readable output). With no `-d`, commands use the current desktop: the one you
created or `use`d last, otherwise the most recent running one.

## Desktops

| Command | |
|---|---|
| `minion up [PROFILE]` | Create and start a desktop (default profile `browser`). `-c N` creates N in parallel. Options: `--name`, `--size 1280x800`, `--memory 2g`, `--cpus 1.5`, `--offline`, `-v HOST:DESKTOP[:ro]` (repeatable), `-e KEY=VALUE`, `-p PORT` (publish a desktop port on 127.0.0.1), `--view` |
| `minion ls` | List desktops with live memory and CPU (`--fast` skips the stats) |
| `minion rm NAME… \| --all` | Remove desktops (their files go with them) |
| `minion stop / start [NAME]` | Stop (files are kept) or start |
| `minion freeze / thaw [NAME]` | Pause every process (0% CPU) or resume. Any other command also thaws |
| `minion fork [NAME] [NEW]` | Clone the desktop's disk state into a new desktop |
| `minion snapshot [NAME] [TAG]` · `minion snapshots` · `minion restore TAG` | Save and restore disk state |
| `minion use NAME` | Set the current desktop |
| `minion profiles [NAME]` | List profiles, or show one in detail |
| `minion pull PROFILE…` · `minion build PROFILE… [--all] [--push]` | Prepare images ahead of time, or build them locally |
| `minion logs` | The desktop's session log |
| `minion doctor` | Check the setup |
| `minion setup` | The first-run wizard, and safe to run again. It checks that Docker or Podman is installed and running (and says how to fix it if not), prepares the profiles you pick (`--profiles office,dev`, default `browser`, `none` to skip), and connects your agent apps. `--yes` takes the defaults without asking. Without a terminal it never waits: it uses the defaults and prints what it would have asked |

## Look

| Command | |
|---|---|
| `minion see` | The screen as text with `@ids`. `--changes` shows only what changed since the last look, `--ocr` always adds OCR, `--no-ocr` never does, `--window TITLE` describes another window, and `--full` keeps paragraphs whole |
| `minion shot [-o FILE]` | A screenshot (`.png`, `.jpg`, `.webp` or `-` for stdout). Options: `--region x,y,w,h`, `--max-width N`, `--marks` (draw `@ids`), `--grid`, `--no-cursor` |
| `minion windows` | List windows |

## Act

Targets are `@12` (from your latest `see`; the most reliable), exact visible text (`"Sign in"`), or coordinates
(`640,400` or `640 400`). Text targets must really be on screen: a click or `wait-for` never settles for a
fragment of what you asked for, and a miss fails with the closest candidates.

| Command | |
|---|---|
| `minion click TARGET` | `--double`, `--triple`, `--right`, `--middle`, `--mod ctrl`. Shortcuts: `dclick`, `rclick` |
| `minion type TEXT` | `--enter` presses Return afterwards. `--paste` pastes through the clipboard, which is fast for long text. `-` reads stdin |
| `minion key KEYS…` | `ctrl+s`, `Return`, `alt+Tab`, `ctrl+shift+t`, `F5`, or several in order (`minion key Tab Tab Return`). `-n 3` repeats. Unknown key names are errors |
| `minion scroll [up\|down\|left\|right] [N] [--at TARGET]` | |
| `minion drag FROM TO` · `minion move TARGET` | |
| `minion fill TARGET TEXT` | Replace a field's content (a label like `"Name"` finds its field). Refuses targets that aren't text fields |
| `minion select TARGET OPTION` | Pick a dropdown option by its text. `see` lists each dropdown's value and options |
| `minion wait-for TEXT [--timeout 15] [--gone]` | Wait until the text is visible on screen (or gone), and say where it was seen |
| `minion act STEP…` | Several actions in one round trip: `minion act "click @3" "fill @4 Ada" "type hi\n" "key ctrl+s"`. Also accepts JSON objects or lists, or `-` for JSON on stdin. `--observe changes` prints the changed UI, `--observe crop` saves an image of the changed region |
| `minion script FILE\|-\|CODE` | Run Python inside the desktop with the GUI API preloaded (`click`, `write`, `key`, `see`, `cells`, `launch`, `run`, …) |
| `minion open TARGET` | An app (`writer`, `calc`, `firefox`…), a URL, a file in the desktop, or a command |
| `minion run CMD…` | A shell command in the desktop. It returns the command's exit code. `-t 60` sets a timeout, `-b` runs in the background |
| `minion cp SRC DST` | Copy files: `minion cp report.pdf :~/Documents/` · `minion cp office-1:~/out.png .` |
| `minion clip [TEXT]` | Read or set the clipboard |
| `minion focus WINDOW [--action close\|maximize\|minimize\|restore]` | |

**Step strings** for `act`: `click|dclick|rclick|move TARGET` · `type TEXT` · `paste TEXT` · `fill TARGET TEXT` ·
`select TARGET OPTION` · `key KEYS [N]` · `scroll DIR [N] [TARGET]` · `drag FROM TO` · `wait SECONDS` ·
`wait_for TEXT` · `focus WINDOW`. The text of `type`, `paste` and `fill` is taken verbatim (quotes and spacing
included; one pair of outer quotes is removed), and `\n` is Return, `\t` is Tab and `\\` is a backslash, as
in `write()` in scripts. `minion type` itself types its argument exactly as your shell passes it.

Every action prints what happened and what changed. With `--shot FILE` it also saves a screenshot:

```text
$ minion click "Save As..."
✓ click menu item "Save As..." (155,215)
→ screen changed 8% (region 0,0 1280x800) · opened "Save As" · focused "Save As"
```

Exit codes: `0` success, `1` the action failed, `2` the desktop or profile wasn't found. `run` returns the
command's own exit code (`124` on timeout).

## Watch and integrate

| Command | |
|---|---|
| `minion view [NAME]` | Open the live view in your browser. It starts a background server if needed. `--no-open` prints the URL. `--ask "Please sign in, then press Done"` hands off to the human and waits (up to `--timeout 600` s) until they press Done, then prints their note. The exit code is 1 if they did not finish |
| `minion replay [-o FILE.html\|FILE.gif] [--open]` | Export the flight recorder |
| `minion serve` | The HTTP API, dashboard and live view. Options: `--host`, `--port 4747`, `--token`, `--no-auth`, `--idle-freeze 600` |
| `minion mcp` | The MCP server on stdio. Options: `--compact` (one `computer` tool), `--no-images` (text only, for clients that would send images to the model as base64 text), `--preload office,dev`, `--idle-freeze 600` |
| `minion share` | A public HTTPS MCP URL (`https://….trycloudflare.com/mcp?token=…`) to paste into ChatGPT, Claude.ai or Le Chat, through a Cloudflare quick tunnel (`cloudflared` if installed, else Docker). Each run has a fresh token, and Ctrl+C stops it. `files` upload/download stay off unless you pass `--files`. Also `--token`, `--port 4748`, `--tailscale` (Funnel instead), `--compact`, `--no-images`. See [remote.md](remote.md) |
| `minion connect [APP…]` | Add the MCP server to your agent apps' configs: Claude Desktop, Claude Code, Cursor, VS Code, Devin Desktop/Windsurf, Gemini CLI, Codex, LM Studio, Cline, Kiro, Zed. With no APP it finds them and asks which (`--all` or `--yes`: every one found). It merges one entry and keeps everything else, backs the file up first, and changes nothing when run again. `--list` shows each app's config and status, `--dry-run` the diff, `--remove` takes Minion out again, and `--compact` connects `minion mcp --compact`. See [connect.md](connect.md) |
| `minion tools [-f openai\|anthropic\|gemini\|openai-responses\|mcp] [--compact]` | Print tool definitions for any LLM API. `minion tools --call see` runs one |
| `minion skill [--install [DIR]]` | Print the Agent Skill (`SKILL.md`) that teaches an agent this CLI, or install it as `DIR/minion/SKILL.md` (default `~/.claude/skills`) |

Quote `~` paths so your own shell doesn't expand them: `minion open '~/Documents/report.docx'`.
