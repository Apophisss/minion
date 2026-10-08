# Claude computer use (`computer_toolset_20260801`) and browser use: executor reference, verified 2026-10-08

## 0. Sources and how each was checked

- **Main page:** https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool (I downloaded the `.md` version; its header says status GA).
- **The "overview" URL in the task does not exist.** https://platform.claude.com/docs/en/agents-and-tools/computer-use/overview returns HTTP 404 through WebFetch; curl gets only an empty page shell. There are no separate sub-pages. The member reference, batch actions, scaling, tool parameters, compatibility and migration are all sections of the computer-use-tool page. https://platform.claude.com/llms.txt lists only "Computer use tool" and "Browser use tool".
- **Related docs pages:**
  - https://platform.claude.com/docs/en/agents-and-tools/tool-use/browser-use-tool
  - https://platform.claude.com/docs/en/agents-and-tools/tool-use/browser-use-sdk
  - https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-reference#client-toolsets
  - https://platform.claude.com/docs/en/build-with-claude/vision
  - https://platform.claude.com/docs/en/build-with-claude/vision-coordinates
- **SDK:** the `anthropic==1.12.1` wheel from PyPI (uploaded 2026-10-08T03:41). I unpacked it and read its type files (not executed). Also the SDK guide https://github.com/anthropics/anthropic-sdk-python/blob/main/computer-toolset.md.
- **Reference implementation:** github.com/anthropics/anthropic-quickstarts, commit `9ec32b9` (2026-10-07).
  - `computer-use-demo/computer_use_demo/tools/computer.py`, `tools/collection.py`, `tools/groups.py`, `loop.py`, `Dockerfile`, `image/*.sh`
  - `computer-toolset/python/vnc_computer.py`, `run.py`
  - The docs link to `github.com/anthropics/claude-quickstarts/tree/main/computer-toolset`. That URL returned 403 through our proxy; the same directory exists in anthropic-quickstarts. Whether one repo is a rename of the other is UNVERIFIED.
- **xdotool:** `xdo.c` and `xdo_util.h` from https://github.com/jordansissel/xdotool (master).
- **Older article:** https://claude.com/blog/best-practices-for-computer-and-browser-use-with-claude, dated May 13, 2026. It predates the toolset, so treat it as background only.
- **Local copies** are in `docs/research/drafts/ (not all copied) computer-use/`:
  - `agents-and-tools_tool-use_computer-use-tool.md`
  - `agents-and-tools_tool-use_browser-use-tool.md`
  - `agents-and-tools_tool-use_browser-use-sdk.md`
  - `agents-and-tools_tool-use_tool-reference.md`
  - `build-with-claude_vision*.md`
  - `sdk_computer_toolset.md`, `xdo.c`
  - `repos/aq/` (the quickstarts clone)
  - `wheel/x/anthropic/` (the unpacked SDK)

---

## 1. The `computer_toolset_20260801` entry

**Availability**
- **Status:** GA on the Claude API and Google Cloud. No beta header. Use the normal `client.messages.create`; the beta namespace is not required.
- **Supported models** (from the page header): `claude-fable-5-1`, `claude-mythos-5-1`, `claude-fable-5`, `claude-mythos-5`, `claude-opus-5-5`, `claude-opus-5`, `claude-sonnet-5-5`, `claude-sonnet-5`, `claude-opus-4-8`, `claude-haiku-5-5`.
- **Opus 5.5 and Sonnet 5.5 on the Claude API or Google Cloud accept only the toolset.** `computer_20251124` returns a 400 there. Amazon Bedrock still accepts `computer_20251124` for those two models.
- Other platforms (Bedrock, Claude Platform on AWS, Foundry) offer only the older beta versions.
- The toolset is not available in Claude Managed Agents.

**Entry shape.** It has no `name` and no display size:
```json
{ "type": "computer_toolset_20260801" }
```
```json
{ "type": "computer_toolset_20260801",
  "configs": { "zoom": { "enabled": false } },
  "cache_control": { "type": "ephemeral" } }
```

| Parameter | Required | Meaning |
|---|---|---|
| `type` | yes | `computer_toolset_20260801` |
| `configs` | no | Keyed by member name. Each value accepts only `enabled` (default `true` for all 17, `zoom` included) and `defer_loading` (default `false`). Members you leave out keep their defaults. |
| `cache_control` | no | Goes on the entry only, never inside `configs`. |
| `allowed_callers` | no | Only `["direct"]` is accepted. |

