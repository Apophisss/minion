# Where to list Minion

Every directory, catalog and awesome list worth being in, how each one takes submissions, and the text to paste.
Checked on 2026-10-15. Directories change their rules often, so read each one's own instructions again before you
submit.

**First:**

1. Release 1.0.0 (tag `v1.0.0`). The release workflow publishes PyPI, npm, the GitHub release with `minion.mcpb`,
   and the official MCP Registry. Most directories show `uvx minion-desktop mcp`, so wait until that works.
2. Check that the registry has Minion:
   `curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.Apophisss/minion"`.
3. Some lists accept only what a person writes and files (said below). There, use the texts as notes and write
   your own.

## The texts

| | |
|---|---|
| Name | Minion |
| Repository | https://github.com/apophisss/minion |
| Registry name | `io.github.Apophisss/minion` |
| License | MIT |
| Install | `uvx minion-desktop mcp`, or `npx -y minion-desktop mcp` (needs uv or pipx). Claude Code: `claude plugin marketplace add apophisss/minion && claude plugin install minion@minion`. Claude Desktop: [`minion.mcpb`](https://github.com/apophisss/minion/releases/latest/download/minion.mcpb) |
| Needs | Docker, OrbStack or Podman. uv (or pipx), except for the Claude Desktop extension |
| Logo | [`packaging/logo-400.png`](../../packaging/logo-400.png) (400×400) or [`packaging/mcpb/icon.png`](../../packaging/mcpb/icon.png) (512×512). URL, once on `main`: `https://raw.githubusercontent.com/apophisss/minion/main/packaging/logo-400.png` |
| Tags | computer use, desktop automation, browser automation, Linux, Docker, MCP, AI agents |

**One line** (94 characters; the registry's description):

```text
Featherweight Linux desktops for AI agents: read the screen as text, click, type, run any app.
```

**One sentence:**

```text
Gives AI agents featherweight Linux desktops in local Docker containers (browser, office, dev, research, data, Windows apps through Wine) that they read as text and control with batched clicks and typing.
```

**A paragraph:**

```text
Minion gives any AI agent its own computer: featherweight Linux desktops in local Docker containers, with browser, office (LibreOffice), dev, research, data and Windows-apps (Wine) profiles. Agents read the screen as text from the accessibility tree and OCR, with stable @ids to click, act in batches, run Python inside the desktop for long GUI loops, and copy files in and out. People can watch any desktop live in the browser, take over, or hand a sign-in back. It works over MCP (stdio or remote), function calling for OpenAI, Anthropic and Gemini, HTTP, a CLI with an Agent Skill, and Python and TypeScript SDKs. MIT licensed, with no Python dependencies.
```

## At a glance

| Where | How | When | Fit |
|---|---|---|---|
| [Official MCP Registry](#official-mcp-registry) | Automatic: `release.yml` | At the release | Done by CI |
| [GitHub MCP Registry](#github-mcp-registry) | Ask GitHub to onboard it | After the registry has it | Curated by GitHub |
| [Glama](#glama) | Add and claim the server; `glama.json` | After the release | Good, and awesome-mcp-servers needs it |
| [awesome-mcp-servers](#awesome-mcp-servers-punkpeye) | Pull request | When Glama's checks pass | The main MCP list |
| [PulseMCP](#pulsemcp) | Nothing: it reads the registry | — | Submissions are paused |
| [mcp.so](#mcpso) | Web form | After the release | Good |
| [MCP Market](#mcp-market) | Web form | After the release | Good, slow when free |
| [mcpservers.org](#mcpserversorg) | Web form | After the release | Good |
| [LobeHub](#lobehub) | Web button or the `lhm` CLI | After the release | Good |
| [cursor.directory](#cursordirectory) | Web form, manual mode | After the release | Good |
| [Cline MCP Marketplace](#cline-mcp-marketplace) | Pull request, or issue with a 400×400 logo | After the release | Good, slow |
| [Smithery](#smithery) | MCPB bundle | When Smithery takes uv bundles | Blocked |
| [Claude directory](#claude-directory-anthropic) | Plugin bundle in the developer portal | After the plugin is ready | Needs work |
| [Docker MCP Catalog](#docker-mcp-catalog) | Pull request | — | Poor fit |
| [Other MCP lists](#other-mcp-lists) | Pull request or issue form | After the release | Good |
| [AI-agent lists](#ai-agent-lists) | Issue form or pull request | After the release, some later | Mixed |
| [Claude lists](#claude-lists) | Issue form (by a person) or pull request | From 2026-10-22, some later | Mixed |
| [Computer-use lists](#computer-use-lists) | Pull request | After the release | Good, slow |
| [Not a fit (yet)](#not-a-fit-yet) | — | — | awesome-llm-apps, awesome-python, awesome-selfhosted, awesome-docker |

## Official MCP Registry

- **Where:** https://registry.modelcontextprotocol.io (API: `/v0.1/servers?search=...`).
- **How:** automatic. The `mcp-registry` job of `.github/workflows/release.yml` waits for the PyPI and npm jobs,
  adds the `.mcpb` from the GitHub release with its SHA-256, and publishes `server.json` with GitHub OIDC. The
  registry checks ownership of each package: the `mcp-name:` comment in `README.md` (PyPI's description) and
  `mcpName` in `clients/typescript/package.json` (npm).
- **The name** has a capital A, like the GitHub account `Apophisss`: the registry lets an account publish
  `io.github.<account>/*` with the account's exact casing
  ([registry#689](https://github.com/modelcontextprotocol/registry/issues/689)). The release workflow checks this
  before it publishes anything.
- **Then:** Glama imports it, PulseMCP will pick it up, GitHub's registry syncs new versions once it has onboarded
  the server, and several registry browsers show it.

## GitHub MCP Registry

- **Where:** https://github.com/mcp, GitHub's curated catalog of MCP servers.
- **How:** curated. GitHub onboards new servers by hand, and after that, new versions sync from the official
  registry. Ask in the onboarding thread,
  [github/github-mcp-server#1257](https://github.com/github/github-mcp-server/discussions/1257).
- **Prerequisites:** Minion is in the official registry.
- **Paste:**

  ```text
  Please consider onboarding Minion to the GitHub MCP Registry.
  - Registry name: io.github.Apophisss/minion, version 1.0.0
  - Packages: PyPI minion-desktop (uvx, stdio), npm minion-desktop (npx, stdio), MCPB (GitHub release)
  - Repository: https://github.com/apophisss/minion (MIT)
  - What it does: Featherweight Linux desktops for AI agents: read the screen as text, click, type, run any app.
  - curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.Apophisss/minion"
  ```

## Glama

- **Where:** https://glama.ai/mcp/servers, the web directory that awesome-mcp-servers is synced with.
- **How:** Glama imports everything in the official registry. To own the listing, select **Add MCP Server** on the
  servers page with the repository URL, sign in with GitHub (Glama checks that you can push to the repository),
  and claim it. The repository's `glama.json` names the maintainers (`Apophisss`). Glama requires it only for
  repositories that belong to an organization, but it makes the claim explicit. After changing `glama.json`, claim
  the server again.
- **Build:** Glama builds each server from a Dockerfile, runs it and asks for its tools. A server whose build fails
  keeps its page but doesn't appear in search. Minion answers `initialize` and `tools/list` without Docker (checked
  in a `python:3.13-slim` container). If Glama asks for the build in the listing's admin, use:

  ```dockerfile
  FROM python:3.13-slim
  RUN pip install --no-cache-dir minion-desktop==1.0.0
  CMD ["minion", "mcp"]
  ```

- **Then:** the listing shows a score badge. awesome-mcp-servers wants it in the entry (below).

## awesome-mcp-servers (punkpeye)

- **Where:** https://github.com/punkpeye/awesome-mcp-servers, the largest MCP list (about 96,000 stars).
- **How:** a pull request that adds one line to `README.md`, under `### 🖥️ OS Automation` (`#os-automation`).
  CONTRIBUTING.md asks for alphabetical order within the section.
- **Prerequisites:** the server is on Glama and passes its checks. A bot labels pull requests without a Glama
  score badge, and almost every merged entry has one. The link text must be `owner/repo`, and the entry needs at
  least one of the list's emojis: 🐍 Python, 🏠 local service, 🍎 🪟 🐧 operating systems.
- **Paste** (copy the badge's path from the Glama listing, which may spell the owner `Apophisss`):

  ```markdown
  - [apophisss/minion](https://github.com/apophisss/minion) [![apophisss/minion MCP server](https://glama.ai/mcp/servers/apophisss/minion/badges/score.svg)](https://glama.ai/mcp/servers/apophisss/minion) 🐍 🏠 🍎 🪟 🐧 - Featherweight Linux desktops for AI agents in local Docker containers (browser, office, dev, research, data, Windows apps through Wine): read the screen as text with stable @ids, act in batches, run code inside, and let a person watch live and take over.
  ```

## PulseMCP

- **Where:** https://www.pulsemcp.com/servers.
- **How:** nothing to do. Submissions are paused (the notice is dated 2026-09-03), and PulseMCP says it will pick up
  servers from the official registry once it resumes. If the form at https://www.pulsemcp.com/submit opens again,
  submit the repository URL.

## mcp.so

- **Where:** https://mcp.so/submit (sign in first). Type: **MCP Server**.
- **How:** the form takes the repository URL and a name. The free plan queues it for review; a paid plan ($39)
  publishes at once with a badge. Afterwards, claim the listing through GitHub.
- **Paste:** Name `Minion`, Repository URL `https://github.com/apophisss/minion`.

## MCP Market

- **Where:** https://mcpmarket.com/submit.
- **How:** the form takes the GitHub repository. Free submissions take four to six weeks; a paid one ($29) goes
  live within a day.
- **Paste:** `https://github.com/apophisss/minion`.

## mcpservers.org

- **Where:** https://mcpservers.org/submit. Its list, wong2/awesome-mcp-servers, takes no pull requests.
- **How:** the form, reviewed within two weeks (or within a day for $39).
- **Paste:** Server Name `Minion` · Category `Development` · Short Description: the one line ·
  Repository `https://github.com/apophisss/minion` · Official MCP Registry Name `io.github.Apophisss/minion` ·
  Remote connections: no · Contact email: yours.

## LobeHub

- **Where:** https://lobehub.com/mcp.
- **How:** **Submit MCP** on that page. As the repository's owner you can also publish with LobeHub's `lhm` CLI,
  which lists it at once; https://lobehub.com/publish-mcp/skill.md has the steps. The start command is
  `uvx minion-desktop mcp`.
- **Paste:** the repository URL, the one line, and the paragraph.

## cursor.directory

- **Where:** https://cursor.directory/plugins/new?type=mcp_server (sign in with GitHub or Google).
- **How:** use **manual** mode. The automatic mode looks for a plugin manifest or an `.mcp.json` at the
  repository's root, and Minion keeps its Claude Code plugin in `plugins/minion`.
- **Paste:** logo `packaging/logo-400.png`, name `Minion`, the one sentence, repository and homepage
  `https://github.com/apophisss/minion`, and one MCP server named `minion`:

  ```json
  { "command": "uvx", "args": ["minion-desktop", "mcp"] }
  ```

## Cline MCP Marketplace

- **Where:** Cline takes entries in two places. The newer one is the repository
  [cline/marketplace](https://github.com/cline/marketplace) (since June 2026), published as
  `https://cline.github.io/marketplace/catalog.json`. The older one is an issue in
  [cline/mcp-marketplace](https://github.com/cline/mcp-marketplace), with more than 2,600 open issues and no change
  to the repository since June 2025. Which one each Cline version reads isn't documented, so use both.
- **Prerequisites:** check that Cline can install and use Minion from the README alone: the issue form asks you
  to confirm it.
- **New catalog:** a pull request that adds `registry/mcps/minion/entry.json` and `registry/mcps/minion/icon.png`
  (a copy of `packaging/logo-400.png`). Run `npm run validate` in that repository first.

  ```json
  {
    "$schema": "../../../schemas/mcp.schema.json",
    "id": "minion",
    "type": "mcp",
    "name": "Minion",
    "tagline": "Featherweight Linux desktops that Cline reads as text and controls",
    "description": "Minion gives Cline its own Linux desktops in local Docker containers: a browser, LibreOffice, developer and data tools, or Windows programs through Wine. Cline reads the screen as text with stable @ids, clicks and types in batches, runs commands and Python inside the desktop, and copies files in and out. You can watch any desktop live in your browser and take over. Needs Docker, OrbStack or Podman, and uv.",
    "author": { "name": "Minion contributors", "url": "https://github.com/apophisss/minion" },
    "homepage": "https://github.com/apophisss/minion",
    "repo": "https://github.com/apophisss/minion",
    "icon": "./icon.png",
    "tags": ["software", "productivity"],
    "license": "MIT",
    "verified": false,
    "featured": false,
    "install": { "args": ["minion", "--", "uvx", "minion-desktop", "mcp"] }
  }
  ```

- **Older route:** the issue form **MCP Server Submission** at
  https://github.com/cline/mcp-marketplace/issues/new?template=mcp-server-submission.yml. GitHub Repository URL:
  `https://github.com/apophisss/minion`. Logo Image: drag in `packaging/logo-400.png`. Tick both testing boxes
  once they're true. Additional Information:

  ```text
  Minion gives Cline its own Linux desktops (browser, office, dev, data, Windows apps through Wine) that it reads as text and controls. Install: uvx minion-desktop mcp. Needs Docker, OrbStack or Podman, and uv. MIT licensed.
  ```

## Smithery

- **Where:** https://smithery.ai.
- **How it works now:** `smithery mcp publish` takes a public MCP URL (a server you host) or an MCPB bundle
  (`smithery mcp publish ./minion.mcpb -n <namespace>/minion`). Its docs no longer mention `smithery.yaml`, so the
  repository has none, and a local command such as `uvx minion-desktop mcp` can't be listed by itself.
- **Why not yet:** Smithery accepts bundles whose runtime is `node`, `python`, `binary` or `bun`. `minion.mcpb` is a
  `uv` bundle (MCPB manifest 0.4), so it would be refused. Wait until Smithery takes `uv` bundles. A separate
  bundle of type `python` would work, since Minion has no dependencies, but users would then need their own
  Python 3.11+.
- **Prerequisites:** a Smithery account and namespace.

## Claude directory (Anthropic)

- **Where:** https://claude.ai/directory/manage, the developer portal (a Pro, Max, Team or Enterprise account, with
  GitHub connected and push access to the repository).
- **Extensions:** the directory no longer accepts MCP Bundles, and its desktop extension listings are deprecated.
  People still install `minion.mcpb` by hand ([install.md](../install.md#claude-desktop)).
- **How:** submit the Claude Code plugin in `plugins/minion` as a **Plugin bundle**. Local MCP servers in plugins
  run in Claude Code, and in Cowork when the session runs on the user's computer, but not in Claude Desktop's chat.
- **Prerequisites** (from the
  [pre-submission checklist](https://claude.com/docs/plugins/pre-submission-checklist) and the
  [directory policy](https://support.claude.com/en/articles/13145358-anthropic-software-directory-policy)):
  - a README of at least 40 words in `plugins/minion` (none yet: this blocks the submission);
  - the launcher pinned to an exact version, `uvx minion-desktop==1.0.0 mcp`, and moved along with each release
    (unpinned blocks; pinned is held for a reviewer);
  - `title`, `readOnlyHint` and `destructiveHint` on every tool. `open`, `view` and the compact `computer` tool
    have only a title, and the others have one of the two hints.
- **Paste:** repository `https://github.com/apophisss/minion`, plugin path `plugins/minion`; the plugin's README
  becomes the listing's description.

## Docker MCP Catalog

- **Where:** https://hub.docker.com/mcp, from pull requests to
  [docker/mcp-registry](https://github.com/docker/mcp-registry) (`servers/<name>/server.yaml`).
- **How it works:** Docker builds an image from a Dockerfile in the repository and runs the server in a container
  (1 CPU, 2 GB, no access to the host's files unless the user grants a folder). Docker reviews every pull request.
- **Why it doesn't fit:** Minion's MCP server starts and drives desktop containers through the host's Docker
  daemon. Inside the Toolkit's container it would need the host's Docker socket, which gives full control of the
  host and undoes the catalog's isolation. Its `files` tool would see the container's disk instead of the user's,
  and the live view that it serves on localhost wouldn't reach the user's browser. Leave it out.

## Other MCP lists

- **[TensorBlock/awesome-mcp-servers](https://github.com/TensorBlock/awesome-mcp-servers)** (feeds tensorblock.co/mcp):
  a pull request that adds a line to `docs/operating-system--command-line.md`, or its
  [issue form](https://github.com/TensorBlock/awesome-mcp-servers/issues/new?template=add-mcp-server.yml):

  ```markdown
  - [apophisss/minion](https://github.com/apophisss/minion): Gives AI agents featherweight Linux desktops in local Docker containers (browser, office, dev, research, data, Windows apps through Wine) that they read as text and control with batched clicks and typing; a person can watch live and take over. Install: `uvx minion-desktop mcp`.
  ```

- **[MobinX/awesome-mcp-list](https://github.com/MobinX/awesome-mcp-list):** a pull request that adds exactly one
  line under `### 🌐 Browser Control` (it holds the desktop-control servers too), titled
  `Add apophisss/minion to Browser Control`, changing only `README.md`. Note the three spaces after the dash:

  ```markdown
  -   **[apophisss/minion](https://github.com/apophisss/minion)** [![GitHub stars](https://img.shields.io/github/stars/apophisss/minion?style=social)](https://github.com/apophisss/minion): Gives MCP agents featherweight Linux desktops in local Docker containers that they read as text and control with batched clicks and typing.
  ```

- **[yzfly/Awesome-MCP-ZH](https://github.com/yzfly/Awesome-MCP-ZH)** (the largest Chinese list): a pull request
  that adds a row to `### 🖱️ 桌面与 GUI 自动化`, titled `新增 Minion 到 桌面与 GUI 自动化`:

  ```markdown
  | [Minion](https://github.com/apophisss/minion) | 为 AI Agent 提供轻量级 Linux 桌面（本地 Docker 容器：浏览器、LibreOffice 办公、开发、研究、数据，以及通过 Wine 运行 Windows 程序）：以文本方式读取屏幕（无障碍树 + OCR，元素 @id 稳定），批量点击与输入，可在桌面内运行代码，人类可实时观看并接管。 | 社区实现, Python 开发 🐍, 本地运行 🏠, 跨平台 🍎🪟🐧, MIT, `uvx minion-desktop mcp`。 |
  ```

- **No longer taking entries:** appcypher/awesome-mcp-servers is archived, and modelcontextprotocol/servers
  retired its list of third-party servers in favor of the registry.

## AI-agent lists

- **[slavakurilyak/awesome-ai-agents](https://github.com/slavakurilyak/awesome-ai-agents):** the
  [project submission form](https://github.com/slavakurilyak/awesome-ai-agents/issues/new?template=project-submission.yml).
  No minimum stars, but it wants a recent substantive commit. Project name `Minion`; repository
  `https://github.com/apophisss/minion`; suggested category `Operating System (OS)`; a link to a recent commit;
  What does it do: the one sentence.
- **[Jenqyang/Awesome-AI-Agents](https://github.com/Jenqyang/Awesome-AI-Agents):** a pull request with one entry at
  the end of `### Tools` (under Applications). Neutral wording, no "best" or "first":

  ```markdown
  - [Minion](https://github.com/apophisss/minion) - Featherweight Linux desktops in local Docker containers that AI agents read as text (accessibility tree and OCR with stable ids) and control with batched clicks and typing, with live human takeover; MCP, function calling, HTTP and CLI. MIT. ![GitHub Repo stars](https://img.shields.io/github/stars/apophisss/minion?style=social)
  ```

- **[kyrolabs/awesome-agents](https://github.com/kyrolabs/awesome-agents): later.** It closes pull requests for
  brand-new repositories without traction. When Minion has some, add this at the bottom of `## Automation`:

  ```markdown
  - [Minion](https://github.com/apophisss/minion): Featherweight Linux desktops in local Docker containers that AI agents read as text and control with batched clicks and typing, through MCP, function calling, HTTP or a CLI. ![GitHub Repo stars](https://img.shields.io/github/stars/apophisss/minion?style=social)
  ```

- **[e2b-dev/awesome-ai-agents](https://github.com/e2b-dev/awesome-ai-agents): skip.** It lists AI assistants and
  agents, sends SDKs and tools to its much smaller awesome-ai-sdks list, and has merged almost nothing since 2024.

## Claude lists

- **[hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code): from 2026-10-22.** It
  takes a repository 14 days after its first commit (2026-10-08), or with 100 stars. Only the web
  [issue form](https://github.com/hesreallyhim/awesome-claude-code/issues/new?template=recommend-resource.yml),
  filled in by a person: no pull requests, no `gh` CLI, one recommendation at a time, a description rather than a
  pitch, no emojis. A required box says the resource is specific to Claude Code, so lead with the plugin and the
  skill. Write it yourself; for reference: Display Name `Minion`; Category
  `Providers, Runtime & Integration Infrastructure`; Link `https://github.com/apophisss/minion`; Author
  `apophisss`, `https://github.com/apophisss`; Description (10–500 characters) along the lines of "A Claude Code
  plugin, Agent Skill and local MCP server that give Claude Linux desktops in Docker containers. Claude reads each
  screen as text with stable element ids, acts in batches and runs code inside; a person can watch and take over."
- **Agent Skill lists** (Minion's skill is `minion/skill/SKILL.md`, installed with `minion skill --install`):
  - [BehiSecc/awesome-claude-skills](https://github.com/BehiSecc/awesome-claude-skills): a pull request, under
    `## 🛠 Development & Code Tools`:

    ```markdown
    - [minion](https://github.com/apophisss/minion/tree/main/minion/skill) - Operate real Linux desktops (Firefox, LibreOffice, IDEs, Windows programs through Wine) with the `minion` CLI: read the screen as text, click and type in batches.
    ```

  - [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills): a pull request titled
    `Add Minion skill`, in alphabetical order under `### Development & Code Tools`. Its description says what
    problem the skill solves, who uses it, and gives an example. It has a large backlog:

    ```markdown
    - [Minion](https://github.com/apophisss/minion) - Operates real Linux desktops in Docker (Firefox, LibreOffice, IDEs, Windows programs through Wine) with the `minion` CLI: reads the screen as text, clicks and types in batches, and runs code inside. *By [@apophisss](https://github.com/apophisss)*
    ```

  - [VoltAgent/awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills): later. It refuses brand-new
    skills. Then: a pull request titled `Add skill: apophisss/minion` with a description of 10 words or fewer:
    `- **[apophisss/minion](https://github.com/apophisss/minion/tree/main/minion/skill)** - Operate real Linux desktops: browser, office, IDEs, Wine apps`.
  - [travisvn/awesome-claude-skills](https://github.com/travisvn/awesome-claude-skills): later. It needs 10 stars
    and closes pull requests written with AI help.
- **Plugin lists** (Minion's Claude Code plugin is `plugins/minion`):
  - [ccplugins/awesome-claude-code-plugins](https://github.com/ccplugins/awesome-claude-code-plugins), under
    `### MCP Servers`:

    ```markdown
    - [Minion](https://github.com/apophisss/minion) — Claude Code plugin and local MCP server that give Claude featherweight Linux desktops (browser, office, dev, Windows apps via Wine) it reads as text and controls. Install: `claude plugin marketplace add apophisss/minion && claude plugin install minion@minion`
    ```

  - [composio-community/awesome-claude-plugins](https://github.com/composio-community/awesome-claude-plugins), under
    `### Integrations`:

    ```markdown
    - [minion](https://github.com/apophisss/minion) - Claude Code plugin with MCP tools and a skill that give Claude real Linux desktops (office, browser, dev, Windows apps via Wine) to read as text and control.
    ```

- **[webfuse-com/awesome-claude](https://github.com/webfuse-com/awesome-claude): skip for now.** Its MCP section
  holds official resources, and it rarely merges.

## Computer-use lists

- **[trycua/acu](https://github.com/trycua/acu)** (Awesome Computer Use): the right section is Projects → Open
  Source → `### Environment & Sandbox`, but the list hasn't merged anything since May 2025. A pull request costs
  little:

  ```markdown
  - [Minion](https://github.com/apophisss/minion)
    - Featherweight Linux desktops in Docker for any agent
    - Screen read as text (accessibility tree + OCR), batched actions, live human takeover
  ```

- **[ranpox/awesome-computer-use](https://github.com/ranpox/awesome-computer-use):** a pull request under
  `## Projects`. It merges in batches:

  ```markdown
  - [Minion](https://github.com/apophisss/minion) - Featherweight Linux desktops in Docker that AI agents read as text (accessibility tree + OCR) and control with batched clicks and typing, via MCP, function calling, HTTP or CLI
  ```

## Not a fit (yet)

- **[Shubhamsaboo/awesome-llm-apps](https://github.com/Shubhamsaboo/awesome-llm-apps):** it hosts runnable apps in
  its own repository and closes pull requests that only add a link. The way in would be a self-contained demo app
  built on Minion.
- **[vinta/awesome-python](https://github.com/vinta/awesome-python):** a shortlist of stable, established projects
  (at least a month old, ranked by PyPI downloads) with no computer-use category.
- **[awesome-selfhosted](https://github.com/awesome-selfhosted/awesome-selfhosted):** for self-hosted network
  services whose first release is more than four months old, and it bans machine-generated contributions.
- **[veggiemonk/awesome-docker](https://github.com/veggiemonk/awesome-docker):** it rejects projects that would
  exist without Docker. Minion can run desktops without it (the `local` backend), so try later, if at all, under
  `### Wrappers`.
