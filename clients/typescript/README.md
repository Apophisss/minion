# minion-desktop for TypeScript and JavaScript

Give your TypeScript agents real Linux desktops. This is the client for [Minion](https://github.com/apophisss/minion)'s
HTTP API. It works with the Vercel AI SDK, Mastra, LangChain.js, the OpenAI and Anthropic SDKs, or your own loop.

- **No dependencies.** It uses the platform's `fetch` and needs Node.js 18+ (or any runtime with a standard `fetch`).
- **Typed.** Every method and every server response has a type.
- **Ready for function calling.** `listTools()` returns Minion's tools in OpenAI, Anthropic, Gemini or MCP format,
  `callTool()` runs them, and `toVercelAiTools()` plugs them into the Vercel AI SDK.
- **An npx command for MCP clients.** `npx -y minion-desktop mcp` starts Minion's MCP server (see [MCP](#mcp)).

## Install

The desktops run on a Minion server. Install it (Python 3.11+ and Docker) and start it:

```bash
pipx install minion-desktop               # or: uv tool install minion-desktop
minion serve --token "$(openssl rand -hex 16)"   # prints http://127.0.0.1:4747/?token=...
```

The package will be published to npm as `minion-desktop`. Until then, install it from the repository:

```bash
git clone https://github.com/apophisss/minion
cd minion/clients/typescript
npm install && npm pack                   # builds dist/ and writes minion-desktop-1.0.0.tgz
cd /path/to/your-project
npm install /path/to/minion/clients/typescript/minion-desktop-1.0.0.tgz
```

Once it is published, this will be `npm install minion-desktop`. The package is ESM only.

## Quick start

```ts
import { writeFile } from "node:fs/promises";
import { Minion } from "minion-desktop";

const minion = new Minion({ token: process.env.MINION_TOKEN }); // baseUrl: http://127.0.0.1:4747
const desk = await minion.create({ profile: "browser" }); // or "office", "dev", "research", "data", "base"

await desk.open("news.ycombinator.com");
const screen = await desk.see(); // the screen as text: every control has an @id
console.log(screen.text);

await desk.click("@12"); // an @id, visible text ("More"), "x,y" or [x, y]
await desk.act([{ action: "key", keys: "ctrl+f" }, { action: "type", text: "Show HN\n" }]);

const shot = await desk.screenshot({ marks: true }); // { data: Uint8Array, mime: "image/png" }
await writeFile("page.png", shot.data);
console.log(`Watch it live: ${desk.viewUrl()}`);

await desk.remove();
```

`new Minion()` takes these options:

| Option | Default | |
|---|---|---|
| `baseUrl` | `$MINION_URL`, else `http://127.0.0.1:4747` | A URL with `?token=...`, as `minion serve` prints it, works too |
| `token` | `$MINION_TOKEN` | Sent as `Authorization: Bearer <token>` |
| `session` | none | The session for tool calls (see [Tools](#tools-for-any-model)) |
| `timeoutMs` | no limit | Abort requests that take longer |
| `fetch` | `globalThis.fetch` | A custom `fetch` (proxies, tests) |
| `headers` | none | Extra headers for every request |

## API

Method options use camelCase. Results are the server's JSON as it is (for example `timed_out`), and each one has a
type. Durations in method options are in seconds, like everywhere else in Minion. Only `timeoutMs` is in milliseconds.

### `Minion`

| Method | Returns |
|---|---|
| `health()` | `{ ok, version, backend }` |
| `profiles()` | The profiles: `name`, `description`, `apps`, ... |
| `desktops({ stats? })` | `DesktopInfo[]`: `name`, `profile`, `state`, `size`, and `memory` and `cpu` with `stats: true` |
| `create({ profile?, name?, size? })` | A `Desktop`. The first desktop of a profile downloads its image first |
| `desktop(name)` | A `Desktop` handle for an existing desktop. It makes no request |
| `listTools(format?, { compact? })` | Tool definitions (see [Tools](#tools-for-any-model)) |
| `callTool(name, args?, { session?, signal? })` | `{ content, isError }` |
| `toVercelAiTools(options?)` | Tools for the Vercel AI SDK |
| `viewUrl(name?)` | The dashboard, or a desktop's live view. The URL contains the token |
| `request(method, path, options?)` / `requestRaw(...)` | Any endpoint, as JSON or as the raw `Response` |

### `Desktop`

| | Methods |
|---|---|
| Looking | `info()` (does not wake a frozen desktop) · `hello()` · `status()` · `windows()` · `see({ ocr?, window? })` returns `{ text, elements, windows, focused, ocr }` · `screenshot({ format?, maxWidth?, marks?, grid? })` returns `{ data, mime }` |
| Acting | `act(actions, { screenshot?, see?, check? })` · `click(target?, { button?, count?, modifiers? })` · `type(text)` · `paste(text)` · `key(keys, { repeat? })` · `scroll(direction?, amount?, target?)` · `fill(target, text)` · `drag(from, to)` · `waitFor(text, { timeout?, gone? })` |
| Apps and shell | `open(target, { wait? })` · `run(command, { timeout?, background? })` returns `{ code, stdout, stderr, timed_out }` · `clipboard()` · `setClipboard(text)` |
| Lifecycle | `freeze()` · `thaw()` · `stop()` · `start()` · `fork(name?)` returns a new `Desktop` · `snapshot(tag?)` returns the tag · `restore(tag)` · `remove()` |
| Humans and replay | `viewUrl()` · `handoff(message, { timeout? })` returns the human's note, or `null` on timeout · `replay()` returns an HTML timeline · `replayGif()` returns GIF bytes |

Targets are `"@12"` (an id from the latest `see()`), visible text (`"Save"`), `"x,y"`, `[x, y]` or `{ x, y }`.
`act()` runs a batch in one round trip. It stops at the first failure, waits for the screen to settle and reports
what changed. Actions can be objects, shorthands (`{ click: "@3" }`), strings (`"key ctrl+s"`) or Claude computer-use
actions (`{ action: "left_click", coordinate: [640, 400] }`):

```ts
const result = await desk.act([
  { action: "fill", target: "Email", text: "ada@example.com" },
  { action: "click", target: "Sign in" },
  { action: "wait_for", text: "Welcome" },
]);
console.log(result.summary); // ✓ filled ... ✓ clicked ... → screen changed 64% · focused "Inbox"
```

Hand a login or a CAPTCHA to a person and wait until they press Done in the live view:

```ts
console.log(`Please sign in: ${desk.viewUrl()}`);
const note = await desk.handoff("Please sign in to GitHub, then press Done", { timeout: 900 });
```

### Errors

Every failure throws a `MinionError` with the server's message and the HTTP `status`: 400 (bad request), 401 (wrong
token), 404 (unknown desktop or profile), 422 (the action failed), or 0 when there was no response (the server is not
running, or `timeoutMs` passed). `body` holds the parsed response. The messages are written so that you can show them
to a model as they are.

```ts
import { MinionError } from "minion-desktop";

try {
  await desk.click("Sign in");
} catch (error) {
  if (error instanceof MinionError && error.status === 422) console.log(error.message, error.body); // body: the ActResult
  else throw error;
}
```

Action helpers throw when an action fails. Pass `{ check: false }` to get the result and check `ok` yourself.

Node's built-in `fetch` gives up on responses that take longer than 5 minutes. For very slow calls (a long
`run()`, or the first `create()` of a profile on a slow network), use `run(..., { background: true })`, run
`minion pull <profile>` first, or raise the limit with undici:
`setGlobalDispatcher(new Agent({ headersTimeout: 0, bodyTimeout: 0 }))`.

## Tools for any model

Minion's tools are the same over MCP, HTTP and Python: `desktop`, `see`, `screenshot`, `act`, `open`, `run`, `script`,
`files` and `view`. You can also ask for one compact `computer` tool that takes CLI-style commands. Get the definitions
in the format your model API expects, give them to the model, and run its calls with `callTool()`:

| `listTools(format)` | For |
|---|---|
| `"openai"` (default) | OpenAI Chat Completions and compatible APIs (`{ type: "function", function: {...} }`) |
| `"openai-responses"` | The OpenAI Responses API |
| `"anthropic"` | The Anthropic Messages API (`{ name, description, input_schema }`) |
| `"gemini"` | Gemini function declarations |
| `"mcp"` | MCP tool definitions (`{ name, description, inputSchema }`) |

`callTool(name, args)` returns MCP's result shape: `{ content: [{ type: "text", text } | { type: "image", data,
mimeType }], isError }`. When a tool fails, for example because a target does not exist, the result has
`isError: true` and the text tells the model what to do next. Each **session** has its own "current desktop", so
give each agent its own session when several agents share a server: `new Minion({ session: "agent-7" })`, or
`callTool(name, args, { session })`.

### Vercel AI SDK

`toVercelAiTools()` turns the tools into AI SDK tools without depending on the `ai` package. It works with AI SDK 4
through 7. Screenshots reach the model as images, and a failed call reaches the model as an error result so that it
can try something else.

```ts
import { anthropic } from "@ai-sdk/anthropic";
import { generateText, stepCountIs } from "ai";
import { Minion } from "minion-desktop";