**What the API rejects** (`invalid_request_error`):
- Old fields on the entry: `name`, `display_width_px`, `display_height_px`, `display_number`, `enable_zoom`.
- `strict` or `input_examples`.
- `defer_loading` on the entry itself, or enabled members with different `defer_loading` values.
- A `configs` key that is not a member name, or any field other than `enabled`/`defer_loading` in a member's value.
- A `configs` that disables every member.
- A code-execution caller in `allowed_callers`.
- The `fine-grained-tool-streaming-2025-05-14` beta header.
- A `tool_choice` of type `tool` that names the toolset or a member. Separately, on Opus 5.5 `tool_choice` `any` returns a 400 as well, so use `auto`.
- A `computer_20251124` entry or any other tool named `computer` in the same request.
- Declaring the browser toolset alongside it is allowed.

**Other facts**
- **Cost:** the toolset adds about 4,500 input tokens per request. Disabling `zoom` saves about 410.
- **Streaming:** each member's `input` arrives as one complete `input_json_delta`, not in fragments.
- **One action per turn:** setting `tool_choice: {"type":"auto","disable_parallel_tool_use":true}` makes Claude send at most one member call per turn.
- **Two different modifier fields:** pointer members carry their held modifier keys in **`text`**. The older `computer_20250124` tool used `key`, and the browser toolset uses `modifiers`.

### The 17 members

Every call carries `"toolset_name":"computer"`, and `name` is the member name. `input` holds only that member's parameters; there is no `action` field.

Field types and which fields are required come from the SDK 1.12.1 classes (`anthropic/types/computer_*_input.py`). Value ranges come from the docs. The last column is the confirmation text the SDK's own helper returns (`lib/tools/_toolsets/_computer_registry.py`).

| Member | `input` fields | What it does | SDK confirmation text |
|---|---|---|---|
| `screenshot` | `{}` | Capture the full display. The result must be an **image**. | (image) |
| `zoom` | `region: [x0,y0,x1,y1]` (int, required; top-left and bottom-right corners, in **screenshot** pixels) | Capture that region at full display resolution, then scale it to fit within your normal screenshot size, keeping the aspect ratio. The result must be an **image**. | (image) |
| `left_click` | `coordinate?: [x,y]`; `text?: str`, the modifiers to hold: `shift`, `ctrl`, `alt`, `super`, or a `+` chord such as `ctrl+shift` | Click at `coordinate`, or at the current cursor position if it is omitted. | `Clicked.` |
| `right_click` | same as `left_click` | | `Right-clicked.` |
| `middle_click` | same as `left_click` | | `Middle-clicked.` |
| `double_click` | same as `left_click` | | `Double-clicked.` |
| `triple_click` | same as `left_click` | | `Triple-clicked.` |
| `left_click_drag` | `start_coordinate: [x,y]` (required); `coordinate: [x,y]` (required); `text?` modifiers | Press at the start point, drag to `coordinate`, release. | `Dragged.` |
| `mouse_move` | `coordinate: [x,y]` (required) | Move without clicking, for hovering. | `Moved the mouse.` |
| `left_mouse_down` | `{}` | Press the left button at the current cursor position. | `Left mouse button pressed.` |
| `left_mouse_up` | `{}` | Release the left button. | `Left mouse button released.` |
| `cursor_position` | `{}` | Report the cursor position as **text**, in screenshot pixels. The SDK formats it as `X={x},Y={y}`; the docs example is `X=512, Y=384`. | (text) |
| `scroll` | `scroll_direction: "up" \| "down" \| "left" \| "right"` (required); `scroll_amount: int` (required; wheel clicks); `coordinate?: [x,y]`; `text?` modifiers | Scroll at `coordinate`, or at the cursor. The SDK's description to the model says "Do NOT use PageUp/PageDown to scroll". | `Scrolled {scroll_direction}.` |
| `type` | `text: str` (required) | Type literal text at the current focus. | `Typed.` |
| `key` | `text: str` (required): one key or a `+` chord, e.g. `"Return"`, `"ctrl+s"`, `"alt+Tab"`; `repeat?: int` from 1 to 100, default 1 | Press the key or chord `repeat` times. **Your handler must honor `repeat`.** | `Pressed {text}.` |
| `hold_key` | `text: str` (required); `duration` (required; seconds, docs say up to 300; SDK type is `int`) | Hold the key or chord down for that long. | `Held {text} for {duration}s.` |
| `wait` | `duration` (required; seconds, up to 300; SDK type `int`) | Pause, e.g. while an app loads. | `Waited {duration}s.` |

