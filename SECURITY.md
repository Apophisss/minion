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
your network: anyone with the token controls them. Never use `--no-auth` on a shared network.

**Prompt injection**

Web pages, documents, window titles and the clipboard can all carry instructions aimed at the agent. Keep
credentials out of desktops, prefer human hand-off (`view` with a message) for sign-ins and payments, and gate
consequential actions (the Anthropic SDK driver takes a `confirm` callable for exactly this).

## Supply chain

Images are built in CI from `debian:trixie-slim` and the recipes in this repository, then published to GHCR.
You can always build them yourself: `MINION_PULL=never minion up office`, or `minion build --all`.
