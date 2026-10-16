"""What real tasks cost an agent: Minion (the screen as text) vs. a screenshot-based computer-use agent.

Runs everyday tasks end to end on a real office desktop, through the same toolkit an MCP client calls,
and counts the tokens of every tool result the agent reads. The screenshot agent is priced from the GUI
actions the same task needs when every action returns a screenshot (the loop of Anthropic's and OpenAI's
computer-use tools), at the providers' published image prices. No model is called, so it costs nothing to run.

    python scripts/bench_tasks.py              # prints the table and writes docs/benchmarks.md
    python scripts/bench_tasks.py --keep       # keep the desktop afterwards

Tokens are counted with tiktoken's o200k_base when it is installed (else characters / 4).
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from minion.tools import Toolkit  # noqa: E402

DESKTOP = "bench-tasks"
W, H = 1280, 800
# One 1280x800 screenshot: Anthropic counts (w * h) / 750 tokens (images up to ~1.15 MP are not downscaled);
# OpenAI (high detail) scales it to 1229x768: 6 tiles of 512 px, 85 + 170 per tile.
CLAUDE_IMAGE = round(W * H / 750)
OPENAI_IMAGE = 85 + 170 * 6

try:
    import tiktoken

    _enc = tiktoken.get_encoding("o200k_base")
    COUNTER = "tiktoken o200k_base"

    def tokens(text: str) -> int:
        return len(_enc.encode(text))
except ImportError:  # pragma: no cover
    COUNTER = "characters / 4"

    def tokens(text: str) -> int:
        return max(1, len(text) // 4)


FORM = """<!doctype html><html><head><title>Sign up</title></head><body><h1>Sign up</h1>
<form onsubmit="document.getElementById('done').textContent='Thanks, ' + this.name.value + '!'; return false">
<p><label>Full name <input name="name"></label></p>
<p><label>Email <input name="email" type="email"></label></p>
<p><label>Country <select name="country"><option>Choose one</option><option>France</option>
<option>Israel</option><option>United Kingdom</option><option>United States</option></select></label></p>
<p><label><input type="checkbox" name="terms"> I agree to the terms</label></p>
<p><button>Submit</button></p></form><p id="done"></p></body></html>"""

NOTES = "\n\n".join(
    f"Section {i}. "
    + " ".join(f"Point {i}.{j}: the quarterly review covers revenue, costs and hiring." for j in range(12))
    for i in range(1, 10)
)

# Each task: what the Minion agent calls, and the GUI actions a screenshot agent needs for the same result
# (each returns one screenshot; the first look is a screenshot too).
TASKS = [
    {
        "name": "Write a report and export it as PDF",
        "calls": [
            ("open", {"target": "writer"}),
            ("act", {"actions": [{"action": "type", "text": "Quarterly report\n\nRevenue grew 12% this quarter.\n"}]}),
            ("act", {"actions": [{"action": "menu", "item": "File > Export As > Export Directly as PDF"}]}),
            ("act", {"actions": [{"action": "path", "path": "~/Documents/report.pdf", "overwrite": True}]}),
            ("files", {"action": "read", "path": "~/Documents/report.pdf"}),
        ],
        "gui": "look · open Writer · type the text · File · Export As · Export Directly as PDF · type the path · "
        "Enter · open the PDF to check it",
    },
    {
        "name": "Fill a spreadsheet with a formula and save it as .xlsx",
        "calls": [
            ("open", {"target": "calc"}),
            (
                "act",
                {
                    "actions": [
                        {
                            "action": "type",
                            "text": "Item\tPrice\nCoffee\t3.5\nBagel\t2.25\nJuice\t4\nTotal\t=SUM(B2:B4)\n",
                        }
                    ]
                },
            ),
            ("act", {"actions": [{"action": "key", "keys": "ctrl+s"}]}),
            ("act", {"actions": [{"action": "path", "path": "~/Documents/budget.xlsx", "overwrite": True}]}),
            ("files", {"action": "read", "path": "~/Documents/budget.xlsx"}),
        ],
        "gui": "look · open Calc · type the rows · ctrl+s · type the path · Enter · look at the cells to check them",
    },
    {
        "name": "Look something up on Wikipedia",
        "calls": [
            ("open", {"target": "https://en.wikipedia.org"}),
            (
                "act",
                {
                    "actions": [
                        {"action": "fill", "target": "Search Wikipedia", "text": "Ada Lovelace"},
                        {"action": "key", "keys": "Return"},
                        {"action": "wait_for", "text": "Analytical Engine"},
                    ]
                },
            ),  # its reply shows the article it went to: no need to look again
        ],
        "gui": "look · open the browser at wikipedia.org · click the search box · type and press Enter · read the "
        "article",
    },
    {
        "name": "Fill in and submit a web form",
        "calls": [
            ("open", {"target": "file:///home/agent/form.html"}),  # opening a page returns it, with its @ids
            (
                "act",
                {
                    "actions": [
                        {"action": "fill", "target": "Full name", "text": "Ada Lovelace"},
                        {"action": "fill", "target": "Email", "text": "ada@example.com"},
                        {"action": "select", "target": "Country", "option": "United Kingdom"},
                        {"action": "click", "target": "I agree to the terms"},
                        {"action": "click", "target": "button:Submit"},
                        {"action": "wait_for", "text": "Thanks"},
                    ]
                },
            ),
        ],
        "gui": "look · open the page · click the name · type · click the email · type · open the country list · "
        "pick the country · tick the box · click Submit · check the result",
    },
    {
        "name": "Read a multi-page document",
        "calls": [("files", {"action": "read", "path": "~/Documents/notes.docx"})],
        "gui": "look · open the document",
        "per_page": True,  # + a look at each page and a page-down between them (added below)
    },
]


def main(argv: list[str]) -> int:
    tk = Toolkit()
    tk.call("desktop", {"action": "remove", "desktop": DESKTOP})
    t0 = time.monotonic()
    made = tk.call("desktop", {"action": "create", "profile": "office", "name": DESKTOP})
    if made.is_error:
        print(made.text)
        return 1
    # Fixtures (not counted): a web form and a document.
    tk.call("files", {"action": "write", "path": "~/form.html", "text": FORM})
    tk.call("files", {"action": "write", "path": "~/Documents/notes.txt", "text": NOTES})
    tk.call("files", {"action": "convert", "path": "~/Documents/notes.txt", "to": "docx"})
    info = tk.call(
        "run", {"command": "minion-convert ~/Documents/notes.docx pdf >/dev/null && pdfinfo ~/Documents/notes.pdf"}
    )
    m = re.search(r"Pages:\s+(\d+)", info.text)
    pages = int(m.group(1)) if m else 3
    for task in (t for t in TASKS if t.get("per_page")):
        task["name"] = task["name"].replace("multi-page", f"{pages}-page")
        task["gui"] += "".join(f" · read page {i}" + (" · page down" if i < pages else "") for i in range(1, pages + 1))
    print(f"desktop ready in {time.monotonic() - t0:.0f}s; tokens counted with {COUNTER}\n")

    results = []
    for task in TASKS:
        start, minion_tokens, errors = time.monotonic(), 0, []
        for name, args in task["calls"]:
            res = tk.call(name, args)
            minion_tokens += tokens(res.text)
            if res.is_error:
                errors.append(f"{name}: {res.text[:200]}")
        steps = len(task["gui"].split(" · "))
        row = {
            "task": task["name"],
            "minion_calls": len(task["calls"]),
            "minion_tokens": minion_tokens,
            "seconds": round(time.monotonic() - start, 1),
            "gui_steps": steps,
            "claude_screenshot_tokens": steps * CLAUDE_IMAGE,
            "openai_screenshot_tokens": steps * OPENAI_IMAGE,
            "errors": errors,
        }
        results.append(row)
        flag = "  ERRORS: " + "; ".join(errors) if errors else ""
        print(
            f"{row['task']:<58} {row['minion_calls']} calls {minion_tokens:>6,} tokens {row['seconds']:>5}s | "
            f"{steps} screenshots {row['claude_screenshot_tokens']:>6,} (Claude){flag}"
        )
    if "--keep" not in argv:
        tk.call("desktop", {"action": "remove", "desktop": DESKTOP})
    write_doc(results)
    return 1 if any(r["errors"] for r in results) else 0


def definitions(compact: bool) -> int:
    """The tokens of the tool definitions, rounded to tens."""
    return round(tokens(json.dumps(Toolkit().definitions("anthropic", compact=compact))), -1)


def write_doc(results: list[dict]) -> None:
    total_m = sum(r["minion_tokens"] for r in results)
    total_c = sum(r["claude_screenshot_tokens"] for r in results)
    total_o = sum(r["openai_screenshot_tokens"] for r in results)
    words = ["One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve"]
    count = words[len(results) - 1] if len(results) <= len(words) else str(len(results))
    lines = [
        "# What tasks cost: Minion vs. screenshots",
        "",
        f"{count} everyday tasks, run end to end on an `office` desktop by `python scripts/bench_tasks.py`. The "
        "**Minion** column counts the tokens of every tool result the agent reads (the same text an MCP client gets). The "
        "**screenshot agent** columns price the same task done the way pixel-based computer use works: each GUI "
        f"action returns a {W}×{H} screenshot ({CLAUDE_IMAGE:,} tokens for Claude, {OPENAI_IMAGE:,} for OpenAI at high "
        "detail), plus a first look. No model is called; the step lists are in the script.",
        "",
        "| Task | Minion: calls · tokens | Screenshot agent: steps · Claude tokens · OpenAI tokens | Fewer tokens with Minion |",
        "|---|---|---|---|",
    ]
    for r in results:
        ratio = r["claude_screenshot_tokens"] / max(1, r["minion_tokens"])
        lines.append(
            f"| {r['task']} | {r['minion_calls']} · {r['minion_tokens']:,} | {r['gui_steps']} · "
            f"{r['claude_screenshot_tokens']:,} · {r['openai_screenshot_tokens']:,} | **{ratio:.1f}×** |"
        )
    lines += [
        f"| **All {count.lower()}** | {sum(r['minion_calls'] for r in results)} · **{total_m:,}** | "
        f"{sum(r['gui_steps'] for r in results)} · {total_c:,} · {total_o:,} | **{total_c / max(1, total_m):.1f}×** |",
        "",
        "Notes:",
        "",
        f"- Tokens are counted with {COUNTER}. Claude's tokenizer isn't public, so its exact counts differ "
        "somewhat. Only what the tools return is counted, on both sides; the model's own messages are left out.",
        "- The screenshot agent is priced generously: one screenshot per GUI action, no retries, no scrolling to "
        "find things, and no zooming in to read small text. Real runs usually take more.",
        "- Minion's agent also gets exact text: cell values and formulas, a PDF's words, a form's labels, so "
        "nothing has to be read off pixels. It needs fewer calls because one `act` can do several steps.",
        "- An action's reply includes what changed when the action went somewhere (a new page, window or dialog) or "
        "changed the screen, which is the look an agent would take next. So the script doesn't look again after "
        "one.",
        f"- Tool definitions are sent with every request in both cases: Minion's 9 tools cost about "
        f"{definitions(False):,} tokens, or about {definitions(True):,} in compact mode (Anthropic's format, "
        "counted the same way).",
        f"- Measured on {dt.date.today().isoformat()} on a 2-vCPU VM.",
    ]
    out = ROOT / "docs" / "benchmarks.md"
    out.write_text("\n".join(lines) + "\n")
    (ROOT / "docs" / "benchmarks.json").write_text(json.dumps(results, indent=1) + "\n")
    print(
        f"\nall {count.lower()}: Minion {total_m:,} tokens vs. {total_c:,} (Claude screenshots): {total_c / max(1, total_m):.1f}x"
    )
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