**Text the SDK feeds the model** (from its 1.12.1 docstrings):
- **`key`:** "Key names are case-insensitive; common names like Return, Tab, Escape, Up, Down, Left, Right, Home, End, Page_Up, Page_Down, Delete, BackSpace are supported."
- **`mouse_move`:** "Use this ONLY to hover without clicking."

**Rules for the executor**
- **Every coordinate is in screenshot pixels.** That includes `coordinate`, `start_coordinate`, `region`, and the position `cursor_position` reports. The origin is the top left of the full screenshots you return. A `zoom` does not change this: after a zoom, Claude still uses the full-screenshot frame.
- **Dispatch on the pair (`toolset_name`, `name`).** A custom tool can share a member's name.
- **Answer withheld or unknown members with an error result.** If Claude calls a member you disabled or don't implement, return `is_error: true`. Never drop the block.
- **Check values and refuse bad ones; don't clamp.** The API does not check them. Raise an error for an out-of-range coordinate, a huge `duration`/`repeat`/`scroll_amount`, or a zoom region with `x1<=x0` or `y1<=y0`.
- **`duration` may need float handling.** The SDK types it as `int`; whether the model ever sends a float is UNVERIFIED, so accepting floats is a safe choice.

---

## 2. Request, `tool_use`, and `tool_result` shapes

### Request (raw HTTP; no `anthropic-beta` header needed)
```json
POST /v1/messages
{
  "model": "claude-opus-5-5",
  "max_tokens": 16000,
  "thinking": { "type": "adaptive" },
  "output_config": { "effort": "high" },
  "system": "You control a Linux desktop. End each group of actions with a screenshot so you can verify the result before continuing.",
  "tools": [
    { "type": "computer_toolset_20260801", "cache_control": { "type": "ephemeral" } },
    { "type": "bash_20250124", "name": "bash" }
  ],
  "messages": [ { "role": "user", "content": "Open Firefox and search for pictures of cats." } ]
}
```
On Opus 5.5:
- Thinking cannot be disabled.
- Effort defaults to `medium`.
- Text written between tool calls comes back as `thinking` blocks, which are empty unless you set `thinking.display: "updates"` (beta header `thinking-display-updates-2026-08-18`).

### Assistant turn with several calls (a "batch action"; `stop_reason: "tool_use"`)
```json
{
  "role": "assistant",
  "content": [
    { "type": "text", "text": "I'll search from the address bar." },
    { "type": "tool_use", "id": "toolu_A", "name": "left_click", "toolset_name": "computer", "input": { "coordinate": [640, 60] } },
    { "type": "tool_use", "id": "toolu_B", "name": "type",       "toolset_name": "computer", "input": { "text": "pictures of cats" } },
    { "type": "tool_use", "id": "toolu_C", "name": "key",        "toolset_name": "computer", "input": { "text": "Return" } },
    { "type": "tool_use", "id": "toolu_D", "name": "screenshot", "toolset_name": "computer", "input": {} }
  ],
  "stop_reason": "tool_use"
}
```

### Required results message (the next `user` turn)
```json
{
  "role": "user",
  "content": [
    { "type": "tool_result", "tool_use_id": "toolu_A", "toolset_name": "computer", "content": [ { "type": "text", "text": "OK" } ] },
    { "type": "tool_result", "tool_use_id": "toolu_B", "toolset_name": "computer", "content": "OK" },
    { "type": "tool_result", "tool_use_id": "toolu_C", "toolset_name": "computer", "content": "OK" },
    { "type": "tool_result", "tool_use_id": "toolu_D", "toolset_name": "computer",
      "content": [ { "type": "image", "source": { "type": "base64", "media_type": "image/png", "data": "iVBORw0KGgo..." } } ] }
  ]
}
```
Other result forms:
- **`cursor_position`:** `"content": "X=512,Y=384"`
- **`zoom`:** an image block, same shape as `screenshot`.
- **A failure, and the calls after it:**
```json
{ "type": "tool_result", "tool_use_id": "toolu_B", "toolset_name": "computer", "is_error": true,
  "content": "Error: Failed to capture screenshot. Display may be locked or unavailable." }
{ "type": "tool_result", "tool_use_id": "toolu_C", "toolset_name": "computer", "is_error": true,
  "content": "Not executed: an earlier computer action in this turn failed." }
```

