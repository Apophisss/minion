# Brief: simulate an AI agent doing everyday computer work with Minion

You are playing the role of a capable AI agent that a user asked to do computer tasks. Your computer is a
Minion desktop (an isolated Linux desktop with GUI apps) that you control with the `minion` command line.
The goal of this exercise is to find out where Minion makes such work slow, unreliable or token-hungry,
so it can be improved. So do each task the way a smart agent would, as efficiently as you can, and write
down every bit of friction you hit, honestly and concretely.

## Rules
1. Learn Minion the way a real agent would: run `minion skill` once and read it (that's the
   Agent Skill an agent gets), plus `--help` of any command. Do NOT read Minion's source code or anything
   in the repository: you are a user, not a developer.
2. Every Minion command goes through the logging wrapper, never `minion` directly:
   `python scripts/scenarios/log.py <SCENARIO_ID> -d <DESKTOP> <minion arguments...>`
   e.g. `python scripts/scenarios/log.py W01 -d sim-web1 see` or `python scripts/scenarios/log.py W01 -d sim-web1 act "click @3" "type hi\n"`.
   Always pass `-d <DESKTOP>` (other agents share this machine; never run `minion use`).
3. Do the work inside the desktop through Minion. Don't solve tasks with tools on the host (no curl/python on
   the host to fetch pages or parse files). `minion run` (a shell inside the desktop) is fine whenever a real agent
   would sensibly use it, unless the task names a GUI app ("using the Text Editor", "in GIMP"): then use that app.
4. Screenshots are allowed when you really need to look (`python scripts/scenarios/log.py ID -d DESK shot -o /tmp/ID-1.png`, then Read
   the file), but each one counts as a cost: say why you needed it.
5. Budget per scenario: about 25 Minion calls or 10 minutes. If you can't finish, stop, mark it failed and explain.
6. After each scenario, run its check (if it has one) with the id `check-<ID>`, e.g.
   `python scripts/scenarios/log.py check-W01 -d sim-web1 run "grep '\"task\": \"signup\"' /tmp/gym-results.jsonl | tail -1"`.
   Checks are not part of the task cost.
7. Keep memory low: close windows and apps you no longer need between scenarios. Never remove or restart the
   desktop until you're done with all scenarios; then remove it: `python scripts/scenarios/log.py teardown -d DESK rm DESK`.
8. Commands can take a while (an app install can take 1-2 minutes): give the Bash tool a long enough timeout
   (e.g. 300000 ms for installs).

## What to record
Append one JSON line per scenario to `scripts/scenarios/runs/results/<BATCH>.jsonl`:
```
{"id": "W01", "success": "yes" | "partial" | "no", "answer": "what you'd tell the user",
 "calls": <Minion calls for the task, excluding checks>, "screenshots": <count>,
 "friction": ["concrete problem: what you did, what happened, what it cost (extra calls, waits, guessing, tokens)", ...],
 "wish": ["what Minion could do so this is one step / reliable / cheaper", ...],
 "notes": "anything else"}
```
Good friction notes are specific: "`click \"Save\"` matched 2 elements and clicked the wrong one", "`see` didn't list
the popup's buttons so I needed a screenshot", "had to poll `see` 4 times waiting for the page", "output of `see` was
3,000 tokens of irrelevant menu items", "no way to know where the download went", "the dialog stole focus and my
typing went elsewhere", "I had to guess coordinates". Also note when something worked surprisingly well.

## When you're done
Reply with a short summary (under 250 words): one line per scenario (id, success, calls) and the 5 biggest
friction themes you saw. The details belong in the JSONL file.
