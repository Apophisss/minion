<p align="center"><a href="README.md">English</a> · <a href="README.zh-CN.md">简体中文</a> · <a href="README.zh-TW.md">繁體中文</a> · <a href="README.ko.md">한국어</a> · <a href="README.ja.md">日本語</a> · עברית</p>

<p align="center">
  <img src="docs/assets/hero.png" alt="Minion: שולחנות עבודה מיידיים לסוכני AI" width="100%">
</p>

<h3 align="center" dir="rtl">תנו לכל סוכן AI מחשב משלו.</h3>

<p align="center" dir="rtl">
  שולחנות עבודה קלילים של Linux (משרד, פיתוח, מחקר, דפדפן, נתונים, אפליקציות Windows) שכל סוכן יכול להשתמש בהם:<br>
  Claude, ChatGPT, Gemini, Cursor, VS Code, LangChain, הקוד שלכם, או מודל שרץ על הלפטופ שלכם.<br>
  הסוכנים קוראים את המסך כטקסט, פועלים בקבוצות של פעולות או בקוד, ומשתמשים בכל תוכנה ובכל אתר.
</p>

<div dir="rtl">

> זהו תרגום מקוצר של ה-[README](README.md) באנגלית. התיעוד המלא והעדכני נמצא באנגלית, והוא הגרסה הקובעת.

## מה זה Minion?

הפרויקט Minion נותן לסוכן AI מחשב משלו, במקום המחשב שלכם. כל שולחן עבודה הוא מחשב Linux אמיתי שרץ בקונטיינר קטן ובלי הרשאות מיוחדות (unprivileged), ובברירת המחדל אין לו גישה לאף תיקייה במחשב המארח. הסוכן קורא את המסך כטקסט עם ‎`see`‎, ולוחץ ומקליד עם ‎`act`‎ או ‎`script`‎. בסוף העבודה אפשר פשוט למחוק את שולחן העבודה, ולפני צעד מסוכן אפשר לשכפל אותו עם ‎`fork`‎. זה בטוח יותר מלתת לסוכן לעבוד על המחשב שלכם.

- **🖥️ כל תוכנה, כל אתר.** דפדפנים, LibreOffice, סביבות פיתוח, טרמינלים, חלונות לבחירת קבצים ותוכניות התקנה, וגם תוכנות Windows דרך Wine. כל אפליקציה נפתחת לפי השם שלה ומותקנת בפעם הראשונה (‎`open gimp`‎), אפליקציות ווב נפתחות בדפדפן (‎`open gmail`‎), והפקודות ‎`menu`‎, ‎`path`‎ ו-‎`read`‎ מגיעות ישר לתפריטים, לחלונות השמירה והפתיחה ולתוכן של מסמכים.
- **🧠 המסך כטקסט.** הפקודה ‎`see`‎ מציגה את הרכיבים שבחלון כרשימה, ולכל רכיב מזהה קבוע (‎`@id`‎) מתוך עץ הנגישות, עם OCR כגיבוי: ‎`@12 button "Save" (210,62)`‎. גם דפי אינטרנט, עורכים, טרמינלים וגיליונות אלקטרוניים (‎`A1: value`‎) יוצאים כטקסט מדויק.
- **🎯 פעולות אמינות.** כל פעולה מחכה שהמסך יתייצב ומדווחת מה השתנה. אם יעד טקסטואלי לא מופיע על המסך, הפעולה נכשלת ומציעה את המועמדים הקרובים ביותר, במקום ללחוץ על משהו אחר.
- **🪙 בנוי לחסוך בטוקנים.** במקום לקרוא את המסך מחדש מקבלים רק את ההבדלים (‎`see(changes=true)`‎: בערך 60 טוקנים במקום בערך 900). מצב קוד מריץ לולאת GUI של 50 צעדים בקריאה אחת, והמצב הקומפקטי מקטין את הגדרות הכלים מכ-2,100 טוקנים ל-230.
- **🪶 קל משקל.** קונטיינר קטן אחד לכל שולחן עבודה, בלי VNC ובלי סביבת שולחן עבודה. שולחן עבודה מוכן תוך כ-1.5 שניות וצורך כ-60MB זיכרון במנוחה, ושולחן עבודה לא פעיל מוקפא אוטומטית (0% CPU) ומתעורר תוך כ-0.2 שניות.
- **🔌 עובד עם כל סוכן.** MCP (מקומי או מרוחק), function calling ל-OpenAI, ל-Anthropic, ל-Gemini ולמודלים מקומיים, HTTP, CLI ו-Agent Skill, ערכות SDK ל-Python ול-TypeScript, ו-computer use של Claude, של OpenAI ושל Gemini.
- **🙋 בני אדם נשארים בתמונה.** בתצוגה החיה בדפדפן אפשר לקחת שליטה בלחיצה אחת, והסוכן יכול להעביר אליכם משימה כמו התחברות לחשבון ולחכות שתלחצו *Done*. כל פעולה מוקלטת, ואפשר לייצא את הסשן לסקריפט Python שמשחזר אותו בלי מודל בכלל.
- **📦 אפס תלויות.** הצד של המחשב המארח כתוב בספרייה הסטנדרטית של Python בלבד. שולחנות העבודה רצים ב-Docker או ב-Podman (macOS, Windows, Linux).