### Rules the API enforces or the docs require
1. **Answer every `tool_use` block.** One `tool_result` each, matched by `tool_use_id`, all in the **single** next `user` message. A missing result gets `invalid_request_error`, so a loop that reads only the first block breaks.
2. **Echo `"toolset_name": "computer"` on every member result.** A result without it, or with a different value, is rejected. Put `toolset_name` only on member results, never on results for ordinary tools.
3. **Run the blocks one after another, in order, and stop at the first failure.**
   - The failed call gets `is_error: true` and a description.
   - Every later computer call in that turn gets `is_error: true` with exactly `Not executed: an earlier computer action in this turn failed.`
   - The browser toolset uses a different halt text (see section 4).
   - The SDK skips only later calls of the *same* toolset. Calls to bash or other tools in that turn still run.
4. **Member results may contain only `text` and `image` blocks.**
   - Only `screenshot` and `zoom` need an image.
   - `"OK"`, or any short line, is enough for the others.
   - If a batch does not end with `screenshot`, you may attach a fresh screenshot as an extra `image` block on the **last** result in the batch. This saves a round trip.
5. **Send `response.content` back unchanged.** Thinking blocks must be passed back exactly as received.
6. **Ask for human approval per block.** If you gate consequential actions, check before each block runs; one turn can finish a multi-step action.

### Python loop (SDK 1.12.1, non-beta)
In 1.12.1, `ToolUseBlock.toolset_name: Optional[str]` and `ToolResultBlockParam.toolset_name` both exist.
```python
from anthropic import Anthropic
client = Anthropic()
TOOLS = [{"type": "computer_toolset_20260801"}]
HALT = "Not executed: an earlier computer action in this turn failed."

while True:
    resp = client.messages.create(model="claude-opus-5-5", max_tokens=16000, tools=TOOLS, messages=messages)
    messages.append({"role": "assistant", "content": resp.content})
    results, failed = [], False
    for b in resp.content:
        if b.type != "tool_use":
            continue
        if b.toolset_name != "computer":
            results.append(run_other_tool(b))          # bash etc.; no toolset_name on these
            continue
        r = {"type": "tool_result", "tool_use_id": b.id, "toolset_name": "computer"}
        if failed:
            r.update(content=HALT, is_error=True)
        else:
            try:
                r["content"] = executor.run(b.name, b.input)   # str, or [image block] for screenshot/zoom
            except Exception as e:
                r.update(content=f"Error: {e}", is_error=True)
                failed = True
        results.append(r)
    if not results:
        break
    messages.append({"role": "user", "content": results})
```

### Alternative: the SDK helper class (beta)
The `anthropic.tools.computer` module in 1.12.1 provides:
- `BetaAbstractComputerToolset20260801` and `BetaAsyncAbstractComputerToolset20260801`
- `BetaScreenshotResult(data=..., media_type="image/png")`
- `BetaComputerCursorPositionResult(x, y)`
- `BetaComputerConfirmContext`
- `BetaToolsetCallContext`

How it works:
- You subclass it, override one method per member, and pass the instance in `tools` to `client.beta.messages.tool_runner(...)`, or answer calls yourself with `instance.tool_result(block)`.
- Members you don't implement are sent to the API as `enabled: false`.
- The constructor **requires a `confirm=` callable** while `type`, `key` or `hold_key` is enabled.
- The SDK checks input types but not values, and **never resizes images**.
- `stream=True, run_tools_eagerly=True` lets calls start while the response is still streaming.

---

## 3. Screenshot requirements

**Size limits for Opus 5.5 and Sonnet 5.5** (the "high-resolution" tier, which covers Claude 4.7 and later; the computer-use page confirms it applies to every toolset model):
- Long edge at most **2576 px**.
- Visual tokens `ceil(w/28) * ceil(h/28)` at most **4784** (about 3.75 MP).

**The API does not downscale toolset images.** An oversized screenshot or zoom image in a `tool_result` is **rejected with a validation error**. You must resize before returning it.

**Other limits that also apply**
- Once a request holds **more than 20 images** (resent history counts, as do images inside `tool_result`s), a stricter per-image limit applies to every image. Stay safe by keeping each side at **2000 px or less**, or keeping 20 or fewer images in the request.
- Max 8000x8000 px per image.
- **10 MB per image (base64)** on the Claude API; 5 MB on Bedrock and Vertex.
- 32 MB per request; up to 600 images per request.

**Format**
- Accepted types: PNG, JPEG, GIF, WebP. The block shape is `{"type":"image","source":{"type":"base64","media_type":"image/png","data":"<b64, no newlines>"}}`.
- The docs say: "Encode screenshots as base64 PNG or JPEG, and consider compressing large screenshots."
- The vision page warns that heavy JPEG compression makes text harder to read.
- Both reference implementations send PNG. My recommendation: use PNG; use JPEG at quality 85 or higher only if bandwidth matters.

