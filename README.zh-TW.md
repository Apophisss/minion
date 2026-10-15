<p align="center"><a href="README.md">English</a> · <a href="README.zh-CN.md">简体中文</a> · 繁體中文 · <a href="README.ko.md">한국어</a> · <a href="README.ja.md">日本語</a> · <a href="README.he.md">עברית</a></p>

<p align="center">
  <img src="docs/assets/hero.png" alt="Minion：為 AI Agent 即時建立的桌面" width="100%">
</p>

<h3 align="center">讓每個 AI Agent 都有一台自己的電腦。</h3>

<p align="center">
  超輕量的 Linux 桌面（辦公、開發、研究、瀏覽器、資料分析、Windows 應用程式），任何 Agent 都能使用：<br>
  Claude、ChatGPT、Gemini、Cursor、VS Code、LangChain、你自己寫的程式，或是在你筆電上執行的模型。<br>
  Agent 以文字讀取螢幕，可以批次操作，也可以用程式碼驅動，能使用任何程式和網站。
</p>

> 本文是英文 [README](README.md) 的精簡翻譯，完整、最新的內容請以英文文件為準。

## Minion 是什麼

Minion 讓 AI Agent 擁有一台屬於自己的電腦，而不是直接使用你的電腦。每個桌面都是一台真正的 Linux 電腦，在一個小巧的無特權容器中執行，預設不會掛載主機上的任何資料夾。Agent 用 `see` 把螢幕讀成文字，再用 `act` 或 `script` 點擊和輸入；桌面用完可以直接刪除，進行有風險的操作之前，也可以先 `fork` 一份。這比讓 Agent 直接操作你的電腦更安全。

- **🖥️ 任何程式，任何網站。** 瀏覽器、LibreOffice、IDE、終端機、檔案對話框、安裝程式都能用，還能透過 Wine 執行 Windows 程式。用名稱開啟任何應用程式，第一次會自動安裝（`open gimp`），網頁應用程式則在瀏覽器中開啟（`open gmail`）。`menu`、`path` 和 `read` 可直接操作選單、檔案對話框和文件內容。
- **🧠 螢幕即文字。** `see` 會列出視窗中的控制項，每個控制項都有穩定的 `@id`（來自無障礙樹，並以 OCR 作為備援）：`@12 button "Save" (210,62)`。網頁、編輯器、終端機和試算表（`A1: value`）都會輸出成精確的文字。
- **🎯 如實回報的操作。** 每個操作都會等畫面穩定後再回報變化。文字目標不在螢幕上時會直接失敗，並列出最接近的候選項目，而不是點到別的地方。
- **🪙 為節省 token 而設計。** 用差異取代重新讀取（`see(changes=true)`：約 60 個 token，而不是約 900 個）；程式碼模式只要一次呼叫就能跑完 50 步的 GUI 迴圈；精簡模式把工具定義從約 2,100 個 token 縮減到 230 個。
- **🪶 超輕量。** 每個桌面只是一個小容器，沒有 VNC，也沒有桌面環境。約 1.5 秒就緒，閒置時約使用 60 MB 記憶體，並會自動凍結（0% CPU），約 0.2 秒就能喚醒。
- **🔌 支援所有 Agent。** MCP（本機或遠端）、適用於 OpenAI、Anthropic、Gemini 和本機模型的 function calling、HTTP、CLI 和 Agent Skill、Python 與 TypeScript SDK，以及 Claude、OpenAI、Gemini 的 computer use。
- **🙋 人隨時可以介入。** 在瀏覽器的即時畫面中，一鍵就能接管；Agent 可以把登入這類操作交給你，等你按下 *Done* 再繼續。每個步驟都有紀錄，還能匯出成不需要模型就能重播的 Python 腳本。
- **📦 零相依性。** 主機端只使用 Python 標準函式庫。桌面在 Docker 或 Podman 中執行（macOS、Windows、Linux）。

## 快速開始

