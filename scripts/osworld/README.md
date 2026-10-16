# OSWorld's office tasks on Minion desktops

[OSWorld](https://github.com/xlang-ai/OSWorld) is the benchmark computer-use agents are compared on. This harness
runs its tasks on Minion desktops and scores them with OSWorld's own checkers, so the same agent can be measured
with two interfaces: **S**, screenshots and coordinates only (the computer-use loop: every action returns a
screenshot), and Minion (the screen as text with @ids, batched actions, a shell and Python in the desktop), under
any other letter: the published results have **M** for Minion 1.0.0 and **N** for 1.1.0, each run with
`MINION_BIN` pointing at that version. The results are in [docs/osworld.md](../../docs/osworld.md).

## How a task runs

`bench.py AGENT start` gives the agent the next task of its batch:

1. A fresh `office` desktop. `/home/user` (OSWorld's home) is a link to the desktop's home, so OSWorld's paths work.
2. The task's setup, as OSWorld does it: the files downloaded into the desktop, the document opened, apps launched,
   windows activated. OSWorld's `pyautogui` snippets run unchanged against [pyautogui.py](pyautogui.py), the few
   calls they use done with xdotool.
3. The task's instruction, and nothing else.

`bench.py AGENT do ...` is one step, through the agent's interface (50 per task). `bench.py AGENT end` runs the task's
post-steps (activate the window, ctrl+s), then OSWorld's checker (`desktop_env.evaluators`: its getters and metrics,
with [stubs.py](stubs.py) standing in for modules the office tasks never call) and records the score in
`results/AGENT.jsonl`. The agent never sees the score. `end --fail` says the task can't be done, which is right for
OSWorld's infeasible tasks and wrong for the others.

Every step is logged in `logs/AGENT/TASK.jsonl`: the command, its output, the seconds it took. The results count
steps, screenshots, the tokens of what the computer returned (tiktoken's o200k_base; a 1280×800 screenshot counts
as 1,365, Claude's estimate) and the time from start to end.

## Is a task fair here?

A Minion desktop runs Debian's LibreOffice 25.2. OSWorld's expected files were saved by an older LibreOffice on
Ubuntu, and some of its checkers compare files closely. Two checks find the tasks this environment blocks:

- [fidelity.py](fidelity.py) puts OSWorld's expected file where the agent's result goes, opens it, saves it (and
  checks that the file was written again: right after a big document opens, LibreOffice can drop the keys), runs
  the task's post-steps and scores it. If the expected file itself fails, so would any result.
- [feasible.py](feasible.py) also checks, for Impress, that saving the task's own file keeps the slide backgrounds
  the expected file has: LibreOffice 25.2 writes a white master background as "none", which OSWorld's
  `compare_pptx_files` counts as different on every slide.

[tasks.json](tasks.json) lists the 30 tasks the results use (10 Calc, 10 Writer, 10 Impress), how they were drawn,
and the tasks they replace.

## Running it

```bash
sh scripts/osworld/setup.sh                    # OSWorld at the commit used, the checkers' packages, the image
PY=~/osworld-run/venv/bin/python
$PY scripts/osworld/fidelity.py               # which tasks a perfect result can pass here (fidelity.jsonl)
$PY scripts/osworld/bench.py plan s1 S 1273e544-688f-496b-8d89-3e0f40aa0606 66399b0d-8fda-4618-95c4-bfc6191617e9
$PY scripts/osworld/bench.py bin s1            # the agent's command: ~/osworld-run/bin/s1 start, s1 shot, ...
$PY scripts/osworld/bench.py brief s1          # its instructions: give them to the agent as its task
$PY scripts/osworld/report.py --feasible       # the table
```

The agent can be any agent that runs shell commands and reads PNG files: the briefs ([briefs/](briefs)) say what
it may do. In the published results each batch of two or three tasks was one fresh Claude session (Claude Code's
general-purpose agent), the same model in every condition, with nothing but its brief.