**Recommended resolution** (from the computer-use page)
- General desktop work: 1024x768 or 1280x720.
- Web applications: **1280x800** or 1366x768.
- Avoid anything above 1920x1080.
- If accuracy is poor, try 1280x720 as a baseline.
- The skill's migration notes (written for Opus 4.7 with `computer_20251124`) call 1080p "a good balance", and 720p or 1366x768 the cheaper options.

Visual tokens per screenshot at common sizes (high-res tier):

| Size | Tokens |
|---|---|
| 1024x768 | 1036 |
| 1280x720 | 1196 |
| 1280x800 | 1334 |
| 1366x768 | 1372 |
| 1920x1080 | 2691 |

**My recommendation for Minion:** run Xvfb at **1280x800x24** and send screenshots at native size. That needs no scaling, stays under the 2000 px rule, and costs about 1,334 tokens each.

**If you do scale**
- Keep the screenshot size fixed for the whole session and keep the display's aspect ratio.
- Convert Claude's points to display pixels: `x_disp = x * DISP_W // SHOT_W`.
- Report `cursor_position` back in screenshot pixels, rounded to an integer.
- Scale a `zoom` region by the same factor, and crop it from a **display-resolution** capture.
- On a macOS Retina display, account for the 2x pixel ratio.
- To compute the exact size, use the docs' helper (from vision-coordinates):
```python
import math
def resized_size(w, h, max_edge=2576, max_tokens=4784):   # high-res tier values
    fits = lambda W, H: (math.ceil(W/28)*28 <= max_edge and math.ceil(H/28)*28 <= max_edge
                         and math.ceil(W/28)*math.ceil(H/28) <= max_tokens)
    if fits(w, h): return (w, h)
    if h > w: rh, rw = resized_size(h, w, max_edge, max_tokens); return (rw, rh)
    ar, lo, hi = w/h, 1, w
    while lo + 1 < hi:
        mid = (lo+hi)//2
        lo, hi = (mid, hi) if fits(mid, max(round(mid/ar), 1)) else (lo, mid)
    return (lo, max(round(lo/ar), 1))
```
For long sessions (more than 20 images), also cap each side at 2000 px.

**Screenshot history**
- Each screenshot costs roughly 1,000 to 1,800 input tokens.
- **On Opus 5.5, Sonnet 5.5, Fable 5.1 and Haiku 5.5, don't remove old screenshots on the client.** Removing an earlier screenshot invalidates every later thinking block.
- Instead, keep screenshots at 2000 px or less per side and use server-side tool-result clearing. This is beta: header `context-management-2025-06-27` with `context_management: {"edits": [{"type": "clear_tool_uses_20250919"}]}`.
- If you must prune on the client, set `prefix_mismatch_behavior: "drop_block"`.
- Caching: one breakpoint after the system prompt and tools, plus up to three on the last `tool_result` of the most recent turns, moved forward each turn (four in total).

**Security note:** Anthropic automatically scans screenshots for prompt injection; opting out requires contacting support.

---

## 4. `browser_toolset_20260801`: it exists, GA

**Availability.** GA on the Claude API and Google Cloud only; not on Bedrock, Claude Platform on AWS or Foundry. Same model list as the computer toolset. No beta header.

**Entry and calls**
- Entry: `{"type":"browser_toolset_20260801"}`, with no `name`. Same `configs`, `cache_control` and `allowed_callers` rules as the computer toolset.
- Calls carry **`"toolset_name":"browser"`**.
- Your executor runs everything against a browser you host (Playwright or CDP); nothing runs on Anthropic's side.
- Cost: about **6,600** input tokens, plus about 880 more if all 4 optional members are enabled.

**31 members: 27 on by default, 4 off.** Every member also accepts an optional `tab_id`, which defaults to the active tab.

