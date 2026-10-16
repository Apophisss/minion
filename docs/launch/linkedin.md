# LinkedIn

Attach the demo video [demo.mp4](../assets/demo.mp4) (LinkedIn plays uploaded videos in the feed), or
[hero.png](../assets/hero.png). LinkedIn doesn't render Markdown, so the post is plain text. Avoid typing
`@` before ids: LinkedIn turns it into a mention. The post has about 2,000 characters (the limit is 3,000).

```text
AI agents are starting to operate computers: clicking, typing, filling in spreadsheets. Before you let one loose, it's worth asking: whose computer?

I built Minion so the answer isn't "yours". It gives every AI agent its own disposable Linux desktop, in a small container on your machine. The agent gets a real computer, with a browser, LibreOffice, an IDE, a terminal and even Windows programs through Wine, and you keep yours.

What makes it practical:

→ The screen as text. Instead of guessing coordinates on screenshots, the agent reads a short list of the controls on screen, each with a stable ID, taken from the accessibility tree. After typing a sentence, checking the result costs about 80 tokens instead of about 900.

→ Honest actions. Every action waits for the screen to settle and reports what changed. If the target isn't on screen, the action fails and names the closest matches instead of clicking something else.

→ Light enough to run many. A desktop is ready in about 1.5 seconds and uses about 60 MB of memory when idle. Idle desktops freeze to 0% CPU.

→ Tested on everyday work. Before the release, AI agents did 93 ordinary computer tasks with it, from zipping a folder to answering an email with the total of its attachment. Fixing what they ran into cut the tool calls by 31% and the failed ones by half.

→ Works with the agents teams already use: Claude Code, Codex, Cursor, VS Code, Gemini CLI, OpenClaw or any MCP client, plus function calling, HTTP and Python for your own agents. Setup is one click, or one command that connects every AI app on the computer.

→ People stay in the loop. Watch any desktop live, take control with one click, or let the agent hand off for a sign-in and wait for you.

Minion is free and open source under the MIT license.

I'd value feedback from anyone building with agents: what would you want an agent to do on a computer of its own?

https://github.com/apophisss/minion

#AIAgents #MCP #OpenSource #DeveloperTools
```

If you prefer, move the link to the first comment and end the post with "Link in the comments".
