# Changelog

## 1.1.1

The live view on a phone or tablet.

- A phone's keyboard only opens for a real text field, so the live view had no way to type, and its toolbar
  overflowed a narrow screen. Now ⌨ opens a typing bar: type, then Send, with buttons for Enter, Backspace, Tab,
  Esc and scrolling, and a lock that hides a password. On the screen, a tap clicks, a long press right-clicks, a
  swipe scrolls and two fingers zoom. On a narrow screen the toolbar is one row, Copy, Paste and Freeze are under
  More, and the screen sits at the top, above the phone's keyboard.

## 1.1.0

Office work, measured on OSWorld, and the desktop for people too.

AI agents did 30 of OSWorld's LibreOffice tasks through screenshots alone and through Minion, scored by OSWorld's
own checkers. With Minion the computer sent the model half the tokens (9,372 per task against 17,974) for the same
success (Minion 1.1.0 96.6%, screenshots 93.2%, 1.0.0 89.9%: within noise on 30 tasks). What got in the agents'
way in 1.0.0 is fixed here, and on the same tasks 1.1.0 took 18% fewer steps and 16% less time than 1.0.0
([docs/osworld.md](docs/osworld.md), with what these numbers can and can't say; the harness is in
[scripts/osworld](scripts/osworld)).

**For people at the desktop**
- Saved sign-ins: `minion login github https://github.com/login` opens a desktop there in the live view; sign in
  by hand (2FA, CAPTCHAs and all), press Done, and `minion up --login github` starts desktops already signed in.
  Agents do the same with `desktop(action="create", login=...)` and list them with `desktop(action="logins")`.
  The live view's More › Save sign-in saves the desktop you're on. A sign-in is a snapshot of that desktop, kept
  in this computer's Docker; `minion share` doesn't offer them unless `--files`.
- The live view's Files panel: browse the desktop's folders, download a file (a folder as a .zip), upload files or
  drop them anywhere on the screen. A download that finishes in the desktop pops up a notice to get it, and a file
  dialog waiting for an upload can take the dropped file. During a hand-off, the agent's note says where the
  person put their files.
- The clipboard both ways: Copy (and Ctrl+C while in control) puts the desktop's clipboard on your computer's.
- A Keys menu for the keys your browser keeps (Ctrl+W, Ctrl+T, Alt+Tab, Alt+F4, F11), and an Open box for a URL,
  app or file.
- The dashboard can create a desktop signed in with a saved sign-in. The HTTP API has `files`, `download`,
  `upload`, `login` and `/api/logins`, and the SDK `Desktop.ls()`, `save_login()`, `logins()` and
  `create(login=...)`.

**LibreOffice**
- `select` picks a dialog's dropdown option from the list it opens (LibreOffice's and GTK's lists are windows of their
  own; typing the option's name picked "Leading" for "Double"), and an option that isn't there is an error that lists
  the real ones. `see` shows a dropdown's value when accessibility doesn't, read off the screen.
- Calc: `click C2:C29` selects a range and `fill B8 "=SUM(B2:B7)"` or `fill C2:C29 "=PROPER(B2)"` enters a value or a
  formula, empty cells and cells out of view included, through the Name Box. `see` lists the Name Box (the current
  cell) and the input line (that cell's whole formula, which accessibility cuts off), says where a sheet's data goes
  on below the view, keeps the spaces a cell's text has, and shows `=NA()` as `#N/A`.
- `see` lists an expanded expander's controls (Find & Replace's Regular expressions, Search in), empty paragraphs
  in Writer (and the cursor on one), and the folder of the document a window has open.
- Replies add what the status bar now says: a shape selected or its text being edited, the selection's position
  and size. A save names the format it wrote ("Excel format"), and warns when the content doesn't match the name.
- The office profile measures in centimeters ("20 cm" typed into an inch field was stored as 19.99 cm) and has
  python-pptx next to openpyxl and python-docx.

**Every app**
- `type` keeps the spaces at the ends of its text ("type , " typed one character).
- An @id from an earlier look is found again when a dialog in front, or one that is opening or closing, kept it out
  of the latest look: the step right after a dialog's OK no longer fails "no longer on screen".
- A click is a short press, as a person's (LibreOffice's add-sheet button ignored instant ones); a control clipped by
  its panel is clicked where it shows, and a list row scrolled out of its list is scrolled to first.
