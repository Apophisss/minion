# Product Hunt

## Listing

| Field | Text |
|---|---|
| Name | Minion |
| Tagline (60 characters at most) | Give every AI agent its own computer |
| Website | https://apophisss.github.io/minion/ |
| GitHub | https://github.com/apophisss/minion |
| Pricing | Free (open source, MIT) |
| Thumbnail | [packaging/mcpb/icon.png](../../packaging/mcpb/icon.png) (512×512) |

Other taglines, if the first one is taken or feels too broad:

- A disposable Linux computer for your AI agent
- Linux desktops that AI agents read as text and control

**Description** (260 characters at most; this one has 244):

> Open-source Linux desktops for AI agents, in Docker on your machine. Agents read the screen as text with stable
> @ids and use any app: browser, LibreOffice, IDE, terminal, Wine. Ready in ~1.5 s, ~60 MB idle. One click in
> Claude, VS Code, Cursor.

**Topics** (pick from Product Hunt's list when you submit): Open Source, Developer Tools, Artificial Intelligence.
Alternatives: GitHub, Productivity.

## Gallery

Start the gallery with the demo video: Product Hunt takes a YouTube link, so upload [demo.mp4](../assets/demo.mp4)
first ([youtube.md](youtube.md)). Then the images, in this order. Product Hunt crops gallery images to its own frame,
so check each one in the preview before you publish.

| # | Image | Caption |
|---|---|---|
| 1 | [hero.png](../assets/hero.png) | Instant Linux desktops for AI agents: office, dev, research, browser, data and Windows apps. |
| 2 | [social-preview.png](../assets/social-preview.png) | Agents read the screen as text. Every control gets a stable @id the agent can click. |
| 3 | [demo.gif](../assets/demo.gif) | An agent on a research desktop, recorded by Minion's built-in flight recorder. |
| 4 | [marks.png](../assets/marks.png) | When pixels matter, a screenshot can label every clickable element with its @id. |
| 5 | [live-view.png](../assets/live-view.png) | Watch any desktop live, click Take control, or let the agent hand off for a sign-in. |
| 6 | [office.png](../assets/office.png) | Office desktops save Microsoft formats by default and type exactly what the agent sends. |
| 7 | [dashboard.png](../assets/dashboard.png) | One dashboard with live thumbnails of every desktop (`minion serve`). |


## Maker's first comment

Post it as soon as the launch is live. Replace `[Name]`.

```text
Hi Product Hunt! I'm [Name], and I made Minion.

Agents that use a computer are useful, but I didn't want one clicking around on mine. Minion gives each agent its own disposable Linux desktop: a small container on your machine with a browser, LibreOffice, an IDE, a terminal, or Windows programs through Wine.

What makes it work for agents:

• The screen as text. Minion reads the accessibility tree (with OCR as a fallback) and gives the agent a short list of controls with stable @ids, so it clicks @12 instead of guessing coordinates.

• Cheap to run. A desktop is ready in about 1.5 s and uses about 60 MB when idle. After typing a sentence, the agent gets a ~60-token diff instead of re-reading the screen (~900 tokens as text, ~1,365 as a screenshot).

• Honest actions. Every action waits for the screen to settle and reports what changed. A miss fails with the closest candidates instead of clicking the wrong thing.

• You stay in control. Watch live, take over with one click, or let the agent hand off for a sign-in and wait for you.

Setup is one click in Claude Desktop, VS Code, Cursor, LM Studio, Goose or Kiro, a plugin for Claude Code, or one line that connects every AI app on your computer. ChatGPT and Claude.ai on the web connect through "minion share".

It's free and open source (MIT). I'd love to hear which apps you'd want your agent to use, and where setup took more than one step for you.
```

## On the day

- Reply to every comment. Answers to the usual questions are in [faq-responses.md](faq-responses.md).
- Share the launch page with people who would use Minion and ask for their honest feedback, not for upvotes.
