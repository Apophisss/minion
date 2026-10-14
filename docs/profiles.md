# Profiles

A profile describes a desktop: which apps it has and how they're tuned. Profiles are small TOML files,
and each one extends another, so images share layers on disk.

```
base ─┬─ browser ─┬─ office ── data
      │           ├─ dev
      │           └─ research
      └─ (your own)
```

## Built-in profiles

| Profile | Apps | Tuning |
|---|---|---|
| `base` | xterm | JWM window manager, AT-SPI accessibility, Tesseract OCR, generated wallpaper, no animations or caret blink |
| `browser` | Firefox ESR + uBlock Origin | Blocks ads, trackers, cookie notices, newsletter and notification prompts. No first-run pages, password prompts, translation pop-ups or session-restore page. Downloads go to `~/Downloads` without a dialog. PDFs open in Firefox. Fonts for most scripts and emoji |
| `office` | Writer, Calc, Impress, Mousepad, PCManFM | Saves `.docx`/`.xlsx`/`.pptx` by default with no "keep format" prompt. No tip of the day, "what's new", donation or get-involved bars, and no recovery dialog after a crash. Metric-compatible fonts (Carlito, Caladea, Liberation) |
| `dev` | lxterminal, Geany, Chromium | git, Python (venv, pip), Node.js + npm, build-essential, jq, ripgrep, sqlite3. Chromium runs with accessibility on |
| `research` | Mousepad (notes) | poppler-utils (`pdftotext`), pandoc, Python requests, BeautifulSoup and lxml |
| `data` | everything in `office` + Python | pandas, NumPy, SciPy, matplotlib, seaborn, openpyxl, tkinter, sqlite3 |

`minion profiles` lists them, and `minion profiles office` shows one in detail.

## Your own profiles

Put a `.toml` file in `~/.config/minion/profiles/`. On macOS that's `~/Library/Application Support/minion/profiles/`,
on Windows `%APPDATA%\minion\profiles\`, and you can also set `$MINION_HOME/profiles`.

```toml
name = "designer"                 # defaults to the file name
title = "Designer"
icon = "🎨"
extends = "browser"               # any profile (default: base)
description = "Firefox plus GIMP and Inkscape."
packages = ["gimp", "inkscape"]   # Debian (trixie) packages
setup = ["install -d -o agent -g agent /home/agent/art"]   # extra build steps, run as root
env = { GTK_THEME = "Adwaita:dark" }  # environment for every app in the desktop
apps = [                          # shown in the menu and accepted by `open`
  { name = "GIMP", id = "gimp", command = "gimp" },
  { name = "Inkscape", command = "inkscape" },
]
autostart = ["gimp"]              # launched when the desktop starts
memory = "3g"                     # default memory limit
shm = "1g"                        # /dev/shm size (browsers like 1g)
size = "1440x900"                 # default screen size
tips = "Shown to agents when they create this desktop."

[files]                           # files baked into the image
"/etc/motd" = "Welcome to the designer desktop.\n"
```

The first `minion up designer` builds the image (`minion-custom-designer:latest`). It is rebuilt automatically
when the file changes. Use `minion build designer` to build ahead of time.

## Images

Built-in images are published as `ghcr.io/apophisss/minion-<profile>:<version>` for `linux/amd64` and
`linux/arm64`. If an image can't be pulled, Minion builds it locally from the bundled recipes, which takes a few
minutes the first time. Related settings:

| Variable | Default | |
|---|---|---|
| `MINION_REGISTRY` | `ghcr.io/apophisss` | where built-in images come from |
| `MINION_IMAGE_TAG` | the release's image tag | |
| `MINION_PULL` | `auto` | `auto` pulls if missing and builds if the pull fails; `never` always builds locally; `always` re-pulls |

The agent code inside a desktop always comes from the Minion version you run, because it is copied in when
the desktop is created. You never have to rebuild images to upgrade Minion.