| Group | Member: input |
|---|---|
| Navigation and capture | `navigate`: `url` (http/https, or `"back"`/`"forward"`/`"reload"`; a URL without a scheme means `https://`; **refuse every other scheme**); `screenshot`: none; `zoom`: `region [x0,y0,x1,y1]` in viewport pixels |
| Pointer | `left_click`, `right_click`, `middle_click`, `double_click`, `triple_click`: `target: Target`, `modifiers?` (e.g. `"shift"`, `"ctrl+shift"`, `"cmd+alt"`); `hover`: `target: Target`; `left_click_drag`: `from: CoordinateTarget`, `target: CoordinateTarget`; `left_mouse_down`, `left_mouse_up`, `mouse_move`: `target: CoordinateTarget`; `scroll`: `target: CoordinateTarget` (required), `scroll_direction`, `scroll_amount?` (1 to 10, default 3); `scroll_to`: `target: RefTarget` |
| Keyboard and timing | `type`: `text`; `key`: `text` (one key, a `+` chord, or a **space-separated sequence** such as `"Backspace Backspace"`), `repeat?` (1 to 100); `hold_key`: `text`, `duration` (0 to 30 s); `wait`: `duration` (0 to 30 s) |
| Page reading | `read_page`: `filter?` (omitted = visible elements, `"interactive"`, or `"all"`), `depth?` (minimum 1, default 15), `ref?`; returns the accessibility tree as text with `[ref_N]` tags; **cap output at 50,000 characters and say so**. `find`: `query` (natural language); up to 20 matches in the same format. `get_page_text`: none |
| Forms and files | `form_input`: `target: RefTarget`, `value` (string, number or boolean); `file_upload` (**off by default**): `target: RefTarget`, `paths?`, `document_ids?` (at least one) |
| Diagnostics | `read_console`, `read_network` (**off by default**): no input; `javascript_exec` (**off by default**): `text` (a JS expression; return the value of the last expression) |
| Tabs | `new_tab`: none; `list_tabs`: none; `switch_tab`: `tab_id` (required); `close_tab`: `tab_id` (required) |

**Target shapes**
- `{"type":"coordinate","x":int,"y":int}`, in **viewport** pixels with no window frame.
- `{"type":"ref","ref":"ref_2"}`. References are scoped to the tab and become stale after navigation or a major re-render.

**Results**
- Allowed block types: `text`, `image` and `browser_state` only.
- `screenshot` and `zoom` need an image.
- `new_tab`, `switch_tab`, `close_tab` and `list_tabs` must return **exactly one `browser_state` block** and nothing else. A `new_tab` result must include exactly one `tab_opened` state change matching the active tab.
- The `browser_state` block shape:
```json
{"type":"browser_state",
 "tabs":[{"tab_id":"tab-1","title":"Docs","url":"https://example.com/docs","active":true}],
 "state_changes":[{"type":"tab_opened","tab_id":"tab-1"}]}
```
- `tabs` is the full list of open tabs, not a change list. If it is non-empty, exactly one tab must be `active`.
- `state_changes` may also contain `download_started` / `download_completed` / `download_failed` entries keyed by a `download_id` you assign.
- Never send a `browser_state` block on an error result. Never send an empty `state_changes` array; omit the field instead.
- Field limits: 4,096 characters; at most 100 tabs and 200 state changes.
- **Halt text differs from the computer toolset:** `Not executed: an earlier action in this turn failed.`

**SDK:** `anthropic.tools.browser.BetaAbstractBrowserToolset20260801` (and an async variant) with `url_policy=`, `file_policy=`, and a `_browser_state()` method. A CDP quickstart lives in the quickstarts repo under `browser-toolset/`.

**Is it a better fit for web tasks? Yes, for anything that stays inside web pages.** The docs say so explicitly:
- Element references survive layout shifts.
- A `read_page` of a typical page often costs fewer tokens than a screenshot.
- `form_input`, `get_page_text` and tab tracking have no computer-use equivalent.
- It needs no desktop.

Its executor is a browser-automation driver, not xdotool. Keep the computer toolset for native apps and anything outside the page.

**Both toolsets can share one request.** Each keeps its own coordinate frame, and `toolset_name` tells same-named members apart (`screenshot`, `key`).

**Suggested design for Minion (my recommendation, not from the docs):** run a headed Chromium on the Xvfb display with `--remote-debugging-port`. The human then watches it through noVNC, `browser_toolset` drives it over CDP, and `computer_toolset` drives the rest of the desktop with xdotool.

---

## 5. Reference implementation: how `computer-use-demo/tools/computer.py` uses xdotool

**Environment variables:** `WIDTH`, `HEIGHT`, `DISPLAY_NUM`. The Dockerfile defaults are `WIDTH=1024`, `HEIGHT=768`, `DISPLAY_NUM=1`. Every command is prefixed with `DISPLAY=:{n} `.

**Toolset class.** `ComputerToolset20260801` subclasses the older tool and sends `{"type":"computer_toolset_20260801"}` as its entry. `ToolCollection.run` routes a toolset call as `toolset(action=<member name>, **input)`.

