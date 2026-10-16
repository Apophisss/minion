# HTTP API

```bash
minion serve                          # http://127.0.0.1:4747/?token=<random>
minion serve --host 0.0.0.0 --token "$(openssl rand -hex 16)"   # reachable from your network
```

Every request needs the token, given as `Authorization: Bearer <token>`, as `?token=`, or through the cookie
that the dashboard sets. Static assets (`/static/*`) are public. JSON in, JSON out. Errors look like
`{"error": "..."}` with status 400 (bad request), 401, 404 (unknown desktop/profile) or 422 (the action failed).

| Method & path | Body / query | Returns |
|---|---|---|
| `GET /api/health` | | `{ok, version, backend}` |
| `GET /api/profiles` | | profiles |
| `GET /api/desktops` | `?stats=1` | desktops (with memory/CPU) |
| `POST /api/desktops` | `{profile, name?, size?, login?}` | the new desktop (201). `login`: start signed in, from a saved sign-in (its profile) |
| `GET /api/desktops/{name}` | | info + agent hello |
| `GET /api/desktops/{name}/info` | | info without waking the desktop |
| `DELETE /api/desktops/{name}` | | |
| `GET /api/desktops/{name}/screenshot` | `?format=png\|jpeg\|webp&max_width=&marks=1&grid=1&download=1` | image |
| `GET /api/desktops/{name}/see` | `?ocr=1&lang=heb&window=&menus=1` | `{text, elements, windows, focused, ocr}` (+ `menus` with `menus=1`) |
| `GET /api/desktops/{name}/windows` | | windows |
| `GET /api/desktops/{name}/status` | | uptime, idle seconds, memory, recorder |
| `POST /api/desktops/{name}/act` | `{actions: [...], screenshot?, see?}` | `{ok, summary, steps, change, opened, closed, focused, screenshot?}` |
| `POST /api/desktops/{name}/open` | `{target, wait?, install?}` | `{command, kind, window, installed?, tips?}`: apps by name are installed first unless `install` is false |
| `POST /api/desktops/{name}/read` | `{path, max_chars?}` | `{text}`: any document as text (docx, xlsx, pptx, odt, pdf, epub, html, images by OCR, …) |
| `POST /api/desktops/{name}/convert` | `{path, to, outdir?}` | `{path}` of the converted file (pdf, docx, xlsx, csv, pptx, png, md, …) |
| `POST /api/desktops/{name}/run` | `{command, timeout?, background?}` | `{code, stdout, stderr, timed_out}` |
| `POST /api/desktops/{name}/clipboard` | `{text?}` | set, or `{text}` (all of it) |
| `GET /api/desktops/{name}/files` | `?path=~/Downloads&hidden=1` | `{path, shown, home, entries: [{name, dir, size, modified}], total}`: folders first |
| `GET /api/desktops/{name}/download` | `?path=~/Downloads/report.pdf` | the file as a download; a folder comes as a `.zip` |
| `POST /api/desktops/{name}/upload` | `?path=FOLDER&name=FILE`, the file as the body | `{path, name, size}` (201). An existing name gets " (1)", as browsers do. Up to 2 GB (`MINION_UPLOAD_MAX_MB`) |
| `POST /api/desktops/{name}/login` | `{name, site?}` | save the desktop as a sign-in that new desktops start from (201) |
| `GET /api/logins` · `DELETE /api/logins/{name}` | | the saved sign-ins: `[{name, profile, site, created}]` |
| `POST /api/desktops/{name}/freeze` · `thaw` · `stop` · `start` | | `{ok, state}` |
| `POST /api/desktops/{name}/snapshot` | `{tag?}` | `{tag}` |
| `POST /api/desktops/{name}/restore` | `{tag}` | |
| `POST /api/desktops/{name}/fork` | `{name?}` | the new desktop |
| `GET /api/desktops/{name}/replay` | `?format=gif` | HTML timeline or GIF |
| `GET /api/desktops/{name}/frame` | `?since=KEY&wait=MS&max_width=` | JPEG, or `204` if unchanged (long poll; header `X-Frame-Key`) |
| `POST /api/desktops/{name}/input` | `{type: move\|down\|up\|click\|scroll\|key\|type, ...}` | raw human input (used by the live view) |
| `GET/POST/DELETE /api/desktops/{name}/handoff` | POST `{message}` to request, POST `{note}` to finish | the pending hand-off. Files the person uploads meanwhile are added to the note |

Pages: `/` is the dashboard and `/view/{name}` is the live view.

## Universal tools (any agent, any language)

| Method & path | |
|---|---|
| `GET /api/tools?format=openai\|openai-responses\|anthropic\|gemini\|mcp[&compact=1]` | tool definitions ready for that API |
| `POST /api/tools/call` | `{"name": "see", "arguments": {...}, "session": "agent-7"}` |
| `POST /api/tools/{name}` | the arguments as the body (one REST endpoint per tool) |
| `GET /openapi.json` | OpenAPI 3.1 for the tools (public). Import it into GPT Actions, Dify, n8n or OpenAPI toolkits |

Results always look like `{"content": [{"type": "text", "text": "..."}, {"type": "image", "data": "<base64>",
"mimeType": "image/png"}], "isError": false}`. Each `session` (or `X-Minion-Session` header) keeps its own
"current desktop", so many agents can share one server. Over HTTP, `files` `upload`/`download` only use paths
inside `MINION_FILES_ROOT` on the server (default `files/` in Minion's data directory; relative paths start
there). To move content without touching the server's disk, use `files` `read`/`write`.

