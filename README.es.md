<p align="center"><a href="README.md">English</a> · <a href="README.zh-CN.md">简体中文</a> · <a href="README.zh-TW.md">繁體中文</a> · <a href="README.ko.md">한국어</a> · <a href="README.ja.md">日本語</a> · <a href="README.he.md">עברית</a> · Español</p>

<p align="center">
  <img src="docs/assets/hero.png" alt="Minion: escritorios instantáneos para agentes de IA" width="100%">
</p>

<h3 align="center">Dale a cada agente de IA su propia computadora.</h3>

<p align="center">
  Escritorios Linux ultraligeros (oficina, desarrollo, investigación, navegador, datos, apps de Windows) que cualquier agente puede usar:<br>
  Claude, ChatGPT, Gemini, Cursor, VS Code, LangChain, tu propio código o un modelo que corre en tu portátil.<br>
  Los agentes leen la pantalla como texto, actúan por lotes o con código, y usan cualquier programa o sitio web.
</p>

> Esta página es una versión resumida del [README](README.md) en inglés. Para más detalle y las novedades, consulta la documentación en inglés.

## Qué es Minion

Minion le da a un agente de IA una computadora propia en lugar de la tuya. Cada escritorio es una computadora Linux real dentro de un contenedor pequeño y sin privilegios, que por defecto no monta ninguna carpeta de tu equipo. El agente lee la pantalla como texto con `see` y hace clic o escribe con `act` o `script`. Cuando terminas, basta con eliminar el escritorio, y antes de un paso arriesgado puedes clonarlo con `fork`. Es más seguro que dejar que un agente controle directamente tu computadora.

- **🖥️ Cualquier programa, cualquier sitio web.** Navegadores, LibreOffice, IDE, terminales, diálogos de archivos e instaladores, y también programas de Windows mediante Wine. Abre cualquier app por su nombre y se instala la primera vez (`open gimp`); las apps web se abren en el navegador (`open gmail`). Con `menu`, `path` y `read` el agente maneja directamente los menús, los diálogos de archivos y el contenido de los documentos.
- **🧠 La pantalla, como texto.** `see` convierte cualquier ventana en una lista de controles con **`@id` estables**, tomados del árbol de accesibilidad y con OCR como respaldo: `@12 button "Save" (210,62)`. Las páginas web, los editores, las terminales y las hojas de cálculo (`A1: value`) también salen como texto exacto.
- **🎯 Acciones honestas.** Cada acción espera a que la pantalla se estabilice y te dice qué cambió. Si el texto que indicas no está realmente en pantalla, falla y muestra los candidatos más cercanos en lugar de hacer clic en otra cosa.
- **🪙 Diseñado para ahorrar tokens.** Recibes diferencias en lugar de volver a leer todo (`see(changes=true)`: unos 60 tokens en vez de unos 900). El **modo código** ejecuta un bucle de 50 pasos de GUI en una sola llamada, y el **modo compacto** reduce las definiciones de herramientas de unos 2.100 tokens a 230.
- **🪶 Ultraligero.** Un contenedor pequeño por escritorio, sin VNC ni entorno de escritorio. Está listo en unos 1,5 s y en reposo usa unos 60 MB. Los escritorios inactivos se congelan automáticamente (0 % de CPU) y despiertan en unos 0,2 s.
- **🔌 Funciona con cualquier agente.** MCP (local o remoto), function calling para OpenAI, Anthropic, Gemini y modelos locales, HTTP, una CLI y un Agent Skill, SDK de Python y TypeScript, y adaptadores nativos para el computer use de **Claude, OpenAI y Gemini**.
- **🙋 Las personas pueden intervenir cuando quieran.** Una vista en vivo en el navegador te permite tomar el control con un clic. El agente puede delegarte tareas como iniciar sesión y esperar a que pulses *Done*. Todas las acciones se graban y se pueden exportar como un script de Python que las repite sin ningún modelo.
- **📦 Cero dependencias.** El lado del anfitrión usa solo la biblioteca estándar de Python. Los escritorios corren en Docker o Podman (macOS, Windows, Linux).

## Primeros pasos

