# Security

## Reporting a vulnerability

Please report vulnerabilities privately through
[GitHub Security Advisories](https://github.com/apophisss/minion/security/advisories/new), not in public issues.
We aim to answer within a few days.

## Threat model

Minion gives AI agents a computer, so the agent and everything it reads must be treated as untrusted.

**What isolates a desktop (Docker/Podman backend)**

- Each desktop is its own unprivileged container (no `--privileged`, default seccomp and capabilities), with
  no host mounts unless you add them (`-v`).
- Nothing listens on the network. The host reaches the in-desktop agent through `docker exec`.
- `--offline` removes network access. `--memory` and `--cpus` cap resources (profiles set memory limits by default).
- Inside, the `agent` user has passwordless `sudo`, because agents need to install tools. This is root *inside the
  container*, not on your machine.
- Chromium in the `dev` profile runs with `--no-sandbox`, and the container is its sandbox.

**What the local backend does not do**

`MINION_BACKEND=local` runs desktops as your own user on your own machine. That is fine for CI and trusted
automation, but it is not isolation.

**The HTTP server**

`minion serve` binds to `127.0.0.1` and requires a random token by default. `--host 0.0.0.0` exposes desktops to
your network: anyone with the token controls them. Never use `--no-auth` on a shared network. It also refuses
cross-site requests (CSRF) and, on loopback binds, foreign `Host` names (DNS rebinding).

**Remote MCP and `minion share`**

`minion serve` also answers MCP at `/mcp` (Streamable HTTP), with the same token as a `Bearer` header or
`?token=` in the URL. `minion share` publishes that endpoint over a Cloudflare quick tunnel, for web chat apps such as
ChatGPT and Claude.ai. Anyone with a share URL controls every desktop on the computer until you press Ctrl+C. Each
share has its own fresh 256-bit token that stops working with it, `files` upload/download of your computer's files
is off unless you pass `--files`, and requests are logged in the terminal. See [docs/remote.md](docs/remote.md).

**Files on your machine**

The `files` tool's `upload` and `download` read and write files on the machine that runs Minion, so they stay
inside one folder: a prompt-injected agent must not be able to copy `~/.ssh` into an internet-connected desktop.
- **MCP server and Python `Toolkit`:** the working directory, which for coding agents is usually the project. When
  the working directory is `/` or your home folder (GUI apps start servers there), it is `~/Minion` instead.
- **HTTP (`minion serve`):** `files/` in Minion's data directory, e.g. `~/.local/share/minion/files`.
- **Override:** set `MINION_FILES_ROOT` (or `Toolkit(files_root=...)`); `MINION_FILES_ROOT=/` allows any path.

Downloads never overwrite an existing file unless the agent passes `overwrite=true`. The CLI (`minion cp`) is
your own command, so it is not confined.

**Prompt injection**

Web pages, documents, window titles and the clipboard can all carry instructions aimed at the agent. Keep
credentials out of desktops, prefer human hand-off (`view` with a message) for sign-ins and payments, and gate
consequential actions (the Anthropic SDK driver takes a `confirm` callable for exactly this).

## Supply chain

Images are built in CI from `debian:trixie-slim` and the recipes in this repository, then published to GHCR.
You can always build them yourself: `MINION_PULL=never minion up office`, or `minion build --all`.
