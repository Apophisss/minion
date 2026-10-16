# X thread

Nine posts. Each one fits in 280 characters (X counts every link as 23). Attach the image named under a post, with
the alt text given.

## 1/9

```text
An AI agent that operates a computer shouldn't operate yours.

Minion gives every agent its own disposable Linux desktop: a small container on your machine. Agents read the screen as text, click, type and use any app.

Open source, MIT. 🧵
```

Video: [demo.mp4](../assets/demo.mp4) (upload the file: X plays it in the feed, muted, and its captions work without
sound). Or the image [hero.png](../assets/hero.png), with the alt text *Minion: instant desktops for AI agents.
Firefox, LibreOffice Writer and an IDE running on Minion desktops.*

## 2/9

```text
How agents see: "see" turns any window into a short list of controls with stable @ids, taken from the accessibility tree (OCR as a fallback):

@12 button "Save" (210,62)

The agent clicks @12. No coordinate guessing. Spreadsheets come out as A1: value.
```

Image: [social-preview.png](../assets/social-preview.png). Alt text: *A LibreOffice Writer window next to the same
screen as text, with an @id for each control.*

## 3/9

```text
Built to save tokens:

1280×800 screenshot: ~1,365
see of a LibreOffice window: ~920
see(changes=true) after typing a sentence: ~80
Tool definitions: ~3,300, or ~450 in compact mode

Code mode runs a 50-step GUI loop in one call.
```

## 4/9

```text
Featherweight: one container per desktop (Xvfb, a minimal window manager, a small agent). No VNC, no desktop environment.

Ready in ~1.5 s. 54–105 MB idle. Idle desktops freeze to 0% CPU and wake in ~0.2 s.

Measured on a 2-vCPU VM.
```

## 5/9

```text
Beyond the browser: LibreOffice, IDEs, terminals, file dialogs, installers, and Windows programs through Wine.

Missing an app? One command: minion-install gimp (apt packages, .deb and .AppImage URLs, pip:, npm:).
```

Image: [office.png](../assets/office.png). Alt text: *A one-page brief in LibreOffice Writer, typed by an AI agent
on a Minion desktop.*

## 6/9

```text
MCP-first. One click in Claude Desktop, VS Code, Cursor, LM Studio, Goose or Kiro, a Claude Code plugin, or one line that connects every AI app on your computer:

curl -fsSL https://raw.githubusercontent.com/apophisss/minion/main/install.sh | sh

Codex, Gemini CLI, opencode, OpenClaw and any MCP client work too.
```

## 7/9

```text
You stay in the loop: watch any desktop live, click Take control, or let the agent hand off ("Please sign in") and wait for Done.

Every step is recorded. Export a GIF, an HTML timeline, or a Python script that replays the session with no model.
```

Image: [demo.gif](../assets/demo.gif). Alt text: *An agent searching Wikipedia on a Minion desktop, step by step,
recorded by Minion's flight recorder.*

## 8/9

```text
Tested on everyday work: AI agents did 93 ordinary computer tasks with Minion, from "zip this folder" to "total the attachment of this email and reply".

Fixing what they ran into cut the calls by 31%, the failed calls by half and the output tokens by 36%.
```

## 9/9

```text
Free and open source (MIT), with zero dependencies on the host.

Code: https://github.com/apophisss/minion
Docs: https://apophisss.github.io/minion/

Feedback welcome, especially about apps where "see" reads the screen poorly.
```

Pin the thread, and reply to questions with answers from [faq-responses.md](faq-responses.md).
