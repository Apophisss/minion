# Python SDK

```bash
pip install minion-desktop     # pure standard library: nothing else is installed
```

```python
from minion import Desktop

desk = Desktop.create("office")  # or Desktop.attach("office-1") / Desktop.attach()
desk.open("writer")
print(desk.see())  # Observation: .text, .elements, .windows, .focused, .ocr
desk.type("Hello!\n")
desk.screenshot("hello.png")
desk.remove()
```

`with Desktop.create(..., keep=False) as desk:` removes the desktop when the block ends.
`with Desktop.attach(name)` only closes the connection.

## Creating and finding desktops

```python
Desktop.create(profile="browser", name=None, size="1280x800", *, memory="", cpus="", network=True,
               mounts=[], env={}, ports=[], progress=print, keep=True, backend=None)
Desktop.attach(name=None)        # None: the current/most recent desktop
Desktop.list(stats=False)        # [DesktopInfo(name, profile, state, size, memory, cpu, ...)]
```

## Looking

| Method | Returns |
|---|---|
| `see(ocr="auto", window=None, full_text=False)` | `Observation`. `str(obs)` is the text an agent reads, and `obs.find("Save")` filters elements |
| `screenshot(path=None, *, region=None, max_width=None, scale=None, width=None, format="png", marks=False, grid=False, cursor=True)` | `Screenshot` with `.data`, `.width`, `.height`, `.scale`, `.save()`, `.base64()` and `.to_screen(x, y)` |
| `zoom(region, width=1024)` | A magnified region |
| `find(text)` | Matches with score and position, from the accessibility tree first and then OCR |
| `windows()` · `cursor()` · `size` · `hello()` · `status()` | |

## Acting

All actions return an `ActResult` (`.ok`, `.summary`, `.steps`, `.change`, `.opened`, `.closed`, `.focused`).
By default a failed action raises `AgentError`. Pass `check=False` to inspect the failure instead.

```python
desk.click("@12")  # an id from the latest see()
desk.click("Sign in")  # visible text
desk.click([640, 400], button="right")
desk.double_click("report.docx")
desk.type("hello\n")  # \n = Return, \t = Tab
desk.paste(long_text)  # through the clipboard
desk.fill("Email", "ada@example.com")  # finds the field by its label
desk.key("ctrl+s")
desk.scroll("down", 5, target="@30")
desk.drag("@4", "@9")
desk.wait_for("Saved", timeout=10)

# several actions in one round trip; dicts or strings
desk.act({"click": "File"}, {"click": "Save As..."}, "type report.docx", "key Return", screenshot=True)
```

The batch API accepts Claude computer-use shapes too (`{"action": "left_click", "coordinate": [x, y]}`).

## Apps, shell and files

```python
desk.open("calc")  # profile app, URL, file in the desktop, or a command
r = desk.run("python3 -c 'print(6*7)'")  # RunResult(.code, .stdout, .stderr, .ok, .check())
desk.run("python3 -m http.server 8000", background=True)
desk.upload("data.csv", "~/Documents/")
desk.download("~/Documents/report.pdf", ".")
desk.write_text("~/notes.md", "# Notes")
desk.read_text("~/notes.md")
desk.clipboard = "copied"
print(desk.clipboard)
desk.window("maximize", "Firefox")
```

## Lifecycle

```python
desk.freeze()
desk.thaw()  # 0% CPU while frozen; any call thaws automatically
desk.stop()
desk.start()
tag = desk.snapshot("before-import")  # disk state
desk.restore(tag)
twin = desk.fork("try-other-approach")
desk.recording("html", "session.html")  # flight recorder (also "gif")
desk.remove()
```

## Errors

`MinionError` is the base class. `NotFound` covers unknown desktops and profiles, `BackendError` covers
Docker or local session problems, and `AgentError` covers failed actions and bad targets. Messages are
written so that they can be shown to a model as they are.

## Raw access

`desk.call(method, params)` speaks to the in-desktop agent directly. See `minion/agent/server.py` for
the methods (`hello`, `screenshot`, `see`, `find`, `act`, `open`, `run`, `clipboard`, `windows`, `window`,
`frame`, `input`, `record`, `status`, `cursor`).
