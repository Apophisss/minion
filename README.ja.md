<p align="center"><a href="README.md">English</a> · <a href="README.zh-CN.md">简体中文</a> · <a href="README.zh-TW.md">繁體中文</a> · <a href="README.ko.md">한국어</a> · 日本語 · <a href="README.he.md">עברית</a></p>

<p align="center">
  <img src="docs/assets/hero.png" alt="Minion：AI エージェントのための、すぐに使えるデスクトップ" width="100%">
</p>

<h3 align="center">すべての AI エージェントに、自分専用のコンピューターを。</h3>

<p align="center">
  どんなエージェントでも使える超軽量の Linux デスクトップ（オフィス、開発、リサーチ、ブラウザー、データ、Windows アプリ）：<br>
  Claude、ChatGPT、Gemini、Cursor、VS Code、LangChain、自作のコード、そしてノート PC で動くモデルまで。<br>
  エージェントは画面をテキストとして読み、操作をまとめて実行したりコードで動かしたりしながら、あらゆるプログラムやウェブサイトを使えます。
</p>

> このページは英語版 [README](README.md) の抄訳です。詳しい内容と最新情報は英語のドキュメントをご覧ください。

## Minion とは

Minion は、AI エージェントにあなたのコンピューターではなく、エージェント専用のコンピューターを与えます。各デスクトップは小さな非特権コンテナで動く本物の Linux コンピューターで、デフォルトではホストのフォルダーを一切マウントしません。エージェントは `see` で画面をテキストとして読み取り、`act` や `script` でクリックや入力を行います。使い終わったデスクトップは削除するだけで、危険な操作の前には `fork` で複製しておけます。エージェントにあなたのコンピューターを直接操作させるより安全です。

- **🖥️ どんなプログラムも、どんなサイトも。** ブラウザー、LibreOffice、IDE、ターミナル、ファイルダイアログ、インストーラーが使え、Wine で Windows プログラムも動きます。アプリは名前で開くだけで、初回に自動でインストールされます（`open gimp`）。Web アプリはブラウザーで開きます（`open gmail`）。`menu`、`path`、`read` でメニュー、ファイルダイアログ、ドキュメントの中身を直接扱えます。
- **🧠 画面をテキストで。** `see` はウィンドウ内のコントロールを一覧にし、それぞれに安定した `@id` を付けます（アクセシビリティツリーから取得し、取れない場合は OCR で補います）：`@12 button "Save" (210,62)`。ウェブページ、エディター、ターミナル、スプレッドシート（`A1: value`）も正確なテキストになります。
- **🎯 正直な操作。** すべての操作は画面が落ち着くまで待ってから、何が変わったかを報告します。テキストで指定した対象が画面上になければ、別の場所をクリックせずに、近い候補を示して失敗します。
- **🪙 トークンを節約する設計。** 画面を読み直す代わりに差分を返します（`see(changes=true)`：約 900 トークンではなく約 80 トークン）。コードモードなら 50 ステップの GUI ループも 1 回の呼び出しで済み、コンパクトモードはツール定義を約 3,300 トークンから 450 トークンに縮めます。
- **🪶 超軽量。** デスクトップ 1 つにつき小さなコンテナが 1 つだけで、VNC もデスクトップ環境もありません。約 1.5 秒で準備が整い、アイドル時のメモリーは約 60 MB。使われていないデスクトップは自動的にフリーズされ（CPU 0%）、約 0.2 秒で復帰します。
- **🔌 どんなエージェントでも。** MCP（ローカルまたはリモート）、OpenAI・Anthropic・Gemini やローカルモデル向けの function calling、HTTP、CLI と Agent Skill、Python と TypeScript の SDK、そして Claude、OpenAI、Gemini の computer use に対応しています。
- **🙋 人がいつでも介入できます。** ブラウザーのライブビューからワンクリックで操作を引き継げます。エージェントはサインインのような作業を人に任せ、*Done* が押されるまで待てます。すべての操作は記録され、モデルなしで再生できる Python スクリプトとして書き出せます。
- **📦 依存ゼロ。** ホスト側は Python 標準ライブラリだけで動きます。デスクトップは Docker か Podman（macOS、Windows、Linux）で動きます。

## はじめる