**Screenshots after actions.** Every action runs through `shell()`, which by default **waits 2.0 s and attaches a screenshot** to the result. `type` attaches one at the end, `wait` returns a screenshot, and `cursor_position` attaches none.

### Command for each member (exact strings)

| Member | Command |
|---|---|
| `screenshot` | `gnome-screenshot -f {path} -p` if gnome-screenshot is installed, otherwise `scrot -p {path}`. Then, when scaling is on: `convert {path} -resize {W}x{H}! {path}`. ImageMagick's `import` is **not** used. Output is base64 PNG. |
| `zoom` | Capture at full resolution to `raw`, then `convert raw -crop {x1-x0}x{y1-y0}+{x0}+{y0} +repage -resize {frameW}x{frameH} zoom.png`. The region is first scaled from screenshot to display pixels. |
| `left_click`, `right_click`, `middle_click`, `double_click`, `triple_click` | `xdotool [mousemove --sync X Y] [keydown MOD] click {BTN} [keyup MOD]`. BTN is 1 for left, 3 for right, 2 for middle, `--repeat 2 --delay 10 1` for double, `--repeat 3 --delay 10 1` for triple. MOD is the toolset's `text` field. |
| `mouse_move` | `xdotool mousemove --sync X Y` |
| `left_click_drag` | `xdotool mousemove --sync SX SY mousedown 1 mousemove --sync EX EY mouseup 1`. With `text`: `xdotool keydown 'MOD' mousemove --sync SX SY mousedown 1 mousemove --sync EX EY mouseup 1 keyup 'MOD'` |
| `left_mouse_down` / `left_mouse_up` | `xdotool mousedown 1` / `xdotool mouseup 1` |
| `scroll` | `xdotool [mousemove --sync X Y] [keydown MOD] click --repeat {amount} {4\|5\|6\|7} [keyup MOD]`. Buttons: 4 up, 5 down, 6 left, 7 right. |
| `type` | The text is split into 50-character chunks; each runs `xdotool type --delay 12 -- {shlex.quote(chunk)}`; then one screenshot. |
| `key` | `xdotool key -- {' '.join([shlex.quote(text)] * repeat)}`, with `repeat` from 1 to 100, default 1. |
| `hold_key` | `xdotool keydown {q} sleep {duration} keyup {q}`. The demo caps duration at 100 s, an older limit; the docs now say up to 300. |
| `wait` | `asyncio.sleep(duration)`, then a screenshot. |
| `cursor_position` | `xdotool getmouselocation --shell`; parse `X=` and `Y=`; scale display to screenshot pixels; return `X={x},Y={y}`. |

### Key code from the demo (verbatim)
```python
TYPING_DELAY_MS = 12
TYPING_GROUP_SIZE = 50
MAX_SCALING_TARGETS = {"XGA": Resolution(width=1024, height=768),
                       "WXGA": Resolution(width=1280, height=800),
                       "FWXGA": Resolution(width=1366, height=768)}
CLICK_BUTTONS = {"left_click": 1, "right_click": 3, "middle_click": 2,
                 "double_click": "--repeat 2 --delay 10 1",
                 "triple_click": "--repeat 3 --delay 10 1"}

def scale_coordinates(self, source, x, y):
    if not self._scaling_enabled: return x, y
    ratio = self.width / self.height
    target_dimension = None
    for dimension in MAX_SCALING_TARGETS.values():
        if abs(dimension["width"] / dimension["height"] - ratio) < 0.02:
            if dimension["width"] < self.width: target_dimension = dimension
            break
    if target_dimension is None: return x, y
    x_scaling_factor = target_dimension["width"] / self.width
    y_scaling_factor = target_dimension["height"] / self.height
    if source == ScalingSource.API:            # model -> display (scale up)
        if x > self.width or y > self.height: raise ToolError(f"Coordinates {x}, {y} are out of bounds")
        return round(x / x_scaling_factor), round(y / y_scaling_factor)
    return round(x * x_scaling_factor), round(y * y_scaling_factor)   # display -> model

# toolset `key` with repeat:
keys = " ".join([shlex.quote(text)] * repeat)
return await self.shell(f"{self.xdotool} key -- {keys}")

# the toolset's `text` modifier is passed on as the older class's `key=`:
if action in CLICK_BUTTONS and text is not None:
    return await super().__call__(action=action, key=text, **kwargs)
```

