"""Claude drives a Minion desktop through the computer-use toolset (Anthropic SDK tool runner).

pip install "minion-desktop[anthropic]"
export ANTHROPIC_API_KEY=...
python examples/claude_computer_use.py "Open Calc, put 1..10 in column A and their sum in A11."
"""

import sys

import anthropic

from minion import Desktop
from minion.integrations.anthropic import MinionComputer, allow_all

task = " ".join(sys.argv[1:]) or "Open Writer and write a haiku about desktops, then save it as haiku.docx."

client = anthropic.Anthropic()
desk = Desktop.create("office")
print(f"Watch it live: minion view -d {desk.name}")

# allow_all: the desktop is a disposable sandbox with no credentials. Gate actions yourself otherwise.
with MinionComputer(desk, confirm=allow_all) as computer:
    runner = client.beta.messages.tool_runner(
        model="claude-opus-5-5",
        max_tokens=16000,
        tools=[computer],
        # Server-side fallback: if the model declines, the API retries on a fallback model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": task}],
    )
    for message in runner:
        if message.stop_reason == "refusal":
            print("The model declined this task.")
            break
        for block in message.content:
            if block.type == "text":
                print(block.text)

desk.recording("html", "claude-session.html")
print(f"Timeline: claude-session.html · desktop {desk.name} is still running (minion rm {desk.name})")