The TypeScript client ([`clients/typescript`](../clients/typescript)) wraps these endpoints, including
`toVercelAiTools()` for the Vercel AI SDK.

Mutating requests must carry the Bearer token, a JSON content type or the `X-Minion: 1` header, which stops
other web pages from forging them. On a loopback bind, only loopback `Host` names are accepted, plus the
names in `MINION_ALLOWED_HOSTS` (comma-separated, e.g. your reverse proxy's domain; once set, the check
applies on any bind).

```bash
T=your-token
curl -s -H "Authorization: Bearer $T" -X POST localhost:4747/api/desktops -d '{"profile":"browser"}'
curl -s -H "Authorization: Bearer $T" -X POST localhost:4747/api/desktops/browser-1/open -d '{"target":"example.com"}'
curl -s -H "Authorization: Bearer $T" localhost:4747/api/desktops/browser-1/see | jq -r .text
curl -s -H "Authorization: Bearer $T" -X POST localhost:4747/api/desktops/browser-1/act \
     -d '{"actions":[{"action":"click","target":"More information..."}]}' | jq -r .summary
```

## Remote MCP (`/mcp`)

`minion serve` (and [`minion share`](remote.md), which puts it on a public HTTPS URL) also speaks the Model
Context Protocol over [Streamable HTTP](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports#streamable-http)
at `/mcp`: the same tools as `minion mcp`, for clients that connect by URL (ChatGPT, Claude.ai, Le Chat,
Cursor, VS Code, the MCP SDKs). Setup for each app: [remote.md](remote.md).

| | |
|---|---|
| Endpoint | `POST /mcp` (the path's case doesn't matter) |
| Auth | the token, as `?token=` in the URL (for chat apps that only take a URL) or `Authorization: Bearer`. The dashboard cookie doesn't count |
| Options | `?compact=1`: the single `computer` tool. `?images=0`: text only (no `screenshot` tool, images left out) |
| Protocol versions | `2025-11-25`, `2025-06-18`, `2025-03-26` (and `2024-11-05` in `initialize`) |
| Sessions | `initialize` returns an `Mcp-Session-Id` header; send it on every later request. Each session has its own toolkit, so its own "current desktop". `DELETE /mcp` with the header ends the session (`204`) |
| Responses | `tools/call` streams `text/event-stream` when the client accepts it: progress notifications (if the request has a `progressToken`), an SSE comment every 10 s while the tool works, then the result. Everything else is `application/json`. Notifications and responses get `202` with no body |

Errors are HTTP statuses with a JSON-RPC error (`id: null`) in the body: `400` for a missing
`Mcp-Session-Id`, an unsupported `MCP-Protocol-Version`, invalid JSON or a JSON-RPC batch (batches were
removed in 2025-06-18), `401` without the token (with `WWW-Authenticate: Bearer`), `403` for a refused
`Origin` or `Host`, `404` for an unknown or ended session (the client then initializes again), `405` for
`GET` (there is no server-initiated stream), `415` for a body that isn't `application/json`. Sessions idle
for 24 hours end, and so do the least recently used ones beyond 100.

The stateless revision `2026-07-28` isn't served yet. Clients that support it probe with a `2026-07-28`
request first; the `400` they get makes them fall back to `initialize`, as that spec's
backward-compatibility rules require (verified with the official Python SDK's `auto` mode).

**Origin.** The MCP spec asks servers to validate `Origin` against DNS rebinding. Clients that run on servers
(ChatGPT, Cursor, VS Code, the SDKs) send none, but claude.ai's backend sends `Origin: https://claude.ai`, so
the header alone proves nothing. On a public name (a tunnel's hostname or one in `MINION_ALLOWED_HOSTS`),
anyone with the token can call the URL directly, so every `Origin` is accepted and the `Host` check is what
stops rebinding pages. On a loopback name, `/mcp` accepts an `Origin` only from local pages
(`localhost`, `127.0.0.1`), from the chat apps' own origins (claude.ai, chatgpt.com, chat.mistral.ai, for
reverse proxies that rewrite `Host`), and from `MINION_ALLOWED_ORIGINS` (comma-separated); any other page
gets `403`.

```bash
T=your-token; U="http://127.0.0.1:4747/mcp?token=$T"
H=(-H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream')
curl -si "$U" "${H[@]}" -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"1"}}}' | grep -i mcp-session-id
S=…   # the Mcp-Session-Id value
curl -s "$U" "${H[@]}" -H "Mcp-Session-Id: $S" -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'   # 202
curl -s "$U" "${H[@]}" -H "Mcp-Session-Id: $S" -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | jq '[.result.tools[].name]'
curl -s "$U" "${H[@]}" -H "Mcp-Session-Id: $S" \
     -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"desktop","arguments":{"action":"list"}}}'
# event: message
# data: {"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"Desktops:\n- …"}],"isError":false}}
```

In `minion share`, `files` `upload`/`download` and saved sign-ins are off unless you pass `--files`, and waits
inside a tool call (desktop creation, hand-offs) stop at 45 s so that chat apps get an answer before they give up.
