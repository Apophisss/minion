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
| `see(ocr="auto", window=None, full_text=False, changes=False)` | `Observation`. `str(obs)` is the text an agent reads, and `obs.find("Save")` filters elements. `changes=True` returns only what changed since the last look (ids are stable). Text accessibility doesn't have is read with OCR in the screen's language; `ocr=True` also reads small pictures, and `ocr="heb"` (or `"ara+eng"`, ...) sets the language |
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
desk.select("@14", "Express shipping")  # a dropdown option, by its text
desk.click("button:Save")  # a kind of control and its label: button, link, field, tab, checkbox, menu, ...
desk.menu("File > Export As > Export as PDF...")  # any menu command; desk.menus() lists them with shortcuts
desk.path("~/Documents/report.pdf")  # fill the open file dialog and confirm (overwrite=True to replace)
desk.key("ctrl+s")
desk.scroll("down", 5, target="@30")
desk.drag("@4", "@9")
desk.wait_for("Saved", timeout=10)

# several actions in one round trip; dicts or strings
desk.act({"click": "File"}, {"click": "Save As..."}, "type report.docx", "key Return", screenshot=True)
```

The batch API accepts Claude computer-use shapes too (`{"action": "left_click", "coordinate": [x, y]}`).
`act(..., observe="changes")` adds the changed UI as text (`res.observation`), and `observe="crop"` adds an
image of just the changed region (`res.crop`).

## Code mode

```python
result = desk.script("""
launch("calc")
for item, price in [("Coffee", 3.5), ("Bagel", 2.25)]:
    write(f"{item}\\t{price}\\n")
write("Total\\t=SUM(B1:B2)\\n")
print(cells()["B3"])
""")
print(result.stdout)  # 5.75
```

The script runs inside the desktop with this API preloaded. Calls cost no model round trips, and only what
it prints comes back. If it fails, the error names the line of your script that failed.

| Function | |
|---|---|
| `see(ocr="auto", window=None, full_text=False, changes=False) -> str` | The screen as text, like `see` |
| `look(...) -> dict` | The same as data: `text`, `elements`, `windows`, `focused`, `ocr` |
| `elements(role=None, name=None) -> list[dict]` | Elements of the focused window. Each has `id` ("@12"), `role`, `name`, `x` and `y` (its center), `box` ([x, y, w, h]), and `text`, `value` and `states` when set |
| `find(text) -> list[dict]` | On-screen matches for a text, best first (`score`, `desc`, `x`, `y`) |
| `cells() -> dict[str, str]` | Visible spreadsheet cells: `{"A1": "Item", "B1": "Price", ...}`. A failed formula reads `#ERROR` |
| `formulas() -> dict[str, str]` | Formulas of the visible cells: `{"B7": "=SUM(B2:B6)"}` |
| `click(target, button="left", count=1, modifiers=None)` · `double_click` · `right_click` · `move` · `drag(a, b)` | Targets: `"@12"`, exact visible text, `"x,y"` or `[x, y]` |
| `write(text)` · `paste(text)` · `key(keys, repeat=1)` · `hold_key(keys, seconds)` | `write("a\tb\n")`: Tab and Return are key presses |
| `fill(target, text)` · `select(target, option)` · `scroll(direction, amount, target)` | |
| `menu(item)` · `menus() -> list[str]` · `path(file, overwrite=False)` | Menu commands by path (`"File > Save As"`), the app's menus with shortcuts, and the open file dialog |
| `read(file) -> str` · `convert(file, to, outdir=None) -> str` | Any document as text, and format conversion (`"pdf"`, `"docx"`, `"xlsx"`, `"csv"`, `"png"`…) |
| `wait(seconds)` · `wait_for(text, timeout=10, gone=False) -> bool` | |
| `launch(target, wait=12, install=True) -> dict` | An app (installed the first time), URL or file; waits for its window (and for a web page to load) |
| `run(command, timeout=60, input=None) -> dict` | A shell command (with optional stdin text): `code`, `stdout`, `stderr` |
| `screenshot(path="/tmp/screenshot.png", region=None, marks=False) -> str` | Saved inside the desktop |
| `windows()` · `focus(window)` · `clipboard(text=None)` | |
| `act(*steps, check=True) -> str` | Several steps at once (strings like `"click @3"` or dicts) |

Actions that fail raise `MinionScriptError`, so a script stops at the first problem instead of carrying on.

## Many desktops

```python
desks = Desktop.create_many("research", 4)  # in parallel, image prepared once
```

## Apps, shell and files

```python
desk.open("calc")  # profile app, URL, file in the desktop, or a command
desk.open("gimp")  # any app by name: installed the first time; .get("tips") has short tips for it
desk.open("google sheets")  # web apps open in the browser
r = desk.run("python3 -c 'print(6*7)'")  # RunResult(.code, .stdout, .stderr, .ok, .check())
desk.run("python3 -m http.server 8000", background=True)
desk.upload("data.csv", "~/Documents/")
desk.download("~/Documents/report.pdf", ".")
desk.write_text("~/notes.md", "# Notes")
desk.read_text("~/notes.md")
print(desk.read("~/Documents/budget.xlsx"))  # any document as text: docx, xlsx (+formulas), pptx, pdf, odt, ...
desk.convert("~/Documents/report.docx", "pdf")  # -> "/home/agent/Documents/report.pdf"
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