## איך מתחילים

כל מה שצריך הוא [Docker](https://docs.docker.com/get-docker/) (או OrbStack, או Podman). אחר כך בוחרים אחת מהדרכים:

**1. בלחיצה אחת** באפליקציית ה-AI שלכם:

</div>

[![Download the Claude Desktop extension](https://img.shields.io/badge/Claude_Desktop-Download_extension-D97757?style=flat-square&logo=claude&logoColor=white)](https://github.com/apophisss/minion/releases/latest/download/minion.mcpb)
[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_Minion-0098FF?style=flat-square)](https://insiders.vscode.dev/redirect/mcp/install?name=minion&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D)
[![Add to Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/install-mcp?name=minion&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtaW5pb24tZGVza3RvcCIsIm1jcCJdfQ%3D%3D)
[![Install in Visual Studio](https://img.shields.io/badge/Visual_Studio-Install_Minion-C16FDE?style=flat-square)](https://vs-open.link/mcp-install?%7B%22name%22%3A%22minion%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D)
[![Add to LM Studio](https://files.lmstudio.ai/deeplink/mcp-install-light.svg)](https://lmstudio.ai/install-mcp?name=minion&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtaW5pb24tZGVza3RvcCIsIm1jcCJdfQ%3D%3D)
[![Install in Goose](https://goose-docs.ai/img/extension-install-dark.svg)](https://goose-docs.ai/extension?cmd=uvx&arg=minion-desktop&arg=mcp&timeout=900&id=minion&name=Minion&description=Linux%20desktops%20that%20agents%20read%20as%20text%20and%20control)
[![Add to Kiro](https://kiro.dev/images/add-to-kiro.svg)](https://kiro.dev/launch/mcp/add?name=minion&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D)

<div dir="rtl">

ב-Claude Code מתקינים את הפלאגין עם הפקודה הבאה. הכפתורים מפעילים את Minion עם [uv](https://docs.astral.sh/uv/), והתוסף ל-Claude Desktop לא צריך שום דבר נוסף.

</div>

```bash
claude plugin marketplace add apophisss/minion && claude plugin install minion@minion
```

<div dir="rtl">

**2. בשורה אחת** שמתקינה את Minion ומחברת את כל אפליקציות ה-AI במחשב (Claude Desktop, Claude Code, Cursor, VS Code, Windsurf/Devin, Gemini CLI, Codex, LM Studio, Cline, Kiro):

</div>

```bash
curl -fsSL https://raw.githubusercontent.com/apophisss/minion/main/install.sh | sh        # macOS, Linux
```

```powershell
irm https://raw.githubusercontent.com/apophisss/minion/main/install.ps1 | iex             # Windows
```

<div dir="rtl">

ההתקנה מסתיימת בהרצה של ‎`minion setup`‎, שבודק את Docker, מכין שולחן עבודה ומריץ את ‎`minion connect`‎. אפשר להריץ כל אחת מהפקודות שוב מתי שרוצים.

**3. מ-ChatGPT, מ-Claude.ai או מ-Le Chat** בדפדפן: מריצים ‎`minion share`‎, ומדביקים את הכתובת שהפקודה מדפיסה בהגדרות ה-connectors של האפליקציה ([הסבר](docs/remote.md), באנגלית).

ואז פשוט מבקשים: *"צור שולחן עבודה מסוג office, כתוב ב-Writer תקציר של עמוד אחד על המספרים שלנו ברבעון השלישי, ושמור אותו בשם brief.docx."* כל דרכי ההתקנה מפורטות ב-[docs/install.md](docs/install.md) (באנגלית).

</div>

<p align="center"><img src="docs/assets/demo.gif" alt="סוכן מחפש בוויקיפדיה על שולחן עבודה של Minion, בהקלטה של הקופסה השחורה של Minion" width="720"></p>
<p align="center" dir="rtl"><sub>סוכן שעובד על שולחן עבודה מסוג <code>research</code>. את ה-GIF יצרה הקופסה השחורה (flight recorder) המובנית של Minion, עם הפקודה <code>minion replay -o demo.gif</code>.</sub></p>

<div dir="rtl">

## חיבור הסוכנים שלכם

הפקודה ‎`minion connect`‎ מוצאת את אפליקציות הסוכנים במחשב (Claude Desktop, Claude Code, Cursor, VS Code, Devin Desktop/Windsurf, Gemini CLI, Codex, LM Studio, Cline, Kiro, Zed) ומוסיפה את שרת ה-MCP של Minion להגדרות שלהן. היא ממזגת רשומה אחת בשם ‎`minion`‎, מגבה את הקובץ לפני שהיא משנה אותו, והרצה חוזרת לא משנה כלום.

</div>

```bash
minion connect              # find your apps and choose which ones to connect
minion connect --list       # every app, its config file, and whether it is connected
minion connect --dry-run    # show the change as a diff, without making it
minion connect --remove     # take Minion out again
minion connect --compact    # one `computer` tool: the smallest context
```

<div dir="rtl">

כל לקוח MCP אחר יכול להריץ את Minion כשרת stdio. רוב האפליקציות מקבלות את ה-JSON הזה (בקובץ ‎`mcp.json`‎ של VS Code עצמו, המפתח נקרא ‎`servers`‎):

</div>

```json
{ "mcpServers": { "minion": { "command": "uvx", "args": ["minion-desktop", "mcp"] } } }
```

<div dir="rtl">

אפשר גם להוסיף אותו בפקודה של הכלי עצמו (ב-Codex צריך להגדיל את זמני ההמתנה לקראת ההורדה הראשונה של אימג', ראו [docs/install.md](docs/install.md#codex)):

</div>

```bash
claude mcp add --scope user minion -- uvx minion-desktop mcp    # Claude Code
codex mcp add minion -- uvx minion-desktop mcp                  # Codex
gemini mcp add --scope user minion uvx minion-desktop mcp       # Gemini CLI
```

<div dir="rtl">

אפשר גם בלי MCP: [function calling](docs/agents.md#without-mcp-function-calling-with-any-model) (כל מודל, כולל מודלים מקומיים) · [HTTP API](docs/http-api.md) · [CLI](docs/cli.md) ו-Agent Skill · [Python](docs/python.md) ו-[TypeScript](clients/typescript) · [computer use של Claude](docs/computer-use.md) · [computer use של OpenAI ו-Gemini](docs/computer-use-openai-gemini.md) · [פריימוורקים לסוכנים](docs/integrations.md).

## דוגמה: סיור קצר מה-shell

כל סוכן עם טרמינל (Claude Code, Codex CLI, Aider, Open Interpreter, Goose) יכול להשתמש ב-CLI ישירות, והפקודה ‎`minion skill --install`‎ מלמדת אותו איך:

</div>

```bash
minion up research
minion open en.wikipedia.org             # waits until the page has loaded
minion fill "Search Wikipedia" "Ada Lovelace" && minion key Return
minion wait-for "Analytical Engine"      # says where it saw the text
minion see --full                        # read the article as text
minion shot -o page.png --marks          # a screenshot with @ids drawn on it
minion cp :~/Documents/notes.md .        # copy files out (and in)
```

<div dir="rtl">

## פרופילים

| פרופיל | מה יש בפנים | הורדה | זיכרון במנוחה |
|---|---|---|---|
| 🌐 ‎`browser`‎ | הדפדפן Firefox עם uBlock Origin (נגד פרסומות, טראקרים, באנרים של עוגיות וחלונות קופצים של ניוזלטרים), והורדות שנשמרות ישר ב-‎`~/Downloads`‎ | 352 MB | כ-‎55–100 MB |
| 📄 ‎`office`‎ | התוכנות Writer, Calc ו-Impress של LibreOffice, עורך טקסט, מנהל קבצים, Firefox וכלי PDF. שומר כברירת מחדל בפורמטים של Microsoft | 511 MB | כ-85 MB |
| 🛠️ ‎`dev`‎ | הכלים git, Python, Node.js וכלי build, סביבת הפיתוח Geany, טרמינל ש-‎`see`‎ יודע לקרוא, Firefox ו-Chromium | 703 MB | כ-55 MB |
| 🔎 ‎`research`‎ | הדפדפן Firefox עם ‎`pdftotext`‎ ו-‎`pandoc`‎, עורך לרשימות, ו-Python עם requests ו-BeautifulSoup | 410 MB | כ-55 MB |
| 📊 ‎`data`‎ | כל מה שיש ב-‎`office`‎, ועוד pandas, NumPy, SciPy, matplotlib, seaborn, openpyxl ו-SQLite | 663 MB | כ-105 MB |
| 🪟 ‎`windows`‎ | סביבת Wine 10 לתוכנות Windows של 64 ו-32 ביט (‎`.exe`‎ ו-‎`.msi`‎). רק במחשבי x86-64 ([תיעוד](docs/windows-apps.md)) | 707 MB | כ-56 MB (כ-270 MB עם תוכנה פתוחה) |
| 🧩 ‎`base`‎ | שרת X, מנהל חלונות, טרמינל והסוכן. הבסיס שכל שאר הפרופילים בנויים עליו | 187 MB | כ-65 MB |

פרופיל משלכם הוא קובץ TOML של חמש שורות בתיקייה ‎`~/.config/minion/profiles/`‎, שנבנה אוטומטית בפעם הראשונה שמשתמשים בו. פרטים ב-[docs/profiles.md](docs/profiles.md) (באנגלית).

## אבטחה

כל שולחן עבודה הוא קונטיינר בלי הרשאות מיוחדות, ובברירת המחדל בלי גישה לתיקיות של המחשב המארח. הדגל ‎`--offline`‎ מנתק את הרשת, והדגלים ‎`--memory`‎ ו-‎`--cpus`‎ מגבילים משאבים. שרת ה-HTTP מאזין רק ל-‎`127.0.0.1`‎ ודורש טוקן אקראי. למשתמש שבתוך שולחן העבודה יש ‎`sudo`‎ בלי סיסמה בתוך הקונטיינר, כדי שסוכנים יוכלו להתקין תוכנות. התייחסו לכל מה שמופיע על המסך כקלט לא מהימן (prompt injection), ואל תכניסו פרטי התחברות לשולחנות עבודה. פרטים ב-[SECURITY.md](SECURITY.md) (באנגלית).

## תיעוד (באנגלית)

[אתר](https://apophisss.github.io/minion/) · [התקנה](docs/install.md) · [חיבור אפליקציות](docs/connect.md) · [MCP מרוחק](docs/remote.md) · [עקרונות התכנון](docs/design.md) · [סוכנים ו-MCP](docs/agents.md) · [אינטגרציות](docs/integrations.md) · [CLI](docs/cli.md) · [Python](docs/python.md) · [HTTP API](docs/http-api.md) · [computer use של Claude](docs/computer-use.md) · [computer use של OpenAI ו-Gemini](docs/computer-use-openai-gemini.md) · [פרופילים](docs/profiles.md) · [אפליקציות Windows](docs/windows-apps.md) · [ארכיטקטורה](docs/architecture.md) · [שאלות נפוצות](docs/faq.md)

נשמח ל-Issues ול-Pull Requests; ראו [CONTRIBUTING.md](CONTRIBUTING.md).

## רישיון

הפרויקט מופץ ברישיון [MIT](LICENSE). שולחנות העבודה מכילים תוכנות קוד פתוח ברישיונות שלהן (Debian, Firefox, LibreOffice, Wine ועוד).

</div>
