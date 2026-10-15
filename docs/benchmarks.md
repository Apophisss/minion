# What tasks cost: Minion vs. screenshots

Five everyday tasks, run end to end on an `office` desktop by `python scripts/bench_tasks.py`. The **Minion** column counts the tokens of every tool result the agent reads (the same text an MCP client gets). The **screenshot agent** columns price the same task done the way pixel-based computer use works: each GUI action returns a 1280×800 screenshot (1,365 tokens for Claude, 1,105 for OpenAI at high detail), plus a first look. No model is called; the step lists are in the script.

| Task | Minion: calls · tokens | Screenshot agent: steps · Claude tokens · OpenAI tokens | Fewer tokens with Minion |
|---|---|---|---|
| Write a report and export it as PDF | 5 · 156 | 9 · 12,285 · 9,945 | **78.8×** |
| Fill a spreadsheet with a formula and save it as .xlsx | 5 · 214 | 7 · 9,555 · 7,735 | **44.6×** |
| Look something up on Wikipedia | 3 · 1,689 | 5 · 6,825 · 5,525 | **4.0×** |
| Fill in and submit a web form | 3 · 533 | 11 · 15,015 · 12,155 | **28.2×** |
| Read a 2-page document | 1 · 1,764 | 5 · 6,825 · 5,525 | **3.9×** |
| **All five** | 17 · **4,356** | 37 · 50,505 · 40,885 | **11.6×** |

Notes:

- Tokens are counted with tiktoken o200k_base. Claude's tokenizer isn't public, so its exact counts differ somewhat. Only what the tools return is counted, on both sides; the model's own messages are left out.
- The screenshot agent is priced generously: one screenshot per GUI action, no retries, no scrolling to find things, and no zooming in to read small text. Real runs usually take more.
- Minion's agent also gets exact text: cell values and formulas, a PDF's words, a form's labels, so nothing has to be read off pixels. It needs fewer calls because one `act` can do several steps.
- Tool definitions are sent with every request in both cases: Minion's 9 tools cost about 2,100 tokens, or about 230 in compact mode.
- Measured on 2026-10-15 on a 2-vCPU VM.