### Halt text and result builder from `loop.py`
- The halt text is `NOT_EXECUTED_ERROR = "Not executed: an earlier computer action in this turn failed."`
- `_make_api_tool_result` builds `{"type":"tool_result","content":[text?, image(png b64)?] or error string,"tool_use_id":id,"is_error":bool,"toolset_name":"computer"}`.
- The halt flag is set by any result that has `.error`.

### Key-name mapping
**`computer-use-demo` has no key-name translation table.** The model's `text` goes to `xdotool key -- <text>` unchanged.

xdotool's only built-in aliases (from `xdo_util.h`, verified against source) are matched case-insensitively against each `+`-separated token:
```c
static const char *symbol_map[] = {
  "alt","Alt_L", "ctrl","Control_L", "control","Control_L", "meta","Meta_L",
  "super","Super_L", "shift","Shift_L", "enter","Return", "return","Return", NULL,NULL };
```
Every other token goes to `XStringToKeysym`. That function is case-sensitive (standard Xlib behavior; not tested here), so `Page_Down`, `BackSpace` and `Escape` must use exact X keysym spelling. The SDK tells the model that key names are case-insensitive, so **the executor should normalize names before calling xdotool.**

The only actual mapping table in Anthropic's examples is in `computer-toolset/python/vnc_computer.py` (RFB keysyms):
```python
KEYSYMS = {
    "return": 0xFF0D, "enter": 0xFF0D, "tab": 0xFF09, "escape": 0xFF1B, "backspace": 0xFF08, "delete": 0xFFFF,
    "insert": 0xFF63, "home": 0xFF50, "end": 0xFF57, "page_up": 0xFF55, "page_down": 0xFF56, "space": 0x20,
    "left": 0xFF51, "up": 0xFF52, "right": 0xFF53, "down": 0xFF54, "shift": 0xFFE1, "ctrl": 0xFFE3,
    "control": 0xFFE3, "alt": 0xFFE9, "super": 0xFFEB, "cmd": 0xFFEB, "win": 0xFFEB,
    **{f"f{n}": 0xFFBD + n for n in range(1, 13)},
}
def keysym(name):   # single char -> its own keysym (Unicode keysym 0x01000000|cp beyond Latin-1)
```
That example also:
- clicks by sending press/release with a 0.01 s gap;
- holds modifiers down in order and releases them in reverse;
- maps `\n` to Return and `\t` to Tab while typing, with 12 ms between keys;
- refuses out-of-bounds points instead of clamping;
- waits 0.5 s before each screenshot;
- refuses screens larger than 1920x1200.

My recommended normalization for an xdotool executor (lower-case the token, then look it up; fall through if absent):
`{"esc":"Escape","escape":"Escape","backspace":"BackSpace","del":"Delete","delete":"Delete","tab":"Tab","space":"space","pageup":"Page_Up","page_up":"Page_Up","pgup":"Page_Up","pagedown":"Page_Down","page_down":"Page_Down","pgdn":"Page_Down","home":"Home","end":"End","insert":"Insert","up":"Up","down":"Down","left":"Left","right":"Right","cmd":"super","win":"super","meta":"super","option":"alt","f1".."f12":"F1".."F12"}`.

### Docker desktop from the demo
**Dockerfile** (Ubuntu 22.04) installs: `xvfb xterm xdotool scrot imagemagick mutter x11vnc tint2 firefox-esr libreoffice gedit pcmanfm galculator xpdf xpaint`, plus noVNC v1.5.0 and websockify v0.12.0.

**Startup sequence**
1. `Xvfb :1 -ac -screen 0 ${W}x${H}x24 -retro -dpi 96 -nolisten tcp -nolisten unix`
2. tint2
3. `mutter --replace --sm-disable`
4. `x11vnc -display :1 -forever -shared -wait 50 -rfbport 5900 -nopw`
5. `novnc_proxy --vnc localhost:5900 --listen 6080`

**Ports**
- 5900: VNC
- 6080: noVNC (`/vnc.html`)
- 8501: Streamlit
- 8080: combined UI

### Where the demo departs from current guidance
- **XGA/WXGA/FWXGA scaling** predates the toolset. Current models accept up to 2576 px / 4784 tokens, but the docs still recommend about 1280x800.
- **A screenshot is attached after every action**, after a 2 s delay. The API allows it, but it costs tokens; you can instead attach one only to the last result of a batch.
- **`hold_key` capped at 100 s** is an older limit; the docs now say up to 300 s.
- **The demo's `screenshot` result** adds xdotool stdout/stderr text next to the image; this is allowed.