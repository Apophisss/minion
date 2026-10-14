"""The same, with your own agent loop: Minion turns Claude's tool_use blocks into tool_result blocks.

Use this pattern with any HTTP client or SDK. Nothing here depends on SDK toolset helpers.
"""

import anthropic

from minion import Desktop
from minion.integrations.anthropic import ComputerUse

client = anthropic.Anthropic()
desk = Desktop.create("browser")
cu = ComputerUse(desk)  # computer_toolset_20260801; use version="computer_20251124" for earlier models

messages = [{"role": "user", "content": "Find the current population of Iceland on Wikipedia."}]
for _ in range(40):
    response = client.beta.messages.create(
        model="claude-opus-5-5",
        max_tokens=16000,
        tools=[cu.tool()],
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=messages,
    )
    if response.stop_reason == "refusal":
        print("The model declined.")
        break
    messages.append({"role": "assistant", "content": response.content})  # keep every block as is
    if response.stop_reason != "tool_use":
        print("".join(b.text for b in response.content if b.type == "text"))
        break
    messages.append({"role": "user", "content": cu.run(response.content)})

desk.remove()
