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
| `POST /api/desktops` | `{profile, name?, size?}` | the new desktop (201) |
| `GET /api/desktops/{name}` | | info + agent hello |
| `GET /api/desktops/{name}/info` | | info without waking the desktop |
| `DELETE /api/desktops/{name}` | | |
| `GET /api/desktops/{name}/screenshot` | `?format=png\|jpeg\|webp&max_width=&marks=1&grid=1&download=1` | image |
| `GET /api/desktops/{name}/see` | `?ocr=1&window=` | `{text, elements, windows, focused, ocr}` |
| `GET /api/desktops/{name}/windows` | | windows |
| `GET /api/desktops/{name}/status` | | uptime, idle seconds, memory, recorder |
| `POST /api/desktops/{name}/act` | `{actions: [...], screenshot?, see?}` | `{ok, summary, steps, change, opened, closed, focused, screenshot?}` |
| `POST /api/desktops/{name}/open` | `{target, wait?}` | `{command, kind, window}` |
| `POST /api/desktops/{name}/run` | `{command, timeout?, background?}` | `{code, stdout, stderr, timed_out}` |
| `POST /api/desktops/{name}/clipboard` | `{text?}` | set, or `{text}` |
| `POST /api/desktops/{name}/freeze` · `thaw` · `stop` · `start` | | `{ok, state}` |
| `POST /api/desktops/{name}/snapshot` | `{tag?}` | `{tag}` |
| `POST /api/desktops/{name}/restore` | `{tag}` | |
| `POST /api/desktops/{name}/fork` | `{name?}` | the new desktop |
| `GET /api/desktops/{name}/replay` | `?format=gif` | HTML timeline or GIF |
| `GET /api/desktops/{name}/frame` | `?since=KEY&wait=MS&max_width=` | JPEG, or `204` if unchanged (long poll; header `X-Frame-Key`) |
| `POST /api/desktops/{name}/input` | `{type: move\|down\|up\|click\|scroll\|key\|type, ...}` | raw human input (used by the live view) |
| `GET/POST/DELETE /api/desktops/{name}/handoff` | POST `{message}` to request, POST `{note}` to finish | the pending hand-off |

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
"current desktop", so many agents can share one server.

Mutating requests must carry the Bearer token, a JSON content type or the `X-Minion: 1` header, which stops
other web pages from forging them. On a loopback bind, only loopback `Host` names are accepted.

```bash
T=your-token
curl -s -H "Authorization: Bearer $T" -X POST localhost:4747/api/desktops -d '{"profile":"browser"}'
curl -s -H "Authorization: Bearer $T" -X POST localhost:4747/api/desktops/browser-1/open -d '{"target":"example.com"}'
curl -s -H "Authorization: Bearer $T" localhost:4747/api/desktops/browser-1/see | jq -r .text
curl -s -H "Authorization: Bearer $T" -X POST localhost:4747/api/desktops/browser-1/act \
     -d '{"actions":[{"action":"click","target":"More information..."}]}' | jq -r .summary
```
