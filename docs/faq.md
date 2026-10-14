# FAQ

**Does it work on macOS and Windows?**
Yes, with Docker Desktop (or OrbStack, Colima, Podman). Desktops are Linux containers, and the `minion` command is
pure Python. Images are published for `amd64` and `arm64`, so Apple Silicon runs them natively.

**Do I need Docker?**
On Linux, no: `MINION_BACKEND=local` runs desktops as native Xvfb sessions using the apps installed on the host
(`sudo apt-get install xvfb xdotool wmctrl x11-utils jwm python3-pil python3-gi gir1.2-atspi-2.0 at-spi2-core tesseract-ocr xclip`).
Local desktops start faster but are not isolated from your user account.

**How is this different from a VM or a VNC desktop image?**
Minion is built for agents rather than people. It gives them a text view of the screen with clickable ids, actions
that wait for the UI to settle and report what changed, desktops tuned to avoid pop-ups, snapshots and forks,
idle freezing, and MCP, SDK and HTTP interfaces. There is no VNC server and no desktop environment, so each
desktop starts in about a second and stays small.

**How is it different from browser automation (Playwright, browser-use)?**
Those drive a browser through the DOM. Minion drives a whole computer: browsers, office apps, terminals, IDEs,
file dialogs, downloads, and anything you `apt-get install`. The two combine well. In a `dev` desktop, start Chromium with
`--remote-debugging-port=9222 --user-data-dir=/tmp/cdp` and run your Playwright script *inside* the desktop
(`minion run "python3 -m venv ~/pw && ~/pw/bin/pip install playwright && ~/pw/bin/python script.py"`, connecting to `http://localhost:9222`). A human can
watch the same browser in the live view while it runs.

**Which models and agents work?**
Any model with tool use. `see` and `act` are text, so text-only models work too, and vision models can also
use `screenshot`. Small and local models do best with the compact `computer` tool (`minion mcp --compact` or
`definitions(..., compact=True)`). Models trained for computer use can drive desktops natively: see
[computer-use.md](computer-use.md) for Claude and [computer-use-openai-gemini.md](computer-use-openai-gemini.md)
for OpenAI and Gemini. To connect agents and frameworks, see [agents.md](agents.md) and
[integrations.md](integrations.md).

**How do I keep token costs down?**
Prefer `see` to screenshots, and `see(changes=true)` or `act(..., observe="changes")` after the first look
(a few dozen tokens instead of about a thousand). Put loops and data entry in one `script` call. Use
`screenshot(detail="low")` or `observe="crop"` when you need pixels. Use compact mode for the tool definitions.
Once a task works, export it with `desktop(action="macro")` and replay it with no model at all.

**How many desktops can I run at once?**
As many as memory allows. An idle desktop uses about 55–105 MB, and apps add their usual footprint (Firefox
and LibreOffice need a few hundred MB each while open). Frozen desktops use no CPU. Use `--memory` and `--cpus`
to cap each desktop, and `minion up -c 8` or `desktop(action="create", count=8)` to start several in parallel.

**Can agents use Windows programs?**
Many of them, through Wine: `minion up windows`. See [windows-apps.md](windows-apps.md).

**Can a desktop use the GPU?**
Not yet. Rendering is software-only (llvmpipe/SwiftShader), which is fine for office work, browsing and development.

**Can I keep a desktop around?**
Yes. Desktops persist until `minion rm`, and stopping keeps their files. Use `-v ~/work:/home/agent/work` to
share a folder, or `minion cp` / `files` to move data. Snapshots are ordinary Docker images (`minion-snapshot:*`).

**How do I see what the agent did?**
`minion replay -o run.html` (or `.gif`) exports the flight recorder. `minion view` shows the desktop live.

**Is it safe to let an agent use a desktop?**
It is safer than letting it use your computer. Each desktop is an isolated, unprivileged container. Treat
on-screen content as untrusted, keep secrets out, and use `--offline` for untrusted files.
See [SECURITY.md](../SECURITY.md).

**Something looks wrong. How do I debug?**
`minion doctor` checks your setup, `minion logs` shows the desktop's session log, `minion view` lets you watch,
and `minion shot --marks` shows what the agent can target.
