# 中文发布稿

两篇稿子：一篇发 V2EX，一篇长文发掘金和知乎。所有事实和数字都来自项目文档（见发布素材的 [README](README.md)）。
正文以作者第一人称写成。V2EX 和掘金都支持 Markdown，直接复制代码块里的原文即可；知乎可以用“导入文档”导入 Markdown。

中文版 README：https://github.com/apophisss/minion/blob/main/README.zh-CN.md

---

## V2EX

**节点：** 分享创造

**标题：** Minion：给 AI Agent 一台自己的 Linux 电脑，用完即弃（开源，支持 MCP）

发帖时选择 Markdown 格式。V2EX 的读者更喜欢平实、直接的介绍，发完帖记得在帖子里回复大家的问题。

````markdown
大家好，分享一个我做的开源项目：Minion。

一句话介绍：让 AI Agent 在一台独立、用完即弃的 Linux 桌面里干活，而不是直接操作你自己的电脑。每个桌面都是本机上的一个小 Docker 容器，Agent 以文本形式“看”屏幕，然后点击、输入、运行任意程序。

**为什么做这个**

现在的 Agent 需要的不只是浏览器，还有电子表格、文字处理、IDE、终端、文件对话框、安装程序。常见的做法是截图 + 猜坐标：一张 1280×800 的截图大约 1,365 个 token，模型还得自己估算点哪里。我想要的是用最便宜、最可靠的方式给任何 Agent 一台完整的电脑，而且不是我自己的那台。

**几个特点**

- **屏幕即文本**：`see` 把窗口转成一份控件列表，每个控件都有稳定的 `@id`（来自无障碍树，OCR 兜底），比如 `@12 button "Save" (210,62)`。Agent 直接 `click @12`，不用猜坐标。
- **省 token**：打完一句话之后，`see(changes=true)` 只返回变化的部分，约 80 个 token（完整读一遍约 900）。精简模式下，工具定义从约 3,300 个 token 降到约 450 个。代码模式（`script`）在桌面里直接跑 Python，50 步的 GUI 循环一次调用就能完成。
- **操作结果如实反馈**：每个操作都会等界面稳定后再报告变化；文本目标找不到就直接失败，并给出最接近的候选，不会乱点。
- **不止浏览器**：LibreOffice、IDE、终端、文件对话框都能用，Windows 程序可以通过 Wine 运行。
- **轻**：约 1.5 秒就绪，空闲内存 54–105 MB，闲置时自动冻结（0% CPU），约 0.2 秒唤醒（2 vCPU 虚拟机上的测量结果）。
- **接入方式多**：MCP 优先，Claude Code、Codex、Cursor、VS Code、Gemini CLI、opencode、OpenClaw 等都能一键或一条命令接入；也支持 OpenAI / Anthropic / Gemini 的 function calling、通过 Ollama / vLLM 运行的本地模型、带 OpenAPI 的 HTTP 接口、CLI，以及 Python / TypeScript SDK。
- **用日常任务检验过**：发布前，我让 AI Agent 用它完成了 93 个日常电脑任务（从“压缩这个文件夹”到“汇总邮件附件里的数字并回复”），记录了每一次调用。修复它们遇到的问题之后，同样的任务调用次数少了 31%，失败的调用少了一半，输出的 token 少了 36%。
- **人随时能介入**：浏览器里可以实时看桌面、一键接管；Agent 也可以把登录这类操作交给你，等你点 Done 再继续。

**安装**（需要 Docker、OrbStack 或 Podman）：

```bash
curl -fsSL https://raw.githubusercontent.com/apophisss/minion/main/install.sh | sh
```

安装脚本最后会运行 `minion setup`：检查 Docker、准备一个桌面，并把 Minion 接入你电脑上已有的 AI 应用。装了 uv 的话，也可以不安装，直接 `uvx minion-desktop mcp`。

**已知的限制**

- 没有 GPU，纯软件渲染，办公、浏览、开发够用。
- Windows 程序只能在 x86-64 机器上跑，而且 Wine 没有无障碍树，只能靠 OCR 读屏。
- 桌面是沙箱，不是保险箱：容器内有免密 sudo，屏幕上的任何内容都可能带有提示注入。别把密钥和账号放进去，登录交给人来做。

MIT 协议，宿主端零依赖（纯 Python 标准库）。

GitHub：https://github.com/apophisss/minion
中文 README：https://github.com/apophisss/minion/blob/main/README.zh-CN.md

欢迎试用和拍砖，尤其想知道哪些应用的 `see` 输出不好用。
````

---

## 掘金 / 知乎

**标题（任选其一）：**

- 给 AI Agent 一台用完即弃的 Linux 电脑：Minion 的设计取舍
- 让 AI Agent 用文本“看”屏幕：一个开源 MCP 桌面工具是怎么省 token 的

