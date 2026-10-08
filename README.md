# Minion

**Your own always-on AI agent - open source, self-hosted, self-improving.**
One chat that drives the best open-source agent harnesses (OpenClaw, Hermes, opencode, Goose, Aider, ...),
any MCP server, its own computer in Docker, and its own code. Think Meta Muse / OpenAI Dots - but yours.

> **Status: pre-alpha, under construction.** The architecture, foundation and build plan are in place;
> the components are being implemented. Nothing below is usable yet. See [docs/plan](docs/plan/README.md)
> and the [roadmap](docs/ROADMAP.md).

## What it will do

- **One conversation for everything** - web UI with voice, phone (PWA), Telegram, CLI, an OpenAI-compatible
  API (so Open WebUI and other chat apps work), and WhatsApp/Slack/Discord through OpenClaw.
- **Uses existing open-source harnesses** instead of reinventing them, and upgrades them automatically.
- **Every MCP server** - add any server at runtime (stdio, Docker, HTTP), search and install from the
  official MCP registry, and share all tools with every harness through one MCP gateway.
- **Builds what it lacks** - writes new tools and MCP servers itself, tests them, hot-loads them, and
  proposes new capabilities proactively.
- **Its own computer** - a built-in Linux desktop in Docker (browser, terminal, apps) that it drives with
  Claude computer use while you watch live.
- **Keeps working when you leave** - background tasks, scheduled automations, approval gates for risky
  actions.
- **Improves itself safely** - changes its own code in git worktrees with tests, health-checked restarts
  and automatic rollback; updates itself when this repo updates; contributes new capabilities back to the
  repo so every installation gets them.
- **Budget-aware** - tracks token spend and paces autonomous work to your monthly budget.
- **Easy** - planned one-line install: `curl -fsSL https://raw.githubusercontent.com/apophisss/minion/main/install.sh | bash`.

## How it fits together

```
 Web / voice / Telegram / OpenAI API ──► Minion core (FastAPI)
                                          ├─ Brain (Claude) ── tools ──┬─ MCP hub ──► any MCP server
                                          │                            ├─ harnesses: OpenClaw, Hermes, opencode, ...
                                          │                            └─ desktop (Xvfb + noVNC, computer use)
                                          ├─ MCP gateway /mcp ◄── harnesses use every tool
                                          └─ evolution: self-modify · self-update · share · automations
 supervisor (from the image) runs the core from a git checkout and rolls back bad changes
```

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Contributing / continuing development
Start with [docs/HANDOFF.md](docs/HANDOFF.md) and [docs/plan/README.md](docs/plan/README.md). Each unit in
`docs/plan/units/` can be implemented independently against the contracts.

---

## בעברית

**Minion** הוא סוכן AI אישי שרץ אצלך על השרת, בקוד פתוח, ומשפר את עצמו - חלופה פתוחה ל-Muse של Meta ול-Dots של OpenAI.
צ'אט אחד (ווב עם קול, טלגרם, CLI, ו-API תואם OpenAI) שמפעיל את סוכני הקוד הפתוח הטובים ביותר (OpenClaw, Hermes ועוד),
כל שרת MCP, מחשב משלו בתוך Docker, וגם את הקוד של עצמו - עם בדיקות, חזרה אוטומטית לגרסה תקינה, עדכון עצמי מה-repo,
ושיתוף יכולות חדשות חזרה ל-repo כדי שכל ההתקנות יקבלו אותן.

**מצב נוכחי:** שלב מוקדם - הארכיטקטורה, התשתית ותוכנית הבנייה מוכנות, והרכיבים בבנייה.
המשך פיתוח: [docs/HANDOFF.md](docs/HANDOFF.md) · תוכנית: [docs/plan](docs/plan/README.md) · מפת דרכים: [docs/ROADMAP.md](docs/ROADMAP.md).

## License
MIT (to be confirmed before the first release).
