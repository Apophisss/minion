# Remote MCP: Minion in ChatGPT, Claude.ai, Le Chat and other remote clients

Agent apps on your computer start Minion's MCP server themselves (`minion mcp`, over stdio). Web chat apps
can't: they run in the cloud and connect to MCP servers by **URL**. Minion serves MCP over Streamable HTTP at
`/mcp`, and `minion share` gives that endpoint a public HTTPS address in one command. People who never use a
terminal agent can then give ChatGPT, Claude or Le Chat a computer.

- [Quick start: `minion share`](#quick-start-minion-share)
- Connect: [ChatGPT](#chatgpt) · [Claude](#claude-claudeai-desktop-and-mobile) · [Le Chat](#le-chat-mistral) · [Cursor, VS Code, Claude Code](#cursor-vs-code-claude-code-and-other-clients-that-send-headers)
- [Your own server (VPS or home server)](#your-own-server-vps-or-home-server)
- [Security](#security) · [Timeouts and limits](#timeouts-and-limits) · [Troubleshooting](#troubleshooting)

## Quick start: `minion share`

```bash
pipx install minion-desktop     # needs Docker (or Podman)
minion pull browser office      # optional, but chat apps stop waiting long before a first-time download ends
minion share
```

```text
✓ Minion is online at https://cedar-quiet-ocean-lamp.trycloudflare.com  (Cloudflare quick tunnel, cloudflared in docker)

  MCP server URL (ChatGPT, Claude.ai, Le Chat: add a custom connector, no sign-in):
    https://cedar-quiet-ocean-lamp.trycloudflare.com/mcp?token=k3J…
  Apps that send headers (Cursor, VS Code, Claude Code): URL https://cedar-quiet-ocean-lamp.trycloudflare.com/mcp
    with the header  Authorization: Bearer k3J…
  Live view (watch and take over):
    https://cedar-quiet-ocean-lamp.trycloudflare.com/?token=k3J…
    http://127.0.0.1:4748/?token=k3J…  (this computer only)

  ! Anyone with this URL can use every Minion desktop on this computer: run programs in
    them, read their screens and files. Keep it private and press Ctrl+C when you're done.

Sharing. Press Ctrl+C to stop; the URL stops working with it.
  14:02:11  desktop create  (203.0.113.7)
  14:02:14  see  (203.0.113.7)
```

Paste the MCP server URL into your chat app (below), then ask: *"Create a browser desktop, open
wikipedia.org and tell me today's featured article."* Open the live view to watch, or to take over.

What `minion share` does:

- It starts a server on `127.0.0.1:4748` for this share only, with a fresh 256-bit token. It doesn't reuse your
  `minion serve` token, so stopping the share revokes the URL.
- It opens a [Cloudflare quick tunnel](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/),
  which needs no Cloudflare account. It uses the `cloudflared` program if it is installed, and otherwise the
  official `cloudflare/cloudflared` Docker image (about 30 MB, downloaded once). With Docker Engine on Linux
  that container uses the host's network. With Docker Desktop (macOS, Windows) it reaches Minion at
  `host.docker.internal`, which Docker Desktop forwards to this computer, so the server stays on 127.0.0.1.
- It checks that the public URL answers before printing it, and prints one line per tool call with the
  caller's IP address. If an address you don't recognize shows up, press Ctrl+C.
- Ctrl+C closes the tunnel and the server (so do `kill` and, on macOS and Linux, closing the terminal). The
  next `minion share` has a new URL and a new token.

| Option | |
|---|---|
| `--files` | let the `files` tool upload and download between desktops and this computer, inside `MINION_FILES_ROOT` (default `files/` in Minion's data folder). Off by default: see [Security](#security) |
| `--token TOKEN` | use your own token (at least 24 URL-safe characters) instead of a fresh one |
| `--port 4748` | the local port (`MINION_SHARE_PORT`); another free port is used if it is taken |
| `--compact` · `--no-images` | hand out a URL for the single `computer` tool, or text only (no screenshots) |
| `--docker` | run cloudflared in Docker even if it is installed |
| `--bind 0.0.0.0` | listen beyond loopback, only if cloudflared runs in a VM that can't reach this computer's 127.0.0.1 (`minion share` detects this and tells you). The trade-off: devices on your network can then reach the port, and that hop is plain HTTP, so someone on an untrusted network could read the token. The token is still required, and only the tunnel's hostname is accepted. Installing cloudflared avoids all of this |
| `--tailscale` | publish with [Tailscale Funnel](https://tailscale.com/docs/features/tailscale-funnel) instead: it prints the `tailscale funnel 4748` command to run, and the stable `https://<machine>.<tailnet>.ts.net/mcp?token=…` URL. Add `--token` to keep that URL across restarts |
| `--json` | print the URLs as one JSON object (for scripts) |

To install cloudflared instead of using Docker: `brew install cloudflared` (macOS),
`winget install --id Cloudflare.cloudflared` (Windows), or a package from
[Cloudflare's downloads page](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/).

## Connect a chat app

The URL already contains the token, so choose **no authentication** wherever the app asks. Treat the URL
like a password: anyone who has it can use your desktops until you stop sharing.

### ChatGPT

Custom MCP servers need a ChatGPT plan with developer mode. On Business, Enterprise and Edu workspaces, an
admin must allow it first. OpenAI moves these menus often, so check
[its help article](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt) if
yours look different. At the time of writing,
[OpenAI's guide](https://developers.openai.com/plugins/deploy/connect-chatgpt) describes these steps:

1. Open [ChatGPT Plugins](https://chatgpt.com/plugins), select **+**, then **Add custom MCP server**. If
   the option is missing, turn on **Developer mode** in Settings first.
2. Enter a name (`Minion`) and a description ("Linux desktops with a browser and office apps").
3. Under **Connection**, enter the MCP server URL that `minion share` printed (it ends in `/mcp?token=…`).
4. Set authentication to none, review the risk warning, and select **I understand and want to continue**.
5. Select **Create as a plugin**, and check that the nine tools (`desktop`, `see`, `act`, …) are listed.
6. In a new conversation, type **@** and pick Minion. ChatGPT asks before tools that change things run.

### Claude (claude.ai, Desktop and mobile)

From [Anthropic's guide](https://claude.com/docs/connectors/custom/add-unlisted) (custom connectors work on
every plan; the Free plan allows one):

1. Go to [**Customize > Connectors**](https://claude.ai/customize/connectors) and click **Add custom
   connector**. On Team and Enterprise plans an Owner adds it in **Organization settings > Connectors**
   (**Add**, **Custom**, **Web**), and members then click **Connect** next to it.
2. Name it `Minion` and paste the MCP server URL.
3. Under **Authentication**, choose **No sign-in**, then click **Add**. If your organization has the
   **Request headers** option (a beta), you can instead use the URL without `?token=…` and add the header
   `Authorization` with the value `Bearer <token>`.
4. In a chat, click **+**, then **Connectors**, and turn Minion on. Approve tool calls when Claude asks, and
   use **Always allow** only for tools you're comfortable with.

Claude connects from Anthropic's servers, so a `127.0.0.1` URL can't work: use the URL from `minion share` or
from [your own server](#your-own-server-vps-or-home-server).

### Le Chat (Mistral)

Mistral's documentation now calls the app **Vibe**, with Le Chat's connectors in **Work**. Custom connectors
are an administrator feature; on Free, Pro and Student plans you are the administrator. From
[Mistral's guide](https://docs.mistral.ai/vibe/work/connectors/mcp-connectors):

1. Open the **Connectors** page, click **+ Add Connector** and switch to the **Custom MCP Connector** tab.
2. Connector name: `minion` (no spaces). Server URL: the MCP server URL. Add a short description.
3. Click **Connect**. Le Chat detects the authentication; with the token in the URL, there is none to set
   up. (It also supports a Bearer token: then use the URL without `?token=…`.)
4. Turn the connector on in a conversation. In **Connectors > My Connectors > Minion > Functions** you can
   pre-approve read-only tools such as `see` and keep the others on manual approval.

### Cursor, VS Code, Claude Code and other clients that send headers

These apps run on your computer, where `minion mcp` (stdio, see [agents.md](agents.md)) is simpler. Use
the remote URL to reach desktops on another machine, or a server that several people share. Clients that
can send headers should send the token as `Authorization: Bearer …` and use the URL without `?token=`.

**Cursor** (`~/.cursor/mcp.json`, or `.cursor/mcp.json` in a project;
[docs](https://cursor.com/docs/mcp)), with the token in the `MINION_TOKEN` environment variable:

```json
{
  "mcpServers": {
    "minion": {
      "url": "https://cedar-quiet-ocean-lamp.trycloudflare.com/mcp",
      "headers": { "Authorization": "Bearer ${env:MINION_TOKEN}" }
    }
  }
}
```

**VS Code** (`.vscode/mcp.json`; [docs](https://code.visualstudio.com/docs/agents/reference/mcp-configuration)).
VS Code asks for the token the first time and stores it securely:

```json
{
  "inputs": [{ "type": "promptString", "id": "minion-token", "description": "Minion token", "password": true }],
  "servers": {
    "minion": {
      "type": "http",
      "url": "https://cedar-quiet-ocean-lamp.trycloudflare.com/mcp",
      "headers": { "Authorization": "Bearer ${input:minion-token}" }
    }
  }
}
```

**Claude Code** ([docs](https://code.claude.com/docs/en/mcp)):

```bash
claude mcp add --transport http minion https://cedar-quiet-ocean-lamp.trycloudflare.com/mcp \
  --header "Authorization: Bearer $MINION_TOKEN"
```

Any other client that supports Streamable HTTP takes the same URL. Add `?compact=1` for the single
`computer` tool, or `?images=0` for text only. The protocol details are in
[http-api.md](http-api.md#remote-mcp-mcp).

## Your own server (VPS or home server)

A quick tunnel is for trying things out: its URL changes every time and it has
[no uptime guarantee](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).
For a permanent setup, run Minion on a machine that stays on. Use Linux with Docker and 2 GB of RAM or more;
each desktop uses 60–100 MB while idle, plus whatever its apps need.

```bash
# as a user in the `docker` group (that group is root-equivalent on the host: use a dedicated user)
pipx install minion-desktop
minion pull browser office                     # download the images before anyone waits for them
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > ~/.minion-token && chmod 600 ~/.minion-token
```

Keep `minion serve` on `127.0.0.1` and put HTTPS in front of it. A systemd unit
(`/etc/systemd/system/minion.service`; change the user, the paths and the domain):

```ini
[Unit]
Description=Minion desktops for AI agents
After=docker.service
Requires=docker.service

[Service]
User=minion
Environment=MINION_ALLOWED_HOSTS=minion.example.com
ExecStart=/bin/sh -c 'exec /home/minion/.local/bin/minion serve --port 4747 --token "$(cat /home/minion/.minion-token)"'
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

`MINION_ALLOWED_HOSTS` lists the public names the server answers to. Without it, Minion refuses any `Host`
header that isn't a loopback name, which is its protection against DNS rebinding.

**With Caddy**, which gets the HTTPS certificate automatically, passes the `Host` header on and doesn't
buffer the SSE responses (`/etc/caddy/Caddyfile`):

```text
minion.example.com {
    reverse_proxy 127.0.0.1:4747
}
```

The connector URL is then `https://minion.example.com/mcp?token=<token>`. With **nginx**, add
`proxy_set_header Host $host;`, `proxy_set_header X-Forwarded-Proto $scheme;`, `proxy_buffering off;` and
`proxy_read_timeout 3600s;` to the location that proxies to `127.0.0.1:4747`.

**With Tailscale**, there is no domain to set up. `tailscale serve 4747` makes the server reachable from
your own devices, for Cursor or VS Code, at `https://<machine>.<tailnet>.ts.net/mcp`. `tailscale funnel 4747`
publishes it on the internet for ChatGPT, Claude and Le Chat. Funnel needs to be allowed in your tailnet's
policy, and TLS ends on your machine:
[Funnel's relays can't decrypt the traffic](https://tailscale.com/docs/features/tailscale-funnel). In both
cases set `MINION_ALLOWED_HOSTS=<machine>.<tailnet>.ts.net`. On a desktop computer,
`minion share --tailscale` does this setup for you.

**`minion serve --host 0.0.0.0`** listens on every network interface. Use it only when the proxy can't reach
127.0.0.1, for example a proxy running in a container or on another machine. Then firewall the port so that
only the proxy can reach it: the token travels in plain HTTP on that hop, and on a non-loopback bind
without `MINION_ALLOWED_HOSTS` any `Host` name is accepted, so the token is the only protection.

## Security

- **The URL is the key.** Whoever has it can create and remove desktops, run any program in them, read their
  screens and files, and watch or take over the live view. That covers every desktop of this computer's
  container engine, including ones you created for other work. Share it only with the chat app, and stop
  sharing when you're done.
- **Your own files stay out of reach.** The HTTP server never reads or writes your files outside one folder,
  and `minion share` closes that folder too: `files` can't upload or download unless you pass `--files`. The
  remote side has no use for it anyway, because the chat app can't see that folder, while an attacker who
  got the URL could read what you dropped there or fill your disk. `files read`/`write` still work, since
  they only touch the desktop.
- **Desktops browse from your network.** Pages they open see your IP address, and they can reach your local
  network (your router, your NAS). Keep that in mind before you share with anyone but yourself.
- **Prompt injection.** Web pages and documents can carry instructions aimed at the model. Keep credentials
  out of desktops and use the hand-off (`view` with a message) for sign-ins. Keep the chat app's approval
  prompts on for tools that change things (`act`, `run`, `script`).
- **Who sees the traffic.** Cloudflare terminates TLS for quick tunnels, so it could see the requests,
  including the token. With Tailscale Funnel or your own server, TLS ends on your machine. Clients that send
  the token in a header keep it out of URLs and logs; Minion's own logs hide it either way.
- **Browser protections.** `/mcp` accepts only the token (`?token=` or `Authorization: Bearer`), never the
  dashboard's cookie. On a loopback address it also refuses web pages: a request whose `Origin` is neither a
  local page nor a known chat app gets 403. Through a tunnel or a proxy, the token decides. Details are in
  [http-api.md](http-api.md#remote-mcp-mcp) and [SECURITY.md](../SECURITY.md).

## Timeouts and limits

- **First desktops download an image** (188–710 MB). Chat apps stop waiting for a tool long before that
  ends: Claude allows [240 seconds per tool call](https://claude.com/docs/connectors/building), and
  developers report that ChatGPT gives up after about a minute. Run `minion pull browser office` (and
  any other profile you want) before you share. In a share, `desktop create` replies "still preparing"
  after 45 seconds (set `MINION_MCP_CREATE_WAIT` to change that), and the model can call it again.
- **Hand-offs** (`view` with a message) wait at most 45 seconds per call in a share. The request stays on
  the human's screen, and the model calls `view` again to keep waiting.
- **Quick tunnels** allow 200 requests at a time and don't stream server-sent events: progress
  notifications arrive together with the result. Minion's keep-alive messages still keep long calls from
  timing out at Cloudflare. A named tunnel, Tailscale or your own server don't have these limits.
- **Screenshots** are images in the tool result. Claude limits results to about 150,000 characters. If a
  chat app struggles with images, use the `?images=0` URL (`minion share --no-images`) and let the model
  read the screen with `see`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| The chat app says it can't reach the server | Is `minion share` still running? The URL changes every run: paste the new one. Check that the URL ends in `/mcp?token=…`. |
| `401` | Wrong or old token. |
| `403 forbidden host` behind your own proxy | Set `MINION_ALLOWED_HOSTS` to your domain, or have the proxy send `Host: 127.0.0.1:4747`. |
| `403` with an `Origin` header | A web client that calls from the browser, on a loopback address: add its origin to `MINION_ALLOWED_ORIGINS` (comma-separated). |
| `minion share` says cloudflared can't reach Minion | Docker can't reach this computer's 127.0.0.1 (seen with some VM-based container engines). Install cloudflared, or use `--bind 0.0.0.0`. |
| Creating a desktop never finishes | The image is downloading: `minion pull <profile>` once, then try again. |
| A tunnel container stayed behind after a crash | `docker rm -f $(docker ps -q --filter label=dev.minion.share=1)` |

Test the endpoint yourself (any MCP client works too, e.g.
`npx @modelcontextprotocol/inspector --cli <URL> --transport http --method tools/list`):

```bash
URL='https://cedar-quiet-ocean-lamp.trycloudflare.com/mcp?token=…'
curl -s "$URL" -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"1"}}}'
```