Solo necesitas [Docker](https://docs.docker.com/get-docker/) (u OrbStack o Podman). Después, elige una opción:

**1. Con un clic** desde tu app de IA:

[![Download the Claude Desktop extension](https://img.shields.io/badge/Claude_Desktop-Download_extension-D97757?style=flat-square&logo=claude&logoColor=white)](https://github.com/apophisss/minion/releases/latest/download/minion.mcpb)
[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_Minion-0098FF?style=flat-square)](https://insiders.vscode.dev/redirect/mcp/install?name=minion&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D)
[![Add to Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/install-mcp?name=minion&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtaW5pb24tZGVza3RvcCIsIm1jcCJdfQ%3D%3D)
[![Install in Visual Studio](https://img.shields.io/badge/Visual_Studio-Install_Minion-C16FDE?style=flat-square)](https://vs-open.link/mcp-install?%7B%22name%22%3A%22minion%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D)
[![Add to LM Studio](https://files.lmstudio.ai/deeplink/mcp-install-light.svg)](https://lmstudio.ai/install-mcp?name=minion&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtaW5pb24tZGVza3RvcCIsIm1jcCJdfQ%3D%3D)
[![Install in Goose](https://goose-docs.ai/img/extension-install-dark.svg)](https://goose-docs.ai/extension?cmd=uvx&arg=minion-desktop&arg=mcp&timeout=900&id=minion&name=Minion&description=Linux%20desktops%20that%20agents%20read%20as%20text%20and%20control)
[![Add to Kiro](https://kiro.dev/images/add-to-kiro.svg)](https://kiro.dev/launch/mcp/add?name=minion&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D)

Claude Code: `claude plugin marketplace add apophisss/minion && claude plugin install minion@minion`. Los botones usan [uv](https://docs.astral.sh/uv/) para iniciar Minion. La extensión de Claude Desktop no necesita nada más.

**2. Con una sola línea** que instala Minion y lo conecta con todas las apps de IA de tu computadora (Claude Desktop, Claude Code, Cursor, VS Code, Windsurf/Devin, Gemini CLI, Codex, LM Studio, Cline, Kiro):

```bash
curl -fsSL https://raw.githubusercontent.com/apophisss/minion/main/install.sh | sh        # macOS, Linux
```

```powershell
irm https://raw.githubusercontent.com/apophisss/minion/main/install.ps1 | iex             # Windows
```

Termina ejecutando `minion setup`, que comprueba Docker, prepara un escritorio y ejecuta `minion connect`. Puedes volver a ejecutar cualquiera de los dos comandos cuando quieras.

**3. Desde ChatGPT, Claude.ai o Le Chat** en el navegador: ejecuta `minion share` y pega la URL que muestra en la configuración de conectores de la app ([cómo hacerlo](docs/remote.md), en inglés).

Después solo tienes que pedírselo: *"Crea un escritorio office, escribe en Writer un resumen de una página sobre las cifras del tercer trimestre y guárdalo como brief.docx."* Todas las formas de instalar están en [docs/install.md](docs/install.md) (en inglés).

<p align="center"><img src="docs/assets/demo.gif" alt="Un agente buscando en Wikipedia en un escritorio de Minion, grabado con el registrador de vuelo de Minion" width="720"></p>
<p align="center"><sub>Un agente en un escritorio <code>research</code>. Este GIF se hizo con el registrador de vuelo integrado de Minion (<code>minion replay -o demo.gif</code>).</sub></p>

## Conectar agentes

`minion connect` busca las apps de agentes que hay en tu computadora (Claude Desktop, Claude Code, Cursor, VS Code, Devin Desktop/Windsurf, Gemini CLI, Codex, LM Studio, Cline, Kiro, Zed) y añade el servidor MCP de Minion a la configuración de cada una. Solo combina una entrada llamada `minion`, hace una copia de seguridad del archivo antes de modificarlo y da el mismo resultado por mucho que lo ejecutes.

```bash
minion connect              # busca tus apps y te deja elegir cuáles conectar
minion connect --list       # muestra todas las apps, sus archivos de configuración y si ya están conectadas
minion connect --dry-run    # muestra los cambios como diff, sin aplicarlos
minion connect --remove     # quita Minion
minion connect --compact    # conecta solo la herramienta `computer`, con el mínimo de contexto
```

Cualquier otro cliente MCP: Minion es un servidor MCP por stdio. La mayoría de las apps aceptan este JSON (el `mcp.json` propio de VS Code usa la clave `servers`):

```json
{ "mcpServers": { "minion": { "command": "uvx", "args": ["minion-desktop", "mcp"] } } }
```

También puedes añadirlo con el comando de cada herramienta (Codex necesita un tiempo de espera mayor para la primera descarga de la imagen del escritorio; consulta [docs/install.md](docs/install.md#codex)):

```bash
claude mcp add --scope user minion -- uvx minion-desktop mcp    # Claude Code
codex mcp add minion -- uvx minion-desktop mcp                  # Codex
gemini mcp add --scope user minion uvx minion-desktop mcp       # Gemini CLI
```

También hay opciones sin MCP: [function calling](docs/agents.md#without-mcp-function-calling-with-any-model) (cualquier modelo, incluidos los locales) · [API HTTP](docs/http-api.md) · [CLI](docs/cli.md) y Agent Skill · [Python](docs/python.md) y [TypeScript](clients/typescript) · [computer use de Claude](docs/computer-use.md) · [computer use de OpenAI y Gemini](docs/computer-use-openai-gemini.md) · [frameworks de agentes](docs/integrations.md).

## Ejemplo: un recorrido desde la shell

Cualquier agente con una terminal (Claude Code, Codex CLI, Aider, Open Interpreter, Goose) puede usar la CLI directamente, y `minion skill --install` le enseña cómo:

```bash
minion up research
minion open en.wikipedia.org             # espera a que la página termine de cargar
minion fill "Search Wikipedia" "Ada Lovelace" && minion key Return
minion wait-for "Analytical Engine"      # indica dónde vio el texto
minion see --full                        # lee el artículo completo como texto
minion shot -o page.png --marks          # captura de pantalla con los @id dibujados
minion cp :~/Documents/notes.md .        # copia archivos hacia afuera (y hacia adentro)
```

## Perfiles

| Perfil | Qué incluye | Descarga | RAM en reposo |
|---|---|---|---|
| 🌐 `browser` | Firefox con uBlock Origin (bloquea anuncios, rastreadores, avisos de cookies y ventanas emergentes de boletines); las descargas van directo a `~/Downloads` | 352 MB | ~55–100 MB |
| 📄 `office` | LibreOffice Writer, Calc e Impress + editor de texto + gestor de archivos + Firefox + herramientas de PDF. Guarda en formatos de Microsoft por defecto | 511 MB | ~85 MB |
| 🛠️ `dev` | git, Python, Node.js, herramientas de compilación, el IDE Geany, una terminal que `see` puede leer, Firefox + Chromium | 703 MB | ~55 MB |
| 🔎 `research` | Firefox + `pdftotext`, `pandoc`, un editor de notas, Python con requests y BeautifulSoup | 410 MB | ~55 MB |
| 📊 `data` | `office` + pandas, NumPy, SciPy, matplotlib, seaborn, openpyxl, SQLite | 663 MB | ~105 MB |
| 🪟 `windows` | Wine 10 para programas de Windows `.exe`/`.msi` de 64 y 32 bits. Solo en anfitriones x86-64 ([documentación](docs/windows-apps.md)) | 707 MB | ~56 MB (unos 270 MB con un programa abierto) |
| 🧩 `base` | Servidor X, gestor de ventanas, terminal y el agente. La base sobre la que construir los demás | 187 MB | ~65 MB |

Un perfil propio es un archivo TOML de 5 líneas en `~/.config/minion/profiles/`. Se construye automáticamente la primera vez que lo usas. Más detalles en [docs/profiles.md](docs/profiles.md) (en inglés).

## Seguridad

Cada escritorio es un contenedor sin privilegios y, por defecto, sin montajes del anfitrión. Usa `--offline` para cortar el acceso a la red, y `--memory` y `--cpus` para limitar los recursos. El servidor HTTP escucha solo en `127.0.0.1` y exige un token aleatorio. El usuario del escritorio tiene `sudo` sin contraseña dentro del contenedor, así que los agentes pueden instalar software. Trata todo lo que aparece en pantalla como entrada no fiable (inyección de prompts) y no pongas credenciales en los escritorios. Más detalles en [SECURITY.md](SECURITY.md) (en inglés).

## Documentación (en inglés)

[Sitio web](https://apophisss.github.io/minion/) · [Instalación](docs/install.md) · [Conectar tus apps](docs/connect.md) · [MCP remoto](docs/remote.md) · [Diseño](docs/design.md) · [Agentes y MCP](docs/agents.md) · [Integraciones](docs/integrations.md) · [CLI](docs/cli.md) · [Python](docs/python.md) · [API HTTP](docs/http-api.md) · [computer use de Claude](docs/computer-use.md) · [computer use de OpenAI y Gemini](docs/computer-use-openai-gemini.md) · [Perfiles](docs/profiles.md) · [Apps de Windows](docs/windows-apps.md) · [Arquitectura](docs/architecture.md) · [Preguntas frecuentes](docs/faq.md)

Las issues y los pull requests son bienvenidos. Consulta [CONTRIBUTING.md](CONTRIBUTING.md).

## Licencia

[MIT](LICENSE). Los escritorios incluyen software de código abierto bajo sus propias licencias (Debian, Firefox, LibreOffice, Wine, …).