const minion = new Minion({ token: process.env.MINION_TOKEN });

const { text } = await generateText({
  model: anthropic("claude-opus-5-5"),
  tools: await minion.toVercelAiTools(),
  stopWhen: stepCountIs(40), // AI SDK 4: maxSteps: 40
  prompt: "Create a browser desktop, find the population of Iceland on Wikipedia and tell me.",
});
console.log(text);
```

To give each agent its own desktop, create it in code and pin the tools to it. The `desktop` argument is then hidden
from the model:

```ts
const desk = await minion.create({ profile: "office" });
const tools = await desk.toVercelAiTools({ exclude: ["desktop"] }); // the agent can't create or remove desktops
```

Options: `session`, `desktop` (a name or a `Desktop`), `include` and `exclude` (tool names), `compact` (the single
`computer` tool), and `jsonSchema` (pass `jsonSchema` from `ai` if you prefer the SDK to build the schemas).

### Any function-calling loop

The same thing with the OpenAI SDK and Chat Completions. Tool messages there can't hold images, so screenshots go
in a user message after the tool results:

```ts
import OpenAI from "openai";
import { Minion } from "minion-desktop";

const openai = new OpenAI();
const minion = new Minion({ token: process.env.MINION_TOKEN, session: "agent-1" });
const tools = await minion.listTools("openai");

