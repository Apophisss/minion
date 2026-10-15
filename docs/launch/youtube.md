# YouTube

Upload [demo.mp4](../assets/demo.mp4): 1920×1080, 1:03, 25 fps, with a silent audio track. It has no narration, and
on-screen captions explain each step, so it works with the sound off. Make it the first video in the Product Hunt
gallery and link it in posts.

## Upload settings

| Field | Value |
|---|---|
| Title (100 characters at most) | Minion: an AI agent uses a browser, a spreadsheet and a word processor (12 tool calls) |
| Thumbnail | [demo-thumbnail.jpg](../assets/demo-thumbnail.jpg) (1280×720) |
| Audience | Not made for kids |
| Category | Science & Technology |
| Tags | AI agent, computer use, MCP, MCP server, Claude, ChatGPT, LibreOffice, automation, open source, Linux, Docker |
| License | Standard YouTube License (the code is MIT) |

Other titles:

- Give every AI agent its own computer: Minion in one minute
- An AI agent plans a trip in 3 apps with 2,372 tokens, no screenshots

## Description

```text
Minion gives every AI agent its own computer: a featherweight Linux desktop in Docker that agents read as text and control over MCP, function calling, HTTP, a CLI or Python.

In this video, an agent researches Lisbon on Wikipedia, makes a budget with a chart in LibreOffice Calc, and writes the plan as a PDF in LibreOffice Writer. Every step is one Minion tool call, shown next to the desktop with the text the agent got back. The whole job took 12 tool calls and 2,372 tokens of text. The same steps done with screenshots would cost about 36,855 tokens (27 screenshots at 1,365 tokens each).

Chapters
0:00 Research on the web
0:17 A budget in a spreadsheet
0:37 A plan as PDF

Free and open source (MIT): https://github.com/apophisss/minion
Website and docs: https://apophisss.github.io/minion/
Benchmark of five real tasks: https://github.com/apophisss/minion/blob/main/docs/benchmarks.md

Recorded live on a Minion desktop with scripts/demo_video.py. Long steps play at 2× speed and waiting for an app or a page to load at 4×, with a badge on screen. No model was called: the script makes the calls an agent would make. The budget figures are part of the task, and the facts and the total it types are checked against what earlier calls returned.

#AIAgents #MCP #OpenSource
```

The last paragraph matters: say how the video was made, so nobody feels misled.

## After uploading

- Add the video link to the Product Hunt gallery (first item) and to the maker's comment.
- Pin a comment with the GitHub link.
- Share the link in the [welcome discussion](https://github.com/apophisss/minion/discussions/18) on GitHub.