**掘金：** 分类选“人工智能”，标签可以用 AI Agent、MCP、Docker、开源。
**知乎：** 以文章形式发到专栏。开头可以改成一个问题，比如“怎么让 AI Agent 用电脑，又不用你自己的电脑？”。不要在不相关的问题下贴推广式回答。

````markdown
> 作者注：Minion 是我做的开源项目（MIT 协议）。这篇文章介绍它为什么这样设计。

## 背景：Agent 该用谁的电脑？

Agent 能操作电脑之后，有一个很现实的问题：它该用谁的电脑？

Agent 和它读到的一切内容都应该被当作不可信的：网页、文档、窗口标题、剪贴板里都可能藏着针对模型的指令（提示注入）。让它直接操作你自己的电脑，它能看到、能改动的东西就太多了。

另一方面，Agent 需要的也不只是浏览器：电子表格、文字处理、IDE、终端、文件对话框、安装程序，甚至 Windows 程序。

Minion 想回答的问题是：**用什么方式，能最便宜、最可靠地给任意 AI Agent 一台完整的电脑？**

## Minion 是什么

每个 Minion 桌面都是一台真正的 Linux 桌面（Debian、X11），运行在本机的一个小型无特权容器里，默认不挂载宿主机的任何目录。Agent 通过 MCP、function calling、HTTP、CLI 或 Python / TypeScript 来使用它。用完可以直接删掉，做有风险的操作之前也可以先 `fork` 一份。

内置的 profile 覆盖常见场景：`browser`、`office`、`dev`、`research`、`data`、`windows`（Wine）和 `base`。缺什么软件，一条 `minion-install` 就能装上：apt 包、`.deb` / `.AppImage` / 压缩包的链接、`pip:` 和 `npm:` 包。

## Agent 怎么“看”屏幕

截图是 Agent 能看的东西里最贵的：一张 1280×800 的截图约 1,365 个 token，而且模型还得自己猜坐标。Minion 的做法是像读屏软件一样读屏幕。下面是 `see` 在 LibreOffice 窗口上的输出：

```text
Screen 1280x800 · 1 window
  [1] "Untitled 1 — LibreOffice Writer" — libreoffice-writer (focused) at 0,0 1280x770

UI of "Untitled 1 — LibreOffice Writer" (click/fill with @id; (x,y) is the element center):
@1 menu "File" (22,38)
@2 menu "Edit" (62,38)
…
@12 document text "Untitled 1 - LibreOffice Document" [editable] (603,424)
  @13 heading "Q3 Market Brief" (603,247)
  @14 paragraph "Prepared by an AI agent on a Minion desktop. No human touched the keyboard." (603,282)
```

- 数据来自无障碍树（GTK、Qt、Firefox、Chromium、LibreOffice 都会暴露自己的控件），没有无障碍树的地方（canvas、Wine 程序）用 OCR 兜底。
- `@id` 是稳定的：同一个控件在多次查看之间保持同一个 id，Agent 不用反复读屏就能操作。
- 电子表格的单元格输出为 `A1: value`，失败的公式会显示为 `#ERROR`。

操作之后，可以只看变化：

```text
✓ typed 30 chars
→ screen changed <1% (region 404,226 236x20)
Changes since your last look 1.0s ago (81 elements unchanged; their @ids still work):
  + @84 paragraph "Quarterly numbers look strong." [focused] (603,234)
  ~ @80 label "4 words, 30 characters" (281,730)
```

## 操作要“诚实”

一个点错了却被告知“✓”的 Agent，浪费的 token 比任何截图都多。所以：

- 每个操作完成后，都会等屏幕不再变化（浏览器里还会等页面加载完），再报告变化：新开或关闭的窗口、焦点、变化的区域。
- 文本目标是严格匹配的：点 "Delete" 永远不会点到 "Delete all"。找不到时直接失败，并列出最接近的候选。
- `fill` 只往文本框里输入，`select` 会重新读取下拉框的值来确认，未知的按键名会报错。

## 省 token 的几个设计

| 方式 | token |
|---|---|
| 1280×800 截图 | ~1,365 |
| `screenshot(detail="low")`，半尺寸 | ~341 |
| `act(observe="crop")`，只截变化的区域 | ~200 |
| LibreOffice 窗口的 `see` | ~920 |
| 打完一句话后的 `see(changes=true)` | ~80 |
| 终端的 `see` | ~50–90 |
| 工具定义：9 个工具 / 精简模式下的一个 `computer` 工具 | ~3,300 / ~450 |

此外，代码模式 `script` 直接在桌面里运行 Python（`click`、`write`、`key`、`see`、`cells` 等），循环和数据录入只需要一次调用，只返回程序打印的内容。任务跑通之后，还可以导出成宏（一段 Python 脚本），以后不需要模型就能重放。

## 轻量化

