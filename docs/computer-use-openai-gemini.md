# OpenAI and Gemini computer use on Minion

OpenAI's and Google's computer-use models need the same thing Claude does: a screen to capture, plus a mouse and
keyboard to drive. Two adapters connect them to a Minion desktop. Like the [Claude adapter](computer-use.md), they
take plain dicts or SDK objects and return plain dicts. They import no SDK, so Minion stays dependency-free.

| Module | Speaks | You call |
|---|---|---|
| `minion.integrations.openai` | Responses API `computer` tool (GA, batched `actions`) and the earlier `computer_use_preview` tool (one `action`) | `cu.params()` / `cu.tool()`, then `cu.run(response.output)` |
| `minion.integrations.gemini` | Gemini computer use through the Interactions API (default) or `models.generate_content`, both function sets | `cu.tool()`, then `cu.run(interaction)` / `cu.run(response)` |

## OpenAI

```bash
pip install openai
```

```python
from openai import OpenAI
from minion import Desktop
from minion.integrations.openai import ComputerUse

client = OpenAI()
desk = Desktop.create("browser")
cu = ComputerUse(desk)  # cu.tool() == {"type": "computer"}

response = client.responses.create(
    model="gpt-6.1-sol",
    input="Open news.ycombinator.com and tell me the top story.",
    **cu.params(),
)
for _ in range(50):  # bound the run
    items = cu.run(response.output)  # one computer_call_output per computer_call
    if not items:
        break  # no more computer calls: the model has answered
    response = client.responses.create(
        model="gpt-6.1-sol", previous_response_id=response.id, input=items, **cu.params()
    )
print(response.output_text)
```

The actions of each `computer_call` run in order as a single Minion `act` batch, which stops at the first failure.
Then a screenshot is sent back as a `computer_screenshot` data URL with `detail: "original"`. Here is how each
action maps to the desktop:

