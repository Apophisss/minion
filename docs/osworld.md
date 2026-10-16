# OSWorld's office tasks: screenshots or Minion

[OSWorld](https://github.com/xlang-ai/OSWorld) is the benchmark computer-use agents are compared on. We ran 30
of its LibreOffice tasks (10 Calc, 10 Writer, 10 Impress) with the same agent through three interfaces, and scored
them with OSWorld's own checkers:

- **Screenshots only**: the computer-use loop. Every action is a click, a key or typing at pixel coordinates, and
  returns a screenshot.
- **Minion 1.0.0**: the screen as text with `@ids`, batched actions, a shell and Python in the desktop.
- **Minion 1.1.0**: the same, with what the 1.0.0 run showed agents running into fixed.

| | Screenshots only | Minion 1.0.0 | Minion 1.1.0 |
|---|---:|---:|---:|
| Success | 93.2% | 89.9% | 96.6% |
| Steps per task | 13.2 | 12.4 | 10.2 |
| Screenshots per task | 12.8 | 1.8 | 0.9 |
| Tokens the computer returned, per task | 17,974 | 9,463 | 9,372 |
| Seconds per task | 195 | 196 | 165 |

What this shows, and what it doesn't:

- **Half the tokens for the same work.** What the computer sends back to the model is about half the size with
  Minion: text instead of a screenshot per action. Success is the same within noise: with 30 tasks, the 95%
  intervals are 79–98% (screenshots), 74–96% (1.0.0) and 83–99% (1.1.0).
- **1.1.0 takes 18% fewer steps and 16% less time than 1.0.0**, and half as many screenshots. It solved two tasks
  1.0.0 didn't and lost none, which is not significant on 30 tasks (sign test p = 0.5), and both were partly the
  agent's own reading (below).
- **The 1.1.0 numbers are optimistic.** Its fixes came from watching agents on these same 30 tasks, and it was
  measured on them again. A fresh sample of tasks would show how much of the gain carries over.
- **One task can't be passed here** (e4ef0baf, below), and it counts as a failure in every condition. Without it,
  success is 96.5% with screenshots, 93.0% with 1.0.0 and 99.9% with 1.1.0 (29 tasks).

## By app

| | Tasks | Screenshots only | Minion 1.0.0 | Minion 1.1.0 |
|---|---:|---|---|---|
| Calc | 10 | 100% · 11.9 steps · 16,573 tokens | 90% · 10.6 steps · 8,021 tokens | 100% · 6.9 steps · 5,907 tokens |
| Writer | 10 | 100% · 11.0 steps · 15,018 tokens | 100% · 10.8 steps · 7,029 tokens | 100% · 8.2 steps · 7,371 tokens |
| Impress | 10 | 79.7% · 16.7 steps · 22,333 tokens | 79.7% · 15.9 steps · 13,338 tokens | 89.7% · 15.5 steps · 14,839 tokens |

Per task, with every condition's score, steps, screenshots, tokens and seconds: [osworld.json](osworld.json).

## The tasks whose result differs

- **Hide the N/A cells (Calc, 6054afcb).** 1.0.0's agent read "hide" as white text through conditional
  formatting, and lost steps to `select` on the rule's dropdown typing "Formula is" and picking "All Cells". The
  1.1.0 and screenshot agents hid the rows.
- **Auto-save every 3 minutes (Impress, 2cd43775).** Every agent set it in Tools > Options. OSWorld's checker
  reads an older copy of the setting that LibreOffice 25.2's dialog no longer writes; the 1.1.0 agent noticed (a
  `grep` of LibreOffice's settings file) and set that one too, in Expert Configuration.
- **A picture's height, and 40 pt text (Impress, e4ef0baf).** No agent can pass it in this environment. Every
  condition made the changes asked (slide 3's picture is 20 cm high and slide 6's text 40 pt, as in the expected
  file), and every one fails on slide 2, which the task leaves alone: saving in LibreOffice 25.2 puts a title's two
  runs of text into one (and moves a text box's edge by 0.01 mm), and OSWorld's checker compares every slide.
  The check that screens tasks for this ([fidelity.py](../scripts/osworld/fidelity.py)) passed it before the runs:
  its ctrl+s, sent right after the 9.5 MB deck opened, didn't save it, and the task has two expected files, the
  second copied over the first. It now checks that the file was written again and tries each expected file on its
  own. With that, of the 22 tasks that have an expected file to try, it fails this one alone.
- **Export a slide as PNG (Impress, 455d3c66).** 0.97 in every condition: the image this LibreOffice exports
  differs slightly from OSWorld's expected one.

## What 1.0.0 got in the way of, and 1.1.0 fixes

After each batch the agent said what made the tasks harder than they should have been. The main things, now
fixed ([CHANGELOG](../CHANGELOG.md#110) has them all):

| Agents ran into | 1.1.0 |
|---|---|
| `select` on a LibreOffice dialog's dropdown typed the option's name: "Double" picked "Leading" | picks the option from the list the dropdown opens, and lists the real options if it's not there |
| Calc cells out of view couldn't be clicked or filled; formulas came back cut off | `click C2:C29`, `fill B8 "=SUM(B2:B7)"`, `fill C2:C29 "=PROPER(B2)"`; `see` shows the Name Box and the whole formula |
| `type ", "` typed one character | `type` keeps spaces at its ends |
| The step right after a dialog's OK failed "no longer on screen" | an @id hidden by a dialog is found again |
| LibreOffice's add-sheet button ignored clicks | a click is a short press, as a person's |
| "20 cm" typed into a dialog that measures in inches was stored as 19.99 cm | the office profile measures in centimeters |
| `read` of a deck gave titles only; formatting tasks needed unzipping the file | `read --details`: backgrounds, each shape's place and size, fonts, spacing |
| Status changes (a shape selected, text being edited) needed a screenshot | replies add what the status bar says |

## How it was run

- **Tasks.** 10 per app drawn from OSWorld's `test_all.json` (commit `b138d34`) with a fixed seed, leaving out
  tasks whose checker reads OSWorld's own accessibility tree. 8 of the 30 drawn couldn't be passed in this
  environment: OSWorld's expected file fails its own checker after a save in LibreOffice 25.2 (1 task), or
  LibreOffice 25.2 writes white slide backgrounds as "none", which the checker counts as different on every slide
  (7). They were replaced by tasks of the same app that pass both checks. A ninth, e4ef0baf, turned out to be
  blocked too, after the runs (above). [tasks.json](../scripts/osworld/tasks.json) lists all of it.
- **Environment.** A fresh Minion `office` desktop per task (Debian's LibreOffice 25.2, 1280×800), set up with
  OSWorld's own steps (files downloaded, documents opened, OSWorld's `pyautogui` snippets run) and scored by
  OSWorld's checkers after its post-steps (activate the window, ctrl+s).
- **Agent.** Each batch of 2 or 3 tasks was one fresh Claude Code agent session given only its brief, with the
  same model in every condition and 50 steps per task. It never saw a score. In the screenshot condition it could
  only take screenshots, click, type and press keys. With Minion it could use everything Minion offers, shell and
  Python in the desktop included.
- **Minion 1.1.0, as measured.** The run used this release's code on the day it ran. A few changes came after it,
  from what it showed, so they aren't in its numbers: `read`'s dates, charts and table sizes, `see` keeping a
  cell's spaces and showing `=NA()` as `#N/A`, and python-pptx in the office image.
- **Counting.** Steps are the commands it ran on its desktop. Tokens are what the computer returned: text counted
  with tiktoken's `o200k_base`, a 1280×800 screenshot as 1,365 tokens (Claude's estimate). Seconds run from a
  task's start to its end, the model's thinking included.

The harness is in [scripts/osworld](../scripts/osworld): it runs any agent that can run shell commands and read
PNG files, and `report.py` makes the tables above.

## Not comparable to OSWorld's leaderboard

The leaderboard compares models on all of OSWorld's 369 tasks, in OSWorld's Ubuntu VM, with its own harness and
step limits. This is 30 office tasks, in Minion's desktops, comparing interfaces for one agent. A coding agent
that can also run shell commands is a different setting from a model that only sees screenshots, and the
screenshot interface here is ours, not a vendor's computer-use tool. One run per task, one model: differences of
a task or two are noise.
