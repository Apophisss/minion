
## Your interface: Minion

The desktop is a Minion desktop, and Minion is how you see and control it. First read Minion's guide for agents:
{SKILL}

Wherever the guide says `minion COMMAND ...`, run `{A} COMMAND ...`: it runs that command on your desktop. For example:

```
{A} see
{A} act "click @12" "type hello\n"
{A} run "ls ~"
{A} screenshot -o /tmp/{A}.png        then look at the PNG with the Read tool
```

Everything Minion offers an agent is allowed, including running commands and Python inside the desktop. Do the work
in the desktop, though: don't copy files out of it to work on them elsewhere. Creating or removing desktops isn't
allowed either: `{A} start` sets up your desktop for each task.