| OpenAI action | On the desktop |
|---|---|
| `click` (`left`, `right`, `wheel`) / `double_click` | a click (`wheel` is the middle button). Held `keys` such as `["SHIFT"]` become modifiers |
| `click` with `back` / `forward` | moves the pointer there and presses alt+Left / alt+Right (Minion's `act` clicks buttons 1 to 3 only) |
| `drag` | a two-point path is a smooth drag. Longer paths press, move through each point, then release |
| `move`, `type`, `wait` | the same. `wait` has no duration in the API, so it sleeps `wait=2.0` seconds, as in OpenAI's examples |
| `scroll` | `scroll_x`/`scroll_y` pixels become wheel clicks at `x, y`, 100 px per click (`scroll_unit=`) |
| `keypress` | `["CTRL", "C"]` becomes `ctrl+c`, `["ENTER"]` becomes `Return`, `["ARROWLEFT"]` becomes `Left`, and so on |
| `screenshot` | nothing to do, because every call is answered with a screenshot |

If an action fails (for example a coordinate off the screen), the rest of that call and any later calls don't run.
A `computer_call_output` can only carry a screenshot, so `run()` also appends a short user message that says what
failed, and keeps the same text in `cu.errors`. Pass `report_errors=False` to leave that message out.

**Safety checks.** A `computer_call` can carry `pending_safety_checks`. `run()` never acknowledges them on its own.
Instead it raises `SafetyCheckRequired` before anything runs. Ask a person, then run again with the checks they
approved. The checks go back as `acknowledged_safety_checks`:

```python
from minion.integrations.openai import SafetyCheckRequired

try:
    items = cu.run(response.output)
except SafetyCheckRequired as err:
    print(err.checks)  # [{"id": ..., "code": ..., "message": ...}]
    if input("Proceed? [y/N] ").strip().lower() != "y":
        raise
    items = cu.run(response.output, acknowledge=err.checks)
```

You can also pass `ComputerUse(desk, confirm=ask_user)`, where `ask_user(checks)` returns `True` to approve.
`cu.pending_safety_checks(response.output)` lists the checks without running anything.

**The preview tool.** Use `ComputerUse(desk, version=PREVIEW)` with `model="computer-use-preview"`. The tool then
includes `display_width`, `display_height` and `environment` (`"linux"` by default). `params()` also adds the
`truncation="auto"` that the preview tool requires.

**Screenshot size.** Coordinates are screenshot pixels. Minion's sizes, up to 3840×2160, fit within the documented
`detail: "original"` limits, so screenshots aren't scaled by default. To spend fewer tokens, pass
`max_long_edge=` or `max_pixels=`, and clicks are mapped back to the desktop. OpenAI reports good results at 1440×900
and 1600×900, so `Desktop.create("browser", size="1440x900")` is a good choice.

## Gemini

```bash
pip install google-genai
```

With the Interactions API:

```python
from google import genai
from minion import Desktop
from minion.integrations.gemini import ComputerUse

client = genai.Client()
desk = Desktop.create("office")
cu = ComputerUse(desk)  # environment="desktop"; use "browser" for web-only tasks

interaction = client.interactions.create(
    model="gemini-3.8-flash",
    input=[{"type": "text", "text": "Write a haiku about otters in Writer."}, cu.screenshot_input()],
    tools=[cu.tool()],  # {"type": "computer_use", "environment": "desktop"}
)
for _ in range(50):
    results = cu.run(interaction)  # one function_result (with a screenshot) per computer call
    if not results:
        break
    interaction = client.interactions.create(
        model="gemini-3.8-flash", previous_interaction_id=interaction.id, input=results, tools=[cu.tool()]
    )
print(interaction.output_text)
```

With `models.generate_content`, `run()` returns `function_response` parts for the next user turn:

```python
from google.genai import types

cu = ComputerUse(desk, api="generate_content")
config = types.GenerateContentConfig(tools=[cu.tool()])  # {"computer_use": {"environment": "ENVIRONMENT_DESKTOP"}}
contents = [{"role": "user", "parts": [{"text": "Write a haiku about otters in Writer."}, cu.screenshot_input()]}]
for _ in range(50):
    response = client.models.generate_content(model="gemini-3.8-flash", contents=contents, config=config)
    contents.append(response.candidates[0].content)
    parts = cu.run(response)
    if not parts:
        break
    contents.append({"role": "user", "parts": parts})
print(response.text)
```

Every result carries a fresh screenshot, so `contents` grows quickly. Google's reference implementation keeps
screenshots only in the last three turns.

**Coordinates** arrive on a normalized 0-999 grid and are mapped to desktop pixels as `int(x / 1000 * width)`.
Screenshots can therefore be downscaled freely with `max_long_edge=` or `max_pixels=`.

**Functions.** Gemini 3.5 and later (`gemini-3.8-flash`, `gemini-3.5-flash-lite`) use `click`, `double_click`,
`triple_click`, `middle_click`, `right_click`, `mouse_down`, `mouse_up`, `move`, `type` (with `press_enter`),
`drag_and_drop`, `wait`, `press_key`, `key_down`, `key_up`, `hotkey`, `take_screenshot` and `scroll`. In the browser
environment they add `navigate`, `go_back` and `go_forward`. `gemini-3-flash-preview` uses the earlier set, which is
also supported: `click_at`, `hover_at`, `type_text_at` (clears the field first by default), `scroll_document`,
`scroll_at`, `key_combination`, `wait_5_seconds`, `search`, `open_web_browser`, `navigate`, `go_back`, `go_forward`
and `drag_and_drop`. A few details:

- `scroll`'s `magnitude_in_pixels` (default 300) is read on the 0-999 grid along the scroll axis, the same way
  the reference implementation reads `magnitude`. It becomes wheel clicks of `scroll_unit=100` px.
- `key_down`/`key_up` on a modifier hold it virtually: it is added to later clicks, drags, scrolls and key presses
  until `key_up`. Other keys are pressed once. Nothing stays physically held, so a key can't get stuck.
- Browser functions use the desktop's browser. `navigate` focuses it, presses ctrl+l, and types the URL and Enter.
  If no browser window is open, it calls `desk.open(url)` instead. `go_back` and `go_forward` press alt+Left and
  alt+Right. `search` and `open_web_browser` go to `search_url=` (default Google).
- In the browser environment each result also reports `"url"`, read from the address bar with `desk.see()`. Pass
  `url=False` to skip that, or pass your own function.
- Mobile-only functions (`open_app`, `list_apps`, `long_press`) are answered with an error.
- Calls to your own functions are left out of `run()`'s results, so answer them yourself in the same turn. To replace
  a predefined function, pass `exclude=["navigate"]`. The tool then lists it in `excluded_predefined_functions` and
  `run()` skips calls to it.

If a call fails, its result has `"error"` in its JSON (and `is_error: true` with the Interactions API), and any
later calls aren't run. `cu.tool(enable_prompt_injection_detection=True, disabled_safety_policies=["data_modification"])`
passes those options through to the tool.

**Safety decisions.** If a call's arguments contain `safety_decision` with `"decision": "require_confirmation"`,
`run()` raises `SafetyCheckRequired` before running anything. The error's `checks` lists the call ID, the function
and the explanation. After a person approves, run it again: `cu.run(interaction, acknowledge=err.checks)`. You can
also use `confirm=`. The results then carry `"safety_acknowledgement": true`. A call with any other decision (such as
blocked) doesn't run and is answered with an error.

## Sources

The formats above were checked on 2026-10-14 against these pages, and against openai 3.31.0 and google-genai 2.30.1:

- OpenAI computer use guide: <https://developers.openai.com/api/docs/guides/tools-computer-use> (formerly
  `platform.openai.com/docs/guides/tools-computer-use`, which now redirects here)
- OpenAI integration recipes (action handlers, key map, screenshots, migration from `computer-use-preview`):
  <https://developers.openai.com/api/docs/guides/tools-computer-use-integration>
- Responses API reference (`computer_call`, `computer_call_output`, `pending_safety_checks`, tool schemas):
  <https://developers.openai.com/api/reference/resources/responses/methods/create>
- OpenAI image sizing (`detail: "original"`): <https://developers.openai.com/api/docs/guides/images-vision>
- Gemini computer use (Interactions API): <https://ai.google.dev/gemini-api/docs/computer-use>
- Gemini computer use (`generate_content`): <https://ai.google.dev/gemini-api/docs/generate-content/computer-use>
- Gemini function calling (`function_result`): <https://ai.google.dev/gemini-api/docs/function-calling>
- Interactions API `steps` schema: <https://ai.google.dev/gemini-api/docs/interactions-breaking-changes-may-2026>
- Gemini 2.5 computer use model (shut down on July 28, 2026):
  <https://ai.google.dev/gemini-api/docs/models/gemini-2.5-computer-use-preview-10-2025>
- Google's reference implementation (function sets, argument names, key names): <https://github.com/google/computer-use-preview>
