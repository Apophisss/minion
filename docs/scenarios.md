# 93 everyday tasks: where agents lost time with Minion, and what changed

To make Minion better at ordinary computer work, AI agents were given 93 everyday tasks to do with it, from the
trivial ("what's the date on this computer?", "zip this folder") to the multi-app ("find Dana's email with the
Q3 figures, total its attachment and reply with the total"). Each agent was a fresh session that learned Minion
from `minion skill`, did its batch as efficiently as it could, and wrote down every bit of friction: a call that
failed, a reply that said "✓" over a click that a pop-up swallowed, a dialog it couldn't see, a screenshot it had
to take, output it had to wade through. Every call was logged. The tasks, the website they use and the scripts
are in [scripts/scenarios](../scripts/scenarios).

The friction notes became the list of fixes ([CHANGELOG](../CHANGELOG.md), "Everyday work"). Then the same 93 tasks
were given to new agents on the fixed Minion, and measured the same way.

All 93 tasks were done in both runs (the checks passed). What it took:

| | Before | After | |
|---|---:|---:|---:|
| Minion calls | 491 | 339 | **−31%** |
| Calls that failed | 28 | 14 | **−50%** |
| Screenshots | 21 | 14 | −33% |
| Tokens of Minion's output | 156,272 | 99,769 | **−36%** |
| Seconds in Minion | 1,615 | 1,447 | −10% |

| Batch | Tasks | Calls | Failed | Screenshots | Output tokens |
|---|---:|---:|---:|---:|---:|
| Web pages 1 (forms, wizard, table, feed, pop-ups, dialogs, iframe, drag and drop…) | 15 | 49 → 43 | 0 → 0 | 0 → 0 | 17,201 → 11,312 |
| Web pages 2 (new tabs, shadow DOM, canvas, long pages, a rich text editor, real sites…) | 15 | 50 → 48 | 2 → 0 | 3 → 3 | 16,378 → 19,088 |
| Office documents (Writer, Calc, Impress) | 15 | 99 → 54 | 9 → 2 | 4 → 2 | 46,803 → 20,224 |
| Everyday chores ("what's the date?", a calculator, the file manager…) | 17 | 105 → 61 | 5 → 2 | 5 → 6 | 22,597 → 13,034 |
| Multi-app workflows (webmail + spreadsheet, a shop, Wikipedia to a chart…) | 7 | 51 → 36 | 4 → 3 | 2 → 0 | 26,064 → 12,573 |
| Development (a terminal, vim, htop, Geany, Chromium, git) | 10 | 48 → 30 | 2 → 1 | 2 → 1 | 10,134 → 7,922 |
| Media (GIMP, a paint program, a video) | 7 | 31 → 27 | 3 → 3 | 1 → 0 | 8,198 → 8,485 |
| Windows programs (Notepad, Command Prompt, Registry Editor, Explorer) | 7 | 58 → 40 | 3 → 3 | 4 → 2 | 8,897 → 7,131 |

The biggest wins are where an agent used to need a look after nearly every step: office documents (−45% calls,
−57% tokens), everyday chores (−42% calls) and multi-app workflows (−29% calls, −52% tokens). Web pages on real
sites (Wikipedia) cost about as much as before: their pages are long either way. Screenshot images aren't in the
token count; each one is about 1,365 more tokens for Claude.

Five batches were run again on the final code; development, everyday chores and workflows were measured on the
code as it was midway (before the last round of fixes: typing pace outside browsers, scroll-to replies, rich text
editors, the review fixes).

## What the agents ran into, and what Minion does now

| Before | Now |
|---|---|
| A page's alert/confirm/prompt dialog was invisible to `see` (only OCR saw it, without @ids), and the reply to the click that opened it just said "screen changed 80%" | `see` lists the dialog first with @ids for its field and buttons, and the reply says "the page opened a dialog: …" |
| A pop-up that appeared over the page swallowed clicks while every step reported "✓" | The click isn't sent, and the batch stops saying what is on top: `covered by a pop-up layer (with dialog "Newsletter")` |
| A download or a save gave no sign of where the file went | `new file ~/Downloads/expenses-september.csv (1 KB)`, `saved ~/Documents/report.docx (12 KB)` |
| A slow report ("Generating…") took a click, a look, a wait and another look | The click waits while the app says it is working and the reply shows the result |
| `see` only listed what was on screen: an endless feed took guessed End presses, a long form a scroll and another look | `scroll-to "Entry 87"` finds text anywhere, loading more of a feed; the rest of a form is listed under the visible part |
| A clicked button that changed the page in place (a wizard's next step, a form's result) needed another look | The reply includes what changed |
| Tables (one cell per line), toolbars (one button per line), labels repeating their control, OCR of text accessibility already had | One row per line, labels dropped, OCR only where it adds something: the same screens in far fewer tokens |
| `type` dropped é, 京 or emoji in Firefox and LibreOffice while reporting success; fast typing in LibreOffice came out reordered | Exact in every app and language |
| `run "(cd site && server &)"` hung for two and a half minutes; `find -L` in a symlink loop ran the desktop out of memory | Returns at once; huge output keeps its start and end |
| `select` changed a web dropdown without the page noticing; an autocomplete field took typing, waiting and a click | Both are one `select` that the page reacts to |
| `read` showed a spreadsheet's values but not its bold header, frozen row, conditional format or chart; a docx's text but not its table of contents, tracked changes or comments | All of those are in `read` |
| Windows programs: `path` didn't recognise Wine's Save dialog; Alt+F4 didn't close a window; OCR misread "71" as "7i" | `path` fills Wine's dialogs (Windows paths too); Alt+F4 and `close` work; digits read as digits |

Each batch's tasks and checks are in [scripts/scenarios/scenarios.md](../scripts/scenarios/scenarios.md). The agents'
notes are in the per-batch results (one JSON object per task), and the call logs are what the numbers above
count: calls (every `minion` command an agent ran, including retries), screenshots, calls that failed, and the
tokens of everything Minion printed (tiktoken's o200k_base). Screenshot images aren't in the token count: each
would add about 1,365 tokens for Claude.