const messages: OpenAI.ChatCompletionMessageParam[] = [
  { role: "user", content: "Open example.com in a browser desktop and tell me what the page says." },
];
for (let step = 0; step < 40; step++) {
  const response = await openai.chat.completions.create({ model: "gpt-5", messages, tools });
  const message = response.choices[0]!.message;
  messages.push(message);
  if (!message.tool_calls?.length) {
    console.log(message.content);
    break;
  }
  const images: OpenAI.ChatCompletionContentPartImage[] = [];
  for (const call of message.tool_calls) {
    if (call.type !== "function") continue;
    const result = await minion.callTool(call.function.name, JSON.parse(call.function.arguments || "{}"));
    const text = result.content.flatMap((c) => (c.type === "text" ? [c.text] : [])).join("\n");
    messages.push({ role: "tool", tool_call_id: call.id, content: text || "(the image follows)" });
    for (const c of result.content) {
      if (c.type === "image") images.push({ type: "image_url", image_url: { url: `data:${c.mimeType};base64,${c.data}` } });
    }
  }
  if (images.length) messages.push({ role: "user", content: [{ type: "text", text: "Screenshots from the tool calls:" }, ...images] });
}
```

For the Responses API, use `listTools("openai-responses")`. Those definitions carry `strict: false`, because
Minion's schemas have optional arguments.

With the Anthropic Messages API, use `listTools("anthropic")`. A result maps directly to a `tool_result` block,
images included:

```ts
const result = await minion.callTool(block.name, block.input as Record<string, unknown>);
const toolResult: Anthropic.ToolResultBlockParam = {
  type: "tool_result",
  tool_use_id: block.id,
  is_error: result.isError,
  content: result.content.map((c) =>
    c.type === "text"
      ? { type: "text", text: c.text }
      : { type: "image", source: { type: "base64", media_type: c.mimeType as "image/png", data: c.data } },
  ),
};
```

Mastra, LangChain.js and other frameworks can wrap `listTools("mcp")` and `callTool()` in their own tool helpers in
the same way.

### MCP

Agents that speak MCP can skip HTTP and use Minion's MCP server directly. It offers the same tools over stdio:

```bash
npx -y minion-desktop mcp   # with this package
uvx minion-desktop mcp      # or `minion mcp` if Minion is installed
```

In any MCP client (the Vercel AI SDK's MCP client, `@mastra/mcp`, `@langchain/mcp-adapters`,
`@modelcontextprotocol/sdk`, ...), configure a stdio server with the command `npx` and the arguments
`["-y", "minion-desktop", "mcp"]`, or `uvx` and `["minion-desktop", "mcp"]`. See [docs/agents.md](../../docs/agents.md).

This package's `minion-desktop` command is a launcher: Minion is a Python program, so it runs `minion` from PyPI in
the same version as this package with uvx, else `pipx run`, else an installed `minion` command, and passes stdin and
stdout straight through. It needs [uv](https://docs.astral.sh/uv/) or pipx, and Docker for the desktops. Any
arguments go to `minion` (`npx -y minion-desktop doctor`), and `MINION_SPEC` picks another version or a fork
(`MINION_SPEC=git+https://github.com/apophisss/minion`).

## Security

The token gives full control of every desktop, and `viewUrl()` links contain it. Anything an agent reads on screen
may be adversarial (prompt injection), so keep long-lived credentials out of desktops and hand sign-ins to a human
with `handoff()`. The `files` tool's `upload` and `download` actions read and write files on the machine that runs
`minion serve`, but only inside its `MINION_FILES_ROOT` folder. Leave that tool out (`exclude: ["files"]`) if
agents should not reach even that folder. See [SECURITY.md](../../SECURITY.md).

## Development

```bash
npm install
npm test               # builds, then runs the offline tests: a fake server, and fake uvx and pipx for the launcher

# Against a real server (creates no desktops). MINION_HOME keeps this server out of your Minion state.
MINION_HOME="$(mktemp -d)" minion serve --port 4810 --token tstok --idle-freeze 0 --quiet &
MINION_URL=http://127.0.0.1:4810 MINION_TOKEN=tstok npm run smoke
```