- 没有桌面环境，也没有 VNC：每个桌面只运行 Xvfb、JWM 窗口管理器、D-Bus / AT-SPI 和一个小小的 Python agent。
- 共享镜像层：profile 层层继承（`base → browser → office → data`），十个桌面在磁盘和 page cache 里共用一份基础镜像。
- 闲置冻结：没人用、也没人看的桌面会被 cgroup freezer 暂停（0% CPU），下一次调用约 0.2 秒恢复。
- 按需加载：无障碍库在第一次 `see` 时才加载；实时画面只在有人看、而且屏幕有变化时才推帧。
- 关闭动画、平滑滚动和光标闪烁：既省 CPU，又能让“屏幕已稳定”的判断更准确。

在一台 2 vCPU 的虚拟机上：每个 profile 都能在 1.2–1.8 秒内就绪，空闲内存 54–105 MB，3 个桌面并行启动用时 3.0 秒。可以用 `python scripts/bench.py` 复现。

## 怎么接入

安装（需要 Docker、OrbStack 或 Podman）：

```bash
curl -fsSL https://raw.githubusercontent.com/apophisss/minion/main/install.sh | sh
```

脚本会安装 `minion` 命令，然后运行 `minion setup`：检查 Docker、下载桌面镜像，并用 `minion connect` 把 Minion 接入你电脑上的 Agent 应用（Claude Desktop、Claude Code、Cursor、VS Code、Gemini CLI、Codex、LM Studio、opencode、OpenClaw 等）。其他 MCP 客户端用这段配置即可：

```json
{ "mcpServers": { "minion": { "command": "uvx", "args": ["minion-desktop", "mcp"] } } }
```

自己写 Agent 循环的话，任何兼容 OpenAI Chat Completions 的接口都可以（包括 Ollama、vLLM 运行的本地模型）：

```python
from openai import OpenAI
from minion.tools import Toolkit

tk = Toolkit()
client = OpenAI()  # 或 OpenAI(base_url="http://localhost:11434/v1", api_key="ollama") 使用本地模型
messages = [{"role": "user", "content": "On a research desktop, find the population of Iceland on Wikipedia."}]
while True:
    msg = (
        client.chat.completions.create(model="YOUR-MODEL", messages=messages, tools=tk.definitions("openai"))
        .choices[0]
        .message
    )
    messages.append(msg)
    if not msg.tool_calls:
        break
    messages += tk.run_calls(msg.tool_calls)  # 执行所有工具调用，返回要发回给模型的消息
print(msg.content)
```

镜像托管在 ghcr.io。如果拉取失败，Minion 会用内置的构建配方在本地构建（第一次需要几分钟）；也可以设置 `MINION_REGISTRY` 指向别的镜像仓库。

## 安全边界

- 每个桌面都是独立的无特权容器，默认不挂载宿主机目录；宿主机通过 `docker exec` 访问，桌面里没有监听任何端口。
- `--offline` 断网，`--memory` 和 `--cpus` 限制资源。
- HTTP 服务器只绑定 `127.0.0.1`，需要随机 token，并拒绝跨站请求和 DNS rebinding。
- 和你电脑之间的文件传输只限于一个文件夹。
- 容器内的用户有免密 `sudo`，方便 Agent 装软件。屏幕上的内容一律当作不可信输入，别把凭据放进桌面，登录、支付这类操作交给人：Agent 可以发起交接，等你在实时画面里操作完、点 Done 再继续。

## 怎么检验的

发布前，我让 AI Agent 用 Minion 完成了 93 个日常电脑任务：网页表单、Office 文档、文件管理器、计算器、网页邮件加电子表格的多应用流程、终端和 vim、GIMP，以及 Wine 里的 Windows 程序。每一次调用都记录下来，每个 Agent 都写下了卡住它的地方。按这些记录修复之后，再让新的 Agent 做同样的 93 个任务：调用次数从 491 降到 339（少 31%），失败的调用从 28 降到 14，输出的 token 从 156,272 降到 99,769（少 36%），两次 93 个任务全部完成。任务、测试网站和脚本都在仓库的 `scripts/scenarios` 里。

## 局限

- 没有 GPU，纯软件渲染（llvmpipe / SwiftShader）。
- `windows` profile 只支持 x86-64；Wine 窗口只能靠 OCR 读，偶尔会认错字符、漏掉图标。
- macOS 和 Windows 上需要 Docker Desktop、OrbStack 或 Podman 这类容器引擎。Linux 上可以不用 Docker 直接跑，但那样就没有隔离。
- 各个 Agent 框架的接入示例只验证到“加载工具”这一步，模型那一侧没有逐一跑过。

## 最后

Minion 采用 MIT 协议，宿主端是约 1 万行纯 Python 标准库代码，零依赖。欢迎试用、提 Issue 和 PR，特别是新的 profile、对某个应用更好的 `see` 输出，以及更多客户端的接入示例。

- GitHub：https://github.com/apophisss/minion
- 中文 README：https://github.com/apophisss/minion/blob/main/README.zh-CN.md
- 网站：https://apophisss.github.io/minion/
````