- `ctrl+click @12` (and shift+, alt+) and `click? TEXT` (a dialog's button, if the dialog comes) work as act steps.
- OCR: a sliver of a window no longer fails the whole window's OCR, the window's own title bar isn't read again, and
  right after a dialog closes `see` waits for LibreOffice to repaint instead of reading a half-drawn window.

**Reading files**
- `read` gives a sheet's dates as dates, its fills, hidden rows and columns, merged cells, filter and zoom, and each
  chart's kind, title and series; a deck's tables, pictures, audio, video and speaker notes; each docx table's size.
- `read --details` adds what formatting tasks check: a slide's background and each shape's place and size in cm,
  bullets, fonts and sizes; a paragraph's alignment, spacing and indents and its runs' formatting (bold, subscript,
  font, size, colour); a sheet's number formats and text colours.

**Install and release**
- An Install workflow runs the one-line installers on clean macOS, Windows and Linux machines and starts
  `minion mcp`, `uvx minion-desktop mcp`, `npx -y minion-desktop mcp` and the Claude Desktop extension as agent
  apps do. It found two Windows bugs, fixed: the installer stopped in a PowerShell session set to stop on errors,
  and the extension's self-test couldn't clean up.
- The release no longer uploads uv's `dist/.gitignore`; `screenshot --region` takes `x y w h` too.

## 1.0.0

The first release of Minion: instant desktops that any AI agent can use.

**Desktops**
- Desktops in Docker/Podman (or native Xvfb on Linux) that are ready in about 1.5 s, use 54–105 MB RAM idle,
  and freeze to 0% CPU automatically.
- Profiles: `base`, `browser`, `office`, `dev`, `research`, `data` and `windows` (Wine), each tuned for agents:
  no first-run wizards, pop-ups, cookie banners, recovery dialogs or AutoCorrect. Custom profiles are TOML files.
  `minion-install` adds any app at runtime: apt packages, `.deb`/`.AppImage`/archive URLs, `pip:` and `npm:`.
- **Any app by name**: `open gimp` (or `vscode`, `chrome`, `dbeaver`, any Debian package) installs the app the first
  time and answers with a few tips for it. Web apps open in the browser (`open gmail`, `open figma`), and apps that
  don't exist on Linux name their alternatives. Java apps get the accessibility bridge.

**Seeing**
- `see`: the screen as text with **stable** `@ids` from the accessibility tree, with OCR as a fallback.
- `see` covers web pages (including text inside cells, divs and inline code), editors (numbered lines with indentation),
  terminals, dropdowns with their value and options, and spreadsheet cells row by row (`row 2: @14 A2 North · @15 B2 120 (=B1*2)`), with failed
  formulas as `#ERROR`.
- `see(changes=true)` returns only what changed since the last look at that window, including new terminal output and
  changed editor lines. Moves and truncation don't count as changes. Long diffs fall back to the full view and say why.
- `see(menus=true)` lists every menu command with its keyboard shortcut. Open right-click menus are listed first.
- **Text accessibility doesn't have** is read with OCR where it is missing: slides, canvases, pictures of text, remote
  screens and programs without an accessibility tree. It is read in the screen's language, chosen from the scripts of
  its titles and labels or given with `lang`. Hebrew, Arabic, Russian, Chinese, Japanese, Korean and Hindi are built
  into the images, and others install on first use. Extra passes catch large text and light text on colour, and a
  cache means an unchanged picture is never read twice. On 24 photographed Hebrew slides, 94% of the words are read,
  up from 2%. `files read` reads image files and scanned PDFs the same way, and clicking on visible text that only
  OCR can find works in the text's language.
- **Documents as text**: `files read` / `minion read` return the text of docx, xlsx (values and formulas), pptx,
  odt/ods/odp, pdf (OCR for scans), epub, html, images and doc/xls/ppt. `files convert` / `minion convert` change
  formats, even while LibreOffice is open. Inside desktops: `minion-read` and `minion-convert`.

**Acting**
- Actions wait for the screen to settle, for web pages and documents to be ready, and for dialogs that appear a moment
  later. Each one reports what changed, including typing that an app still starting up only shows seconds later.
- Text targets match exactly: "Delete" never clicks "Delete all". A miss fails with the closest controls and their
  `@ids` instead of clicking something else.
- `fill` only types into text fields. `select` picks dropdown options. Unknown key names are errors.
- `menu` runs any menu command by its path ("File > Export As > Export as PDF...") without opening menus, and waits
  for the dialog that a command ending in "…" opens.
- `path` fills the open Open/Save/Export dialog with a full path and confirms (it waits for a dialog that is still
  opening); existing files are only replaced with `overwrite`, and the app's error boxes are reported.
- Targets can name a kind of control (`button:Save`, `link:Docs`, `field:Email`), and a control that is scrolled out
  of view is scrolled into view.
- Typing in LibreOffice is lossless for any language, and its coordinates are correct from the first look.
- **Code mode** (`script`): Python runs inside the desktop with a GUI API, so loops cost one call.
- **Macros**: export the recorded session as a Python script that replays it without a model.

**Everyday work** (found by AI agents doing 93 ordinary computer tasks, from "what's the date?" to "total the
attachment of Dana's email and reply with it"; see [docs/scenarios.md](docs/scenarios.md))
- An action's reply says what happened, not just that keys were sent: a web page's alert/confirm/prompt dialog
  (listed first by `see`, with @ids for its field and buttons), files saved, downloaded or deleted, a pop-up over
  the button a click was meant for (the click isn't sent), and a drag whose card didn't move. After a click or a key that
  changed the screen, it includes what changed, so the agent rarely needs another look. It waits while the app
  shows "Loading…" or "Generating…".
- `scroll-to TEXT` (`find`) brings text into view anywhere on a long page or list, loading more of an endless feed
  until it shows up. A web form that goes on below the fold is listed to its end, so one `act` fills all of it.
  `wait-for` counts text that is on the page but out of view.
- Fewer tokens for the same screen: tables, spreadsheet rows and toolbars one row per line, no labels repeating
  their control, no OCR of text accessibility already has (terminals, editors, form labels), no "picture with no
  text" notes on plain pages. Controls that share a label say where they are (`button "Empty" in "Spam"`).
- Rich text editors, unnamed check boxes and terminal programs that fill the screen (vim, htop) come out whole.
- `select` works on autocomplete fields and makes web pages react; `fill` sets sliders and date fields and says
  what a field shows if the page reformatted it. Typing is exact in every app and language (é, ש, 東, emoji), and
  in LibreOffice it no longer races the app. `goto` (a URL in the current tab), `close`, `copy` (an element's text to the clipboard),
  `rclick` and `dclick` work inside `act`, and a text target waits a moment for a control that is still appearing;
  Alt+F4 closes any window, Windows programs included.
- Windows programs: `path` fills Wine's file dialogs (Windows paths too), `open notepad FILE` opens the file, and
  OCR reads selected rows, lone buttons and digits that look like letters.
- `read` shows what text alone doesn't: bold cells, frozen panes, conditional formats and charts in a sheet; a
  table of contents, tracked changes, comments, images and page setup in a docx; and what a picture without text is.
  `convert` names its result (`convert a.csv b.xlsx`), takes several files, and turns web pages into documents.
- `run` no longer hangs on a command that leaves a server running (`(cd app && server &)`), and keeps only the
  ends of huge output instead of running the desktop out of memory.
- Images: `file`, `zip`, `htop` and `vim` in every desktop; openpyxl and python-docx in the office ones; `pip:`
  libraries from `minion-install` import in `python3`. The file manager lists files as a table, Firefox navigates to
  a typed URL instead of searching for it, and GIMP skips its welcome dialog.

**Measured**
- 93 everyday tasks done by AI agents, before and after the everyday-work fixes: 31% fewer calls, half the calls
  that failed, a third fewer screenshots and 36% fewer output tokens ([docs/scenarios.md](docs/scenarios.md)).
- Five real tasks cost an agent 8,668 tokens with Minion and 50,505 with a screenshot agent: 5.8× fewer
  ([docs/benchmarks.md](docs/benchmarks.md), `python scripts/bench_tasks.py`).
- A one-minute demo video: one job in a browser, a spreadsheet and a word processor in 12 tool calls and 2,372 tokens
  ([docs/assets/demo.mp4](docs/assets/demo.mp4), `python scripts/demo_video.py`).

**Every agent**
- One toolset (`minion/tools.py`), served as:
  - an MCP server over stdio or Streamable HTTP (`/mcp`): 9 tools, or one `computer` tool with `--compact`, and
    `--no-images` for text-only clients
  - function-calling definitions for OpenAI (Chat Completions and Responses), Anthropic and Gemini, with
    `Toolkit.run_calls()`
  - HTTP tool endpoints with OpenAPI
  - a CLI and an Agent Skill (`minion skill`)
  - a Python SDK and a TypeScript client (with Vercel AI SDK tools)
- Native computer-use adapters for Claude (`computer_toolset_20260801` and earlier tools), OpenAI and Gemini.
- Verified recipes for the OpenAI Agents SDK, LangChain/LangGraph, LlamaIndex, CrewAI, smolagents, Pydantic AI,
  Google ADK and AutoGen.

**Getting started**
- One-line installers (`install.sh`, `install.ps1`), the `minion setup` wizard, and `minion connect`, which adds
  Minion to Claude Desktop, Claude Code, Cursor, VS Code, Windsurf/Devin, Gemini CLI, Codex, LM Studio, Cline, Kiro,
  Zed, opencode and OpenClaw.
- One-click installs: a Claude Desktop extension (`minion.mcpb`), buttons for VS Code, Visual Studio, Cursor,
  LM Studio, Goose and Kiro, a Claude Code plugin, and an MCP Registry entry.
- `npx -y minion-desktop mcp` for MCP clients that expect an npx command: the npm package runs Minion from PyPI,
  in the same version, with uvx or pipx.
- `minion share`: a public HTTPS MCP URL (Cloudflare quick tunnel) for ChatGPT, Claude.ai and Le Chat.

**Working alongside people**
- Parallel desktops: `create count=N`, `Desktop.create_many()`, `fork`, `snapshot`/`restore`, and per-session
  current desktops.
- Live view with take-over, human hand-off (`view --ask`), a dashboard, and a flight recorder (HTML/GIF/script).
- Security: the HTTP server has a random token and CSRF and DNS-rebinding protection. Host file transfers are
  confined to one folder. Share URLs carry their own token.
