# Claude computer use on Minion

Claude's computer-use tool needs an environment: a screen to capture and a mouse and keyboard to drive.
Minion is that environment, with no Dockerfile or VNC to wire up. It supports:

- **`computer_toolset_20260801`**, the current toolset (GA on the Claude API and Google Cloud, no beta header).
  All 17 members are supported: `screenshot`, `zoom`, `left_click`, `right_click`, `middle_click`, `double_click`,
  `triple_click`, `left_click_drag`, `mouse_move`, `left_mouse_down`, `left_mouse_up`, `cursor_position`,
  `scroll`, `type`, `key` (with `repeat`), `hold_key` and `wait`.
- **`computer_20251124`** and **`computer_20250124`**, the earlier beta tools (`input.action`), for models and
  platforms that still use them.

Screenshots are resized to the model's image limits (2576 px / ~3.75 MP for toolset models, 1568 px /
1.15 MP for the earlier tools). Claude's coordinates are mapped back to the desktop for you. Batches
run in order and stop at the first failure, as the API requires.

## With the Anthropic SDK (tool runner)

```bash
pip install "minion-desktop[anthropic]"
```

```python
import anthropic
from minion import Desktop
from minion.integrations.anthropic import MinionComputer, allow_all

desk = Desktop.create("office")
with MinionComputer(desk, confirm=allow_all) as computer:
    runner = anthropic.Anthropic().beta.messages.tool_runner(
        model="claude-opus-5-5",
        max_tokens=4096,
        tools=[computer],
        messages=[{"role": "user", "content": "Open Calc, enter the numbers 1 to 10 in column A and sum them."}],
    )
    for message in runner:
        print(message)
```

`MinionComputer` is a `BetaAbstractComputerToolset20260801` driver. The SDK requires a `confirm` callable when a
driver implements `type`/`key`/`hold_key`. `allow_all` approves everything, which suits a disposable desktop
holding no credentials. For anything that matters, pass your own function and ask a person before
consequential actions. Other options: `remove_on_close=True` removes the desktop with the toolset,
and `max_long_edge` / `max_pixels` downscale screenshots further to save tokens.

Every action result includes one line about what changed (for example `OK — screen changed 12% · opened "Save As"`),
which helps the model notice when a click did nothing.

## Your own loop (any HTTP client or SDK)

```python
from minion import Desktop
from minion.integrations.anthropic import ComputerUse

desk = Desktop.create("browser")
cu = ComputerUse(desk)  # version="computer_20251124" for the earlier tool
tools = [cu.tool()]  # {"type": "computer_toolset_20260801"}
headers = {"anthropic-beta": cu.beta_header} if cu.beta_header else {}

# after each response:
tool_results = cu.run(response.content)  # one tool_result per computer call, toolset_name echoed
messages.append({"role": "assistant", "content": response.content})
messages.append({"role": "user", "content": tool_results})
```

`cu.run()` accepts SDK objects or plain dicts, skips non-computer blocks, and answers the calls
after a failure with `Not executed: an earlier computer action in this turn failed.`

## Tips

- 1280×800 (the default) is a good fit for web apps. Use `size="1024x768"` for cheaper screenshots, or 1920×1080 if
  the model supports it.
- Give the model Minion's other powers alongside the toolset. For example, expose `desk.run` as a custom tool for
  shell work, and `desk.see()` text as a cheaper, exact way to read the screen.
- `desk.recording("html", "run.html")` shows every step Claude took, with thumbnails.