必要なのは [Docker](https://docs.docker.com/get-docker/)（または OrbStack、Podman）だけです。あとは次のいずれかを選んでください。

**1. AI アプリからワンクリックで：**

[![Download the Claude Desktop extension](https://img.shields.io/badge/Claude_Desktop-Download_extension-D97757?style=flat-square&logo=claude&logoColor=white)](https://github.com/apophisss/minion/releases/latest/download/minion.mcpb)
[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_Minion-0098FF?style=flat-square)](https://insiders.vscode.dev/redirect/mcp/install?name=minion&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D)
[![Add to Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/install-mcp?name=minion&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtaW5pb24tZGVza3RvcCIsIm1jcCJdfQ%3D%3D)
[![Install in Visual Studio](https://img.shields.io/badge/Visual_Studio-Install_Minion-C16FDE?style=flat-square)](https://vs-open.link/mcp-install?%7B%22name%22%3A%22minion%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D)
[![Add to LM Studio](https://files.lmstudio.ai/deeplink/mcp-install-light.svg)](https://lmstudio.ai/install-mcp?name=minion&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtaW5pb24tZGVza3RvcCIsIm1jcCJdfQ%3D%3D)
[![Install in Goose](https://goose-docs.ai/img/extension-install-dark.svg)](https://goose-docs.ai/extension?cmd=uvx&arg=minion-desktop&arg=mcp&timeout=900&id=minion&name=Minion&description=Linux%20desktops%20that%20agents%20read%20as%20text%20and%20control)
[![Add to Kiro](https://kiro.dev/images/add-to-kiro.svg)](https://kiro.dev/launch/mcp/add?name=minion&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D)

Claude Code：`claude plugin marketplace add apophisss/minion && claude plugin install minion@minion`。ボタンは [uv](https://docs.astral.sh/uv/) で Minion を起動します。Claude Desktop 拡張機能には、ほかに何も必要ありません。

**2. 1 行で**：Minion をインストールし、このコンピューター上のすべての AI アプリ（Claude Desktop、Claude Code、Cursor、VS Code、Windsurf/Devin、Gemini CLI、Codex、LM Studio、Cline、Kiro）に接続します。

```bash
curl -fsSL https://raw.githubusercontent.com/apophisss/minion/main/install.sh | sh        # macOS, Linux
```

```powershell
irm https://raw.githubusercontent.com/apophisss/minion/main/install.ps1 | iex             # Windows
```

最後に `minion setup` が実行され、Docker の確認、デスクトップの準備、`minion connect` の実行までを行います。どちらのコマンドも、いつでも再実行できます。

**3. ブラウザー版の ChatGPT、Claude.ai、Le Chat から**：`minion share` を実行し、表示された URL をアプリのコネクター設定に貼り付けます（[手順](docs/remote.md)、英語）。

あとは頼むだけです：*「office デスクトップを作成して、Writer で第 3 四半期の数字について 1 ページの概要を書き、brief.docx として保存してください。」* インストール方法の一覧は [docs/install.md](docs/install.md)（英語）にあります。

<p align="center"><img src="docs/assets/demo.gif" alt="Minion のデスクトップで Wikipedia を検索するエージェント。Minion のフライトレコーダーで記録" width="720"></p>
<p align="center"><sub><code>research</code> デスクトップで作業するエージェント。この GIF は Minion に組み込まれたフライトレコーダー（<code>minion replay -o demo.gif</code>）で作成しました。</sub></p>
<p align="center"><sub>▶ <a href="https://apophisss.github.io/minion/assets/demo.mp4">1 分間のデモ動画を見る</a>：エージェントが Wikipedia で旅行を調べ、スプレッドシートでグラフ付きの予算を作り、計画を PDF に書き出します。ツール呼び出し 12 回、2,372 トークン。</sub></p>

## エージェントを接続する

`minion connect` は、このコンピューターにあるエージェントアプリ（Claude Desktop、Claude Code、Cursor、VS Code、Devin Desktop/Windsurf、Gemini CLI、Codex、LM Studio、Cline、Kiro、Zed）を見つけて、それぞれの設定に Minion の MCP サーバーを追加します。マージするのは `minion` という名前のエントリー 1 つだけで、変更前にはファイルをバックアップし、何度実行しても結果は変わりません。

```bash
minion connect              # アプリを探し、接続するものを選ぶ
minion connect --list       # すべてのアプリ、その設定ファイル、接続済みかどうかを表示
minion connect --dry-run    # 実際には変更せず、変更内容を diff で表示
minion connect --remove     # Minion を取り除く
minion connect --compact    # `computer` ツール 1 つだけを接続し、コンテキストを最小限に
```

そのほかの MCP クライアント：Minion は stdio の MCP サーバーです。ほとんどのアプリは次の JSON を受け付けます（VS Code 独自の `mcp.json` では、キー名が `servers` です）。

```json
{ "mcpServers": { "minion": { "command": "uvx", "args": ["minion-desktop", "mcp"] } } }
```

各ツールのコマンドで追加することもできます（Codex では、デスクトップイメージの初回ダウンロードに備えてタイムアウトを延ばす必要があります。[docs/install.md](docs/install.md#codex) を参照）。

```bash
claude mcp add --scope user minion -- uvx minion-desktop mcp    # Claude Code
codex mcp add minion -- uvx minion-desktop mcp                  # Codex
gemini mcp add --scope user minion uvx minion-desktop mcp       # Gemini CLI
```

MCP を使わない方法もあります：[function calling](docs/agents.md#without-mcp-function-calling-with-any-model)（ローカルモデルを含むあらゆるモデル）· [HTTP API](docs/http-api.md) · [CLI](docs/cli.md) と Agent Skill · [Python](docs/python.md) と [TypeScript](clients/typescript) · [Claude の computer use](docs/computer-use.md) · [OpenAI と Gemini の computer use](docs/computer-use-openai-gemini.md) · [エージェントフレームワーク](docs/integrations.md)。

## 例：シェルからひと回り

ターミナルを使えるエージェント（Claude Code、Codex CLI、Aider、Open Interpreter、Goose）なら、CLI をそのまま使えます。使い方は `minion skill --install` が教えてくれます。

```bash
minion up research
minion open en.wikipedia.org             # ページの読み込みが終わるまで待つ
minion fill "Search Wikipedia" "Ada Lovelace" && minion key Return
minion wait-for "Analytical Engine"      # テキストが見えた場所を教えてくれる
minion see --full                        # 記事全体をテキストとして読む
minion shot -o page.png --marks          # @id を描き込んだスクリーンショット
minion cp :~/Documents/notes.md .        # ファイルを取り出す（入れることもできる）
```

## プロファイル

| プロファイル | 中身 | ダウンロード | アイドル時のメモリー |
|---|---|---|---|
| 🌐 `browser` | uBlock Origin 入りの Firefox（広告、トラッカー、Cookie バナー、ニュースレターのポップアップをブロック）。ダウンロードは `~/Downloads` に直接保存 | 363 MB | ~55–100 MB |
| 📄 `office` | LibreOffice の Writer、Calc、Impress + テキストエディター + ファイルマネージャー + Firefox + PDF ツール。デフォルトで Microsoft 形式で保存 | 526 MB | ~85 MB |
| 🛠️ `dev` | git、Python、Node.js、ビルドツール、Geany IDE、`see` で読めるターミナル、Firefox + Chromium | 714 MB | ~55 MB |
| 🔎 `research` | Firefox + `pdftotext`、`pandoc`、メモ用のエディター、requests と BeautifulSoup 入りの Python | 422 MB | ~55 MB |
| 📊 `data` | `office` + pandas、NumPy、SciPy、matplotlib、seaborn、openpyxl、SQLite | 674 MB | ~105 MB |
| 🪟 `windows` | 64 ビット・32 ビットの Windows `.exe`/`.msi` プログラム用の Wine 10。x86-64 ホストのみ（[ドキュメント](docs/windows-apps.md)） | 717 MB | ~56 MB（プログラムを開くと約 270 MB） |
| 🧩 `base` | X サーバー、ウィンドウマネージャー、ターミナル、エージェント。ほかのプロファイルの土台です | 199 MB | ~65 MB |

独自のプロファイルは、`~/.config/minion/profiles/` に置く 5 行の TOML ファイルです。初めて使うときに自動でビルドされます。詳しくは [docs/profiles.md](docs/profiles.md)（英語）をご覧ください。

## セキュリティ

各デスクトップは、デフォルトでホストのマウントを持たない非特権コンテナです。`--offline` でネットワークを切断し、`--memory` と `--cpus` でリソースを制限できます。HTTP サーバーは `127.0.0.1` にのみバインドし、ランダムなトークンを必須とします。デスクトップのユーザーはコンテナ内でパスワードなしの `sudo` を使えるので、エージェントはソフトウェアをインストールできます。画面上のものはすべて信頼できない入力（プロンプトインジェクション）として扱い、認証情報をデスクトップに入れないでください。詳しくは [SECURITY.md](SECURITY.md)（英語）をご覧ください。

## ドキュメント（英語）

[ウェブサイト](https://apophisss.github.io/minion/) · [インストール](docs/install.md) · [アプリの接続](docs/connect.md) · [リモート MCP](docs/remote.md) · [設計](docs/design.md) · [エージェントと MCP](docs/agents.md) · [連携](docs/integrations.md) · [CLI](docs/cli.md) · [Python](docs/python.md) · [HTTP API](docs/http-api.md) · [Claude の computer use](docs/computer-use.md) · [OpenAI と Gemini の computer use](docs/computer-use-openai-gemini.md) · [プロファイル](docs/profiles.md) · [Windows アプリ](docs/windows-apps.md) · [アーキテクチャ](docs/architecture.md) · [FAQ](docs/faq.md)

Issue や Pull Request を歓迎します。[CONTRIBUTING.md](CONTRIBUTING.md) をご覧ください。

## ライセンス

[MIT](LICENSE)。デスクトップに含まれるオープンソースソフトウェア（Debian、Firefox、LibreOffice、Wine など）には、それぞれのライセンスが適用されます。
