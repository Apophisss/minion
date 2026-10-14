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

**Which models work best?**
Any model with tool use can use `see` + `act` (text-only models too). Vision models also use `screenshot`.
For Claude's native computer-use tool, see [computer-use.md](computer-use.md).

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