只需要 [Docker](https://docs.docker.com/get-docker/)（或 OrbStack、Podman）。接著任選一種方式：

**1. 在 AI 應用程式中一鍵安裝：**

[![Download the Claude Desktop extension](https://img.shields.io/badge/Claude_Desktop-Download_extension-D97757?style=flat-square&logo=claude&logoColor=white)](https://github.com/apophisss/minion/releases/latest/download/minion.mcpb)
[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_Minion-0098FF?style=flat-square)](https://insiders.vscode.dev/redirect/mcp/install?name=minion&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D)
[![Add to Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/install-mcp?name=minion&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtaW5pb24tZGVza3RvcCIsIm1jcCJdfQ%3D%3D)
[![Install in Visual Studio](https://img.shields.io/badge/Visual_Studio-Install_Minion-C16FDE?style=flat-square)](https://vs-open.link/mcp-install?%7B%22name%22%3A%22minion%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D)
[![Add to LM Studio](https://files.lmstudio.ai/deeplink/mcp-install-light.svg)](https://lmstudio.ai/install-mcp?name=minion&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtaW5pb24tZGVza3RvcCIsIm1jcCJdfQ%3D%3D)
[![Install in Goose](https://goose-docs.ai/img/extension-install-dark.svg)](https://goose-docs.ai/extension?cmd=uvx&arg=minion-desktop&arg=mcp&timeout=900&id=minion&name=Minion&description=Linux%20desktops%20that%20agents%20read%20as%20text%20and%20control)
[![Add to Kiro](https://kiro.dev/images/add-to-kiro.svg)](https://kiro.dev/launch/mcp/add?name=minion&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D)

Claude Code：`claude plugin marketplace add apophisss/minion && claude plugin install minion@minion`。上面的按鈕會透過 [uv](https://docs.astral.sh/uv/) 啟動 Minion；Claude Desktop 擴充功能則不需要另外安裝任何東西。

**2. 一行指令**：安裝 Minion，並連接這台電腦上所有的 AI 應用程式（Claude Desktop、Claude Code、Cursor、VS Code、Windsurf/Devin、Gemini CLI、Codex、LM Studio、Cline、Kiro）：

```bash
curl -fsSL https://raw.githubusercontent.com/apophisss/minion/main/install.sh | sh        # macOS, Linux
```

```powershell
irm https://raw.githubusercontent.com/apophisss/minion/main/install.ps1 | iex             # Windows
```

安裝的最後一步是 `minion setup`：檢查 Docker、準備好一個桌面，再執行 `minion connect`。這兩行指令隨時都可以重新執行。

**3. 在瀏覽器中使用 ChatGPT、Claude.ai 或 Le Chat**：執行 `minion share`，把它印出的網址貼到應用程式的連接器（connector）設定中（[說明](docs/remote.md)，英文）。

接著直接提出需求：*「建立一個 office 桌面，用 Writer 寫一頁關於我們第三季數字的簡報，存成 brief.docx。」* 所有安裝方式請見 [docs/install.md](docs/install.md)（英文）。

<p align="center"><img src="docs/assets/demo.gif" alt="一個 Agent 在 Minion 桌面上搜尋維基百科，由 Minion 的飛行記錄器錄製" width="720"></p>
<p align="center"><sub>一個在 <code>research</code> 桌面上工作的 Agent。這個 GIF 由 Minion 內建的飛行記錄器（flight recorder）產生（<code>minion replay -o demo.gif</code>）。</sub></p>

## 連接你的 Agent

`minion connect` 會找出這台電腦上的 Agent 應用程式（Claude Desktop、Claude Code、Cursor、VS Code、Devin Desktop/Windsurf、Gemini CLI、Codex、LM Studio、Cline、Kiro、Zed），把 Minion 的 MCP 伺服器加進它們的設定。它只會合併一筆名為 `minion` 的設定，修改前會先備份，重複執行也不會造成任何變化。

```bash
minion connect              # 找出你的應用程式，選擇要連接哪些
minion connect --list       # 列出所有應用程式、各自的設定檔，以及是否已連接
minion connect --dry-run    # 以 diff 預覽變更，不實際修改
minion connect --remove     # 移除 Minion
minion connect --compact    # 只提供一個 `computer` 工具，佔用的上下文最少
```

其他 MCP 用戶端：Minion 是一個 stdio MCP 伺服器，大多數應用程式都接受下面這段 JSON（VS Code 自己的 `mcp.json` 中，鍵名是 `servers`）：

```json
{ "mcpServers": { "minion": { "command": "uvx", "args": ["minion-desktop", "mcp"] } } }
```

也可以用各個工具自己的指令加入（Codex 第一次下載桌面映像檔時需要調高逾時設定，請見 [docs/install.md](docs/install.md#codex)）：

```bash
claude mcp add --scope user minion -- uvx minion-desktop mcp    # Claude Code
codex mcp add minion -- uvx minion-desktop mcp                  # Codex
gemini mcp add --scope user minion uvx minion-desktop mcp       # Gemini CLI
```

不使用 MCP 也可以：[function calling](docs/agents.md#without-mcp-function-calling-with-any-model)（任何模型，包括本機模型）· [HTTP API](docs/http-api.md) · [CLI](docs/cli.md) 和 Agent Skill · [Python](docs/python.md) 與 [TypeScript](clients/typescript) · [Claude computer use](docs/computer-use.md) · [OpenAI 與 Gemini computer use](docs/computer-use-openai-gemini.md) · [Agent 框架](docs/integrations.md)。

## 範例：在 shell 中走一遍

任何能使用終端機的 Agent（Claude Code、Codex CLI、Aider、Open Interpreter、Goose）都可以直接使用 CLI，`minion skill --install` 會教它怎麼用：

```bash
minion up research
minion open en.wikipedia.org             # 等到頁面載入完成
minion fill "Search Wikipedia" "Ada Lovelace" && minion key Return
minion wait-for "Analytical Engine"      # 會告訴你在哪裡看到這段文字
minion see --full                        # 以文字讀取整篇文章
minion shot -o page.png --marks          # 螢幕截圖，並在上面標出 @id
minion cp :~/Documents/notes.md .        # 把檔案複製出來（也可以複製進去）
```

## Profile（桌面範本）

| Profile | 內容 | 下載大小 | 閒置記憶體 |
|---|---|---|---|
| 🌐 `browser` | Firefox + uBlock Origin（阻擋廣告、追蹤器、Cookie 橫幅、電子報彈出視窗），下載的檔案直接存到 `~/Downloads` | 352 MB | ~55–100 MB |
| 📄 `office` | LibreOffice Writer、Calc、Impress + 文字編輯器 + 檔案管理員 + Firefox + PDF 工具，預設儲存為 Microsoft 格式 | 511 MB | ~85 MB |
| 🛠️ `dev` | git、Python、Node.js、建置工具、Geany IDE、`see` 可讀取的終端機、Firefox + Chromium | 703 MB | ~55 MB |
| 🔎 `research` | Firefox + `pdftotext`、`pandoc`、筆記編輯器，以及附 requests 和 BeautifulSoup 的 Python | 410 MB | ~55 MB |
| 📊 `data` | `office` + pandas、NumPy、SciPy、matplotlib、seaborn、openpyxl、SQLite | 663 MB | ~105 MB |
| 🪟 `windows` | Wine 10，可執行 64 位元和 32 位元的 Windows `.exe`/`.msi` 程式。需要 x86-64 主機（[文件](docs/windows-apps.md)） | 707 MB | ~56 MB（開啟程式後約 270 MB） |
| 🧩 `base` | X server、視窗管理員、終端機和 agent，是其他 profile 的基礎 | 187 MB | ~65 MB |

自訂 profile 只是 `~/.config/minion/profiles/` 裡一個 5 行的 TOML 檔，第一次使用時會自動建置，詳情請見 [docs/profiles.md](docs/profiles.md)（英文）。

## 安全性

每個桌面都是無特權容器，預設不掛載主機的資料夾；可以用 `--offline` 中斷網路，用 `--memory` 和 `--cpus` 限制資源。HTTP 伺服器只綁定 `127.0.0.1`，而且需要隨機 token。容器內的使用者有免密碼的 `sudo`，方便 Agent 安裝軟體。請把螢幕上的所有內容都當成不可信的輸入（提示詞注入），不要把帳密放進桌面。詳情請見 [SECURITY.md](SECURITY.md)（英文）。

## 文件（英文）

[網站](https://apophisss.github.io/minion/) · [安裝](docs/install.md) · [連接你的應用程式](docs/connect.md) · [遠端 MCP](docs/remote.md) · [設計理念](docs/design.md) · [Agent 與 MCP](docs/agents.md) · [框架整合](docs/integrations.md) · [CLI](docs/cli.md) · [Python](docs/python.md) · [HTTP API](docs/http-api.md) · [Claude computer use](docs/computer-use.md) · [OpenAI 與 Gemini computer use](docs/computer-use-openai-gemini.md) · [Profile](docs/profiles.md) · [Windows 應用程式](docs/windows-apps.md) · [架構](docs/architecture.md) · [常見問題](docs/faq.md)

歡迎提出 Issue 和 Pull Request，請先閱讀 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 授權條款

[MIT](LICENSE)。桌面中包含的開源軟體（Debian、Firefox、LibreOffice、Wine 等）適用各自的授權條款。
