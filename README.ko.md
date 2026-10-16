<p align="center"><a href="README.md">English</a> · <a href="README.zh-CN.md">简体中文</a> · <a href="README.zh-TW.md">繁體中文</a> · 한국어 · <a href="README.ja.md">日本語</a> · <a href="README.he.md">עברית</a></p>

<p align="center">
  <img src="docs/assets/hero.png" alt="Minion: AI 에이전트를 위한 즉시 실행 데스크톱" width="100%">
</p>

<h3 align="center">모든 AI 에이전트에게 자기만의 컴퓨터를.</h3>

<p align="center">
  어떤 에이전트든 쓸 수 있는 초경량 Linux 데스크톱(오피스, 개발, 리서치, 브라우저, 데이터, Windows 앱):<br>
  Claude, ChatGPT, Gemini, Cursor, VS Code, LangChain, 직접 작성한 코드, 노트북에서 돌아가는 모델까지.<br>
  에이전트는 화면을 텍스트로 읽고, 동작을 묶어서 실행하거나 코드로 제어하며, 어떤 프로그램이나 웹사이트든 사용합니다.
</p>

> 이 문서는 영어 [README](README.md)를 간추려 옮긴 것입니다. 전체 내용과 최신 정보는 영어 문서를 기준으로 합니다.

## Minion이란?

Minion은 AI 에이전트에게 여러분의 컴퓨터 대신 에이전트 전용 컴퓨터를 줍니다. 데스크톱 하나하나가 작은 비특권(unprivileged) 컨테이너에서 돌아가는 진짜 Linux 컴퓨터이고, 기본 설정에서는 호스트의 폴더를 하나도 마운트하지 않습니다. 에이전트는 `see`로 화면을 텍스트로 읽고, `act`나 `script`로 클릭하고 입력합니다. 다 쓴 데스크톱은 지우면 그만이고, 위험한 작업 전에는 `fork`로 복제해 둘 수 있습니다. 에이전트에게 여러분의 컴퓨터를 직접 맡기는 것보다 안전합니다.

- **🖥️ 어떤 프로그램이든, 어떤 웹사이트든.** 브라우저, LibreOffice, IDE, 터미널, 파일 대화상자, 설치 프로그램을 모두 쓸 수 있고, Wine으로 Windows 프로그램도 실행합니다. 앱은 이름으로 열면 처음 한 번 자동으로 설치되고(`open gimp`), 웹 앱은 브라우저에서 열립니다(`open gmail`). `menu`, `path`, `read`로 메뉴, 파일 대화상자, 문서 내용에 바로 접근합니다.
- **🧠 화면을 텍스트로.** `see`는 창 안의 컨트롤을 목록으로 보여 주고, 컨트롤마다 안정적인 `@id`가 붙습니다(접근성 트리에서 가져오고, 없으면 OCR로 대신합니다): `@12 button "Save" (210,62)`. 웹 페이지, 편집기, 터미널, 스프레드시트(`A1: value`)도 정확한 텍스트로 나옵니다.
- **🎯 정직한 동작.** 모든 동작은 화면이 안정될 때까지 기다린 뒤 무엇이 바뀌었는지 알려 줍니다. 텍스트로 지정한 대상이 화면에 없으면 엉뚱한 곳을 클릭하지 않고, 가장 가까운 후보를 알려 주며 실패합니다.
- **🪙 토큰 절약을 위한 설계.** 화면을 다시 읽는 대신 바뀐 부분만 받습니다(`see(changes=true)`: 약 900 토큰 대신 약 80 토큰). 코드 모드는 50단계짜리 GUI 루프도 호출 한 번으로 끝내고, 컴팩트 모드는 도구 정의를 약 3,300 토큰에서 450 토큰으로 줄입니다.
- **🪶 초경량.** 데스크톱마다 작은 컨테이너 하나뿐이고, VNC도 데스크톱 환경도 없습니다. 약 1.5초 만에 준비되고, 유휴 상태에서는 약 60MB를 쓰며, 쓰지 않으면 자동으로 동결되었다가(CPU 0%) 약 0.2초 만에 깨어납니다.
- **🔌 모든 에이전트와 함께.** MCP(로컬 또는 원격), OpenAI·Anthropic·Gemini와 로컬 모델을 위한 function calling, HTTP, CLI와 Agent Skill, Python·TypeScript SDK, 그리고 Claude, OpenAI, Gemini의 computer use까지 지원합니다.
- **🙋 언제든 사람이 개입.** 브라우저의 라이브 뷰에서 클릭 한 번으로 제어권을 가져올 수 있고, 에이전트는 로그인 같은 일을 사람에게 넘긴 뒤 *Done*을 누를 때까지 기다립니다. 모든 동작이 기록되어, 모델 없이 그대로 재생하는 Python 스크립트로 내보낼 수도 있습니다.
- **📦 의존성 0.** 호스트 쪽은 순수 Python 표준 라이브러리만 씁니다. 데스크톱은 Docker나 Podman(macOS, Windows, Linux)에서 돌아갑니다.

