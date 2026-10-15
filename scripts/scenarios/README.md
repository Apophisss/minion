# Everyday-work scenarios

93 ordinary computer tasks, from trivial ("what's the date on this computer?") to multi-app jobs ("total the
attachment of Dana's email and reply with it"), for finding out where an agent using Minion wastes calls, tokens
or time, or fails, and for measuring the fixes.

- [scenarios.md](scenarios.md): the tasks, in 8 batches (web pages, office documents, everyday chores,
  multi-app workflows, development, media, Windows programs), each with a check.
- [site/](site): a local website with the web patterns agents trip on: a long signup form, a checkout wizard,
  a paginated table, an endless feed, pop-ups over the page, alert/confirm/prompt dialogs, a payment form in an
  iframe, drag and drop, hover menus, autocomplete, a custom date picker, slow reports, toasts, a sign-in pop-up
  window, shadow DOM, a canvas chart, a webmail, a shop, a rich text editor, a Hebrew form and more. Each page
  logs what the user did to `/tmp/gym-results.jsonl`, which the checks read.
- [files/](files): the documents, pictures, video and code the tasks use.
- [setup.py](setup.py) prepares a desktop for a batch; [log.py](log.py) runs and logs one `minion` command;
  [metrics.py](metrics.py) adds up calls, screenshots, failed calls, output tokens and seconds.
- [brief.md](brief.md): the instructions for the agent doing the tasks.

## How it was run

Each batch was given to a separate AI agent (a fresh session that learns Minion from `minion skill`, as any agent
would) with [brief.md](brief.md): do the tasks as efficiently as you can through `log.py`, and write down every
bit of friction, concretely. The agents' notes, not just the numbers, said what to fix: a dialog `see` couldn't
list, a reply that left out the result, a "✓" over a click that a pop-up swallowed.

```bash
python scripts/scenarios/setup.py web --name web1        # a browser desktop with the site
python scripts/scenarios/log.py W01 -d web1 see           # what the agent runs, logged
python scripts/scenarios/metrics.py                       # the table
```

The results are in [docs/scenarios.md](../../docs/scenarios.md).