## 시작하기

[Docker](https://docs.docker.com/get-docker/)(또는 OrbStack, Podman)만 있으면 됩니다. 그다음 아래 방법 중 하나를 고르세요.

**1. AI 앱에서 클릭 한 번으로:**

[![Download the Claude Desktop extension](https://img.shields.io/badge/Claude_Desktop-Download_extension-D97757?style=flat-square&logo=claude&logoColor=white)](https://github.com/apophisss/minion/releases/latest/download/minion.mcpb)
[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_Minion-0098FF?style=flat-square)](https://insiders.vscode.dev/redirect/mcp/install?name=minion&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D)
[![Add to Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/install-mcp?name=minion&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtaW5pb24tZGVza3RvcCIsIm1jcCJdfQ%3D%3D)
[![Install in Visual Studio](https://img.shields.io/badge/Visual_Studio-Install_Minion-C16FDE?style=flat-square)](https://vs-open.link/mcp-install?%7B%22name%22%3A%22minion%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D)
[![Add to LM Studio](https://files.lmstudio.ai/deeplink/mcp-install-light.svg)](https://lmstudio.ai/install-mcp?name=minion&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtaW5pb24tZGVza3RvcCIsIm1jcCJdfQ%3D%3D)
[![Install in Goose](https://goose-docs.ai/img/extension-install-dark.svg)](https://goose-docs.ai/extension?cmd=uvx&arg=minion-desktop&arg=mcp&timeout=900&id=minion&name=Minion&description=Linux%20desktops%20that%20agents%20read%20as%20text%20and%20control)
[![Add to Kiro](https://kiro.dev/images/add-to-kiro.svg)](https://kiro.dev/launch/mcp/add?name=minion&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D)

Claude Code: `claude plugin marketplace add apophisss/minion && claude plugin install minion@minion`. 위 버튼들은 [uv](https://docs.astral.sh/uv/)로 Minion을 실행하고, Claude Desktop 확장 프로그램은 그 밖에 아무것도 필요하지 않습니다.

**2. 한 줄 설치**: Minion을 설치하고 이 컴퓨터의 모든 AI 앱(Claude Desktop, Claude Code, Cursor, VS Code, Windsurf/Devin, Gemini CLI, Codex, LM Studio, Cline, Kiro)에 연결합니다.

```bash
curl -fsSL https://raw.githubusercontent.com/apophisss/minion/main/install.sh | sh        # macOS, Linux
```

```powershell
irm https://raw.githubusercontent.com/apophisss/minion/main/install.ps1 | iex             # Windows
```

설치는 `minion setup`으로 끝납니다. Docker를 확인하고, 데스크톱 하나를 준비하고, `minion connect`를 실행합니다. 두 명령 모두 언제든 다시 실행해도 됩니다.

**3. 브라우저에서 ChatGPT, Claude.ai, Le Chat 사용**: `minion share`를 실행하고, 출력된 URL을 앱의 커넥터(connector) 설정에 붙여 넣습니다([방법](docs/remote.md), 영어).

그런 다음 이렇게 부탁하면 됩니다: *"office 데스크톱을 만들고, Writer로 우리 3분기 실적에 대한 한 페이지짜리 브리핑을 써서 brief.docx로 저장해 줘."* 모든 설치 방법은 [docs/install.md](docs/install.md)(영어)에 있습니다.

<p align="center"><img src="docs/assets/demo.gif" alt="Minion 데스크톱에서 위키백과를 검색하는 에이전트, Minion의 플라이트 레코더로 녹화" width="720"></p>
<p align="center"><sub><code>research</code> 데스크톱에서 일하는 에이전트. 이 GIF는 Minion에 내장된 플라이트 레코더(<code>minion replay -o demo.gif</code>)로 만들었습니다.</sub></p>
<p align="center"><sub>▶ <a href="https://apophisss.github.io/minion/assets/demo.mp4">1분 데모 영상 보기</a>: 에이전트가 위키백과에서 여행을 조사하고, 스프레드시트에 차트가 있는 예산을 만들고, 계획을 PDF로 내보냅니다. 도구 호출 12번, 2,372 토큰.</sub></p>

## 에이전트 연결하기

`minion connect`는 이 컴퓨터에 있는 에이전트 앱(Claude Desktop, Claude Code, Cursor, VS Code, Devin Desktop/Windsurf, Gemini CLI, Codex, LM Studio, Cline, Kiro, Zed)을 찾아 각 앱의 설정에 Minion MCP 서버를 추가합니다. `minion`이라는 항목 하나만 병합하고, 파일을 바꾸기 전에 먼저 백업하며, 여러 번 실행해도 결과가 달라지지 않습니다.

```bash
minion connect              # 이 컴퓨터의 앱을 찾아서 연결할 앱을 고릅니다
minion connect --list       # 모든 앱과 설정 파일, 연결 여부를 보여 줍니다
minion connect --dry-run    # 실제로 바꾸지 않고 변경 내용을 diff로 보여 줍니다
minion connect --remove     # Minion을 다시 제거합니다
minion connect --compact    # `computer` 도구 하나만 연결해 컨텍스트를 최소로 씁니다
```

그 밖의 MCP 클라이언트: Minion은 stdio MCP 서버입니다. 대부분의 앱은 아래 JSON을 그대로 받습니다(VS Code의 자체 `mcp.json`에서는 키 이름이 `servers`입니다).

```json
{ "mcpServers": { "minion": { "command": "uvx", "args": ["minion-desktop", "mcp"] } } }
```

각 도구의 명령으로 추가할 수도 있습니다(Codex는 데스크톱 이미지를 처음 내려받을 때 타임아웃을 늘려야 합니다. [docs/install.md](docs/install.md#codex) 참고).

```bash
claude mcp add --scope user minion -- uvx minion-desktop mcp    # Claude Code
codex mcp add minion -- uvx minion-desktop mcp                  # Codex
gemini mcp add --scope user minion uvx minion-desktop mcp       # Gemini CLI
```

MCP 없이도 쓸 수 있습니다: [function calling](docs/agents.md#without-mcp-function-calling-with-any-model)(로컬 모델을 포함한 모든 모델) · [HTTP API](docs/http-api.md) · [CLI](docs/cli.md)와 Agent Skill · [Python](docs/python.md)과 [TypeScript](clients/typescript) · [Claude computer use](docs/computer-use.md) · [OpenAI·Gemini computer use](docs/computer-use-openai-gemini.md) · [에이전트 프레임워크](docs/integrations.md).

## 예제: 셸에서 둘러보기

터미널을 쓸 수 있는 에이전트(Claude Code, Codex CLI, Aider, Open Interpreter, Goose)는 CLI를 바로 쓸 수 있고, `minion skill --install`이 사용법을 가르쳐 줍니다.

```bash
minion up research
minion open en.wikipedia.org             # 페이지 로딩이 끝날 때까지 기다립니다
minion fill "Search Wikipedia" "Ada Lovelace" && minion key Return
minion wait-for "Analytical Engine"      # 텍스트를 어디에서 봤는지 알려 줍니다
minion see --full                        # 문서 전체를 텍스트로 읽습니다
minion shot -o page.png --marks          # @id를 표시한 스크린샷
minion cp :~/Documents/notes.md .        # 파일을 밖으로(또는 안으로) 복사합니다
```

## 프로필

| 프로필 | 들어 있는 것 | 다운로드 | 유휴 RAM |
|---|---|---|---|
| 🌐 `browser` | Firefox와 uBlock Origin(광고, 추적기, 쿠키 배너, 뉴스레터 팝업 차단), `~/Downloads`로 바로 저장되는 다운로드 | 363 MB | ~55–100 MB |
| 📄 `office` | LibreOffice Writer, Calc, Impress + 텍스트 편집기 + 파일 관리자 + Firefox + PDF 도구. 기본적으로 Microsoft 형식으로 저장 | 526 MB | ~85 MB |
| 🛠️ `dev` | git, Python, Node.js, 빌드 도구, Geany IDE, `see`로 읽을 수 있는 터미널, Firefox + Chromium | 714 MB | ~55 MB |
| 🔎 `research` | Firefox + `pdftotext`, `pandoc`, 메모용 편집기, requests와 BeautifulSoup이 들어 있는 Python | 422 MB | ~55 MB |
| 📊 `data` | `office` + pandas, NumPy, SciPy, matplotlib, seaborn, openpyxl, SQLite | 674 MB | ~105 MB |
| 🪟 `windows` | 64비트·32비트 Windows `.exe`/`.msi` 프로그램을 위한 Wine 10. x86-64 호스트 전용([문서](docs/windows-apps.md)) | 717 MB | ~56 MB(프로그램을 열면 약 270 MB) |
| 🧩 `base` | X 서버, 창 관리자, 터미널, 에이전트. 다른 프로필의 기반 | 199 MB | ~65 MB |

나만의 프로필은 `~/.config/minion/profiles/`에 두는 5줄짜리 TOML 파일이며, 처음 사용할 때 자동으로 빌드됩니다. 자세한 내용은 [docs/profiles.md](docs/profiles.md)(영어)를 참고하세요.

## 보안

각 데스크톱은 기본적으로 호스트 마운트가 없는 비특권 컨테이너입니다. `--offline`으로 네트워크를 끊고, `--memory`와 `--cpus`로 자원을 제한할 수 있습니다. HTTP 서버는 `127.0.0.1`에만 바인딩되고 무작위 토큰이 필요합니다. 데스크톱 사용자는 컨테이너 안에서 비밀번호 없이 `sudo`를 쓸 수 있어서, 에이전트가 소프트웨어를 설치할 수 있습니다. 화면에 보이는 모든 것은 신뢰할 수 없는 입력(프롬프트 인젝션)으로 취급하고, 자격 증명을 데스크톱에 넣지 마세요. 자세한 내용은 [SECURITY.md](SECURITY.md)(영어)를 참고하세요.

## 문서(영어)

[웹사이트](https://apophisss.github.io/minion/) · [설치](docs/install.md) · [앱 연결](docs/connect.md) · [원격 MCP](docs/remote.md) · [설계](docs/design.md) · [에이전트와 MCP](docs/agents.md) · [통합](docs/integrations.md) · [CLI](docs/cli.md) · [Python](docs/python.md) · [HTTP API](docs/http-api.md) · [Claude computer use](docs/computer-use.md) · [OpenAI·Gemini computer use](docs/computer-use-openai-gemini.md) · [프로필](docs/profiles.md) · [Windows 앱](docs/windows-apps.md) · [아키텍처](docs/architecture.md) · [FAQ](docs/faq.md)

이슈와 풀 리퀘스트를 환영합니다. [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.

## 라이선스

[MIT](LICENSE). 데스크톱에 들어 있는 오픈 소스 소프트웨어(Debian, Firefox, LibreOffice, Wine 등)는 각자의 라이선스를 따릅니다.
