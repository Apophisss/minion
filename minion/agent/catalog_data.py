"""The app catalog: how to install, launch and use the apps an agent asks for by name.

Pure data, standard library only (it is copied into every desktop with the rest of the agent).

Every entry has an ``id`` (lowercase ``[a-z0-9-]``), a display ``name``, ``aliases`` (other lowercase names
people type; unique across the catalog) and exactly ONE way to get the app:

- ``apt``: Debian 13 (trixie) packages, installed with Recommends (what ``minion-install`` does).
- ``deb``: a stable "latest" download URL per CPU architecture (``amd64``/``arm64``) for a .deb, an
  .AppImage or a .tar.gz. Some URLs have no file extension (the type shows after redirects or in
  Content-Disposition). A .tar.gz is unpacked to ``~/apps/<id>``, so ``command`` is the full path.
- ``github``: the newest GitHub release of ``repo``; per architecture, a regex that matches exactly one asset.
- ``url``: a web app, opened in the desktop's browser.
- ``unavailable``: the app does not run here; ``alternatives`` lists ids of entries that do the job.

Installable entries have a ``command`` (the launch command, with the flags the app needs in a container)
and usually ``size_mb`` (approximate download from a bare base desktop, dependencies included). ``tips``
(at most 300 characters) gives an agent the most useful keys and, where one exists, a headless/CLI route.

Checked on 2026-10-15 against Debian 13 and the vendors' download URLs. Electron and Chromium apps need
``--no-sandbox`` in a container (they abort without it) and ``--force-renderer-accessibility`` so their UI
shows up in the accessibility tree.
"""

APPS: list[dict] = [
    # ---------------------------------------------------------------- office and documents
    {
        "id": "libreoffice",
        "name": "LibreOffice",
        "aliases": ["libre office", "soffice"],
        "apt": ["libreoffice-writer", "libreoffice-calc", "libreoffice-impress", "libreoffice-gtk3"],
        "command": "libreoffice",
        "tips": "Start Center: ctrl+o opens any document, or pick Writer, Calc or Impress. Convert headless (also "
        "while the GUI runs): soffice -env:UserInstallation=file:///tmp/lo --headless --convert-to pdf "
        "--outdir ~/out in.docx",
        "size_mb": 290,
    },
    {
        "id": "writer",
        "name": "LibreOffice Writer",
        "aliases": ["libreoffice writer", "libreoffice-writer", "lowriter"],
        "apt": ["libreoffice-writer", "libreoffice-gtk3"],
        "command": "libreoffice --writer",
        "tips": "ctrl+1/2/3 headings, ctrl+0 body text, ctrl+enter page break, ctrl+h find & replace, ctrl+f12 "
        "table, F5 Navigator, ctrl+shift+s save as. PDF: soffice -env:UserInstallation=file:///tmp/lo "
        "--headless --convert-to pdf in.docx",
        "size_mb": 280,
    },
    {
        "id": "calc",
        "name": "LibreOffice Calc",
        "aliases": ["libreoffice calc", "libreoffice-calc", "localc"],
        "apt": ["libreoffice-calc", "libreoffice-gtk3"],
        "command": "libreoffice --calc",
        "tips": "ctrl+shift+t Name Box (type A1:C10, Return), F2 edit cell, F4 toggles $ references, "
        "ctrl+shift+v paste special, ctrl+page down next sheet. CSV to XLSX: soffice "
        "-env:UserInstallation=file:///tmp/lo --headless --convert-to xlsx in.csv",
        "size_mb": 280,
    },
    {
        "id": "impress",
        "name": "LibreOffice Impress",
        "aliases": ["libreoffice impress", "libreoffice-impress", "loimpress"],
        "apt": ["libreoffice-impress", "libreoffice-gtk3"],
        "command": "libreoffice --impress",
        "tips": "ctrl+m new slide, F5 slideshow from the first slide, shift+F5 from the current one, Escape ends "
        "it. PDF: soffice -env:UserInstallation=file:///tmp/lo --headless --convert-to pdf deck.pptx",
        "size_mb": 270,
    },
    {
        "id": "draw",
        "name": "LibreOffice Draw",
        "aliases": ["libreoffice draw", "libreoffice-draw", "lodraw"],
        "apt": ["libreoffice-draw", "libreoffice-gtk3"],
        "command": "libreoffice --draw",
        "tips": "Edits PDFs: libreoffice --draw in.pdf (text becomes editable boxes), then File > Export As > "
        "Export as PDF. "
        "Headless: soffice -env:UserInstallation=file:///tmp/lo --headless --convert-to png drawing.odg",
        "size_mb": 270,
    },
    {
        "id": "math",
        "name": "LibreOffice Math",
        "aliases": ["libreoffice math", "libreoffice-math", "lomath"],
        "apt": ["libreoffice-math", "libreoffice-gtk3"],
        "command": "libreoffice --math",
        "tips": "Type markup in the Commands pane: a^2 + b^2 = c^2, sqrt{x}, {a} over {b}, "
        "sum from{i=1} to{n} x_i, int from a to b f(x) dx. The preview updates as you type.",
        "size_mb": 260,
    },
    {
        "id": "abiword",
        "name": "AbiWord",
        "aliases": [],
        "apt": ["abiword"],
        "command": "abiword",
        "tips": "Light word processor (.doc, .docx, .odt, .rtf). Convert headless: abiword --to=pdf in.docx "
        "writes in.pdf (--to-name=out.pdf picks the name).",
        "size_mb": 55,
    },
    {
        "id": "gnumeric",
        "name": "Gnumeric",
        "aliases": [],
        "apt": ["gnumeric"],
        "command": "gnumeric",
        "tips": "Spreadsheet (.xlsx, .ods, .csv). Convert headless: ssconvert in.xlsx out.csv "
        "(the output extension picks the format).",
        "size_mb": 260,
    },
    {
        "id": "scribus",
        "name": "Scribus",
        "aliases": [],
        "apt": ["scribus"],
        "command": "scribus",
        "tips": "Page layout (.sla). PDF: File > Export > Save as PDF. Python scripts: Script > Execute Script; "
        "batch: scribus -g -ns -py script.py doc.sla",
        "size_mb": 150,
    },
    {
        "id": "calibre",
        "name": "calibre",
        "aliases": [],
        "apt": ["calibre"],
        "command": "calibre",
        "tips": "E-book library. Without the GUI: ebook-convert in.epub out.pdf (epub, mobi, azw3, docx, pdf, "
        "txt...), ebook-meta book.epub, calibredb add book.epub, ebook-viewer book.epub.",
        "size_mb": 380,
    },
    {
        "id": "evince",
        "name": "Evince (Document Viewer)",
        "aliases": ["document viewer", "pdf viewer"],
        "apt": ["evince"],
        "command": "evince",
        "tips": "ctrl+f find, ctrl+l page number box, F9 side pane, ctrl+left/right rotate, F11 fullscreen, "
        "F5 presentation. Reading text is faster with pdftotext -layout in.pdf - (minion-install poppler-utils).",
        "size_mb": 60,
    },
    {
        "id": "okular",
        "name": "Okular",
        "aliases": [],
        "apt": ["okular"],
        "command": "okular",
        "tips": "PDF/EPUB viewer with annotations: F6 annotation toolbar (alt+1 highlight, alt+2 underline, "
        "alt+3 squiggle, alt+4 strike out), ctrl+g go to page, ctrl+f find, F7 side panel.",
        "size_mb": 250,
    },
    {
        "id": "xournalpp",
        "name": "Xournal++",
        "aliases": ["xournal", "xournal++"],
        "apt": ["xournalpp"],
        "command": "xournalpp",
        "tips": "Handwriting and PDF annotation: File > Annotate PDF, write on it, then File > Export as PDF; "
        "ctrl+s saves the .xopp notes. Headless: xournalpp --create-pdf=out.pdf notes.xopp",
        "size_mb": 140,
    },
    {
        "id": "pdfarranger",
        "name": "PDF Arranger",
        "aliases": ["pdf arranger", "pdf-arranger"],
        "apt": ["pdfarranger"],
        "command": "pdfarranger",
        "tips": "Merge, split and reorder PDF pages: ctrl+i imports another PDF, drag pages to reorder, Delete "
        "removes, ctrl+left/right rotates, ctrl+e exports the selected pages, ctrl+s saves.",
        "size_mb": 25,
    },
    # ---------------------------------------------------------------- text editors and files
    {
        "id": "mousepad",
        "name": "Mousepad",
        "aliases": ["text editor"],
        "apt": ["mousepad"],
        "command": "mousepad",
        "tips": "ctrl+f find, ctrl+r find & replace, ctrl+l go to line, ctrl+s save, ctrl+shift+s save as.",
        "size_mb": 15,
    },
    {
        "id": "gedit",
        "name": "gedit",
        "aliases": [],
        "apt": ["gedit"],
        "command": "gedit",
        "tips": "ctrl+f find, ctrl+h replace, ctrl+i go to line, ctrl+t new tab, ctrl+shift+s save as.",
        "size_mb": 245,
    },
    {
        "id": "kate",
        "name": "Kate",
        "aliases": [],
        "apt": ["kate"],
        "command": "kate",
        "tips": "ctrl+f find, ctrl+r replace, ctrl+g go to line, ctrl+shift+s save as.",
        "size_mb": 150,
    },
    {
        "id": "pcmanfm",
        "name": "PCManFM (file manager)",
        "aliases": ["file manager", "files"],
        "apt": ["pcmanfm"],
        "command": "pcmanfm",
        "tips": "ctrl+l types a path, ctrl+h shows hidden files, F2 renames, ctrl+t new tab, alt+up parent "
        "folder. Copy files in or out of the desktop with minion cp.",
        "size_mb": 75,
    },
    # ---------------------------------------------------------------- graphics and photos
    {
        "id": "gimp",
        "name": "GIMP",
        "aliases": ["gimp-3", "gnu image manipulation program"],
        "apt": ["gimp"],
        "command": "gimp",
        "tips": "ctrl+shift+e Export As (PNG/JPG; ctrl+s saves .xcf only), ctrl+shift+v paste as new image, "
        "ctrl+shift+j fit in window, shift+c crop, t text, Image > Scale Image. Batch: magick in.png "
        "-resize 50% out.jpg (minion-install imagemagick).",
        "size_mb": 90,
    },
    {
        "id": "inkscape",
        "name": "Inkscape",
        "aliases": [],
        "apt": ["inkscape"],
        "command": "inkscape",
        "tips": "ctrl+shift+e Export, ctrl+shift+d Document Properties, ctrl+shift+f Fill and Stroke, "
        "ctrl+shift+x XML editor; tools: s select, r rectangle, e ellipse, t text, b pen; 5 fits the page. "
        "Headless: inkscape --export-type=png in.svg (or --export-filename=out.pdf)",
        "size_mb": 105,
    },
    {
        "id": "krita",
        "name": "Krita",
        "aliases": [],
        "apt": ["krita"],
        "command": "krita",
        "tips": "Painting: e toggles eraser mode, Insert adds a paint layer; File > Export saves PNG/JPG. "
        "Headless: krita in.kra --export --export-filename out.png",
        "size_mb": 290,
    },
    {
        "id": "darktable",
        "name": "darktable",
        "aliases": [],
        "apt": ["darktable"],
        "command": "darktable",
        "tips": "RAW editor: l lighttable, d darkroom, ctrl+e exports the selected images with the current "
        "settings. Headless: darktable-cli in.CR2 out.jpg (an .xmp sidecar may go before the output).",
        "size_mb": 95,
    },
    {
        "id": "rawtherapee",
        "name": "RawTherapee",
        "aliases": ["raw therapee"],
        "apt": ["rawtherapee"],
        "command": "rawtherapee",
        "tips": "RAW developer. Headless: rawtherapee-cli -o out.jpg -c in.CR2 (-c comes last; -Y overwrites, "
        "-j90 sets JPEG quality).",
        "size_mb": 45,
    },
    {
        "id": "mypaint",
        "name": "MyPaint",
        "aliases": [],
        "apt": ["mypaint"],
        "command": "mypaint",
        "tips": "Painting on an endless canvas: ctrl+s saves .ora, ctrl+shift+s save as, ctrl+shift+e exports "
        "PNG/JPG and keeps working on the .ora.",
        "size_mb": 25,
    },
    {
        "id": "digikam",
        "name": "digiKam",
        "aliases": [],
        "apt": ["digikam"],
        "command": "digikam",
        "tips": "Photo manager. First start runs a setup wizard: pick the photo folder (e.g. ~/Pictures) and "
        "the SQLite database. Batch resize/convert: Tools > Batch Queue Manager.",
        "size_mb": 435,
    },
    {
        "id": "kolourpaint",
        "name": "KolourPaint",
        "aliases": [],
        "apt": ["kolourpaint"],
        "command": "kolourpaint",
        "tips": "Simple paint program like MS Paint: ctrl+e resize/scale, ctrl+u auto-crop, ctrl+r rotate, "
        "ctrl+i invert colors.",
        "size_mb": 140,
    },
    {
        "id": "drawing",
        "name": "Drawing",
        "aliases": ["gnome drawing"],
        "apt": ["drawing"],
        "command": "drawing",
        "tips": "Small paint app like MS Paint: ctrl+o open, ctrl+v pastes an image, ctrl+s save, ctrl+shift+s "
        "save as; tools are in the side bar.",
        "size_mb": 15,
    },
    {
        "id": "ristretto",
        "name": "Ristretto (image viewer)",
        "aliases": ["image viewer", "photo viewer"],
        "apt": ["ristretto"],
        "command": "ristretto",
        "tips": "space next image, BackSpace previous, ctrl+= fit to window, ctrl+0 actual size, ctrl+] rotate "
        "right, F11 fullscreen.",
        "size_mb": 35,
    },
    # ---------------------------------------------------------------- 3D and CAD
    {
        "id": "blender",
        "name": "Blender",
        "aliases": [],
        "apt": ["blender"],
        "command": "blender",
        "tips": "F12 render image, ctrl+F12 render animation, ctrl+s save, n sidebar. Software OpenGL here (slow "
        "viewport). Headless: blender -b in.blend -o /tmp/out_#### -f 1 (one frame), -a (animation), "
        "-P script.py (Python)",
        "size_mb": 255,
    },
    {
        "id": "freecad",
        "name": "FreeCAD",
        "aliases": ["free cad"],
        "apt": ["freecad"],
        "command": "freecad",
        "tips": "Parametric 3D CAD. Views: 0 isometric, 1 front, 2 top, 3 right; V then F fits all. Headless "
        "Python: freecadcmd script.py",
        "size_mb": 475,
    },
    {
        "id": "librecad",
        "name": "LibreCAD",
        "aliases": ["libre cad"],
        "apt": ["librecad"],
        "command": "librecad",
        "tips": "2D CAD (DXF). Type commands in the command line: line (li), circle (ci), rect, text; points as "
        "x,y or @dx,dy (relative).",
        "size_mb": 35,
    },
    {
        "id": "openscad",
        "name": "OpenSCAD",
        "aliases": [],
        "apt": ["openscad"],
        "command": "openscad",
        "tips": "3D models as code: F5 preview, F6 render, F7 export STL. Headless: openscad -o out.stl "
        "model.scad (also .png, .svg, .dxf, .off)",
        "size_mb": 40,
    },
    {
        "id": "kicad",
        "name": "KiCad",
        "aliases": [],
        "apt": ["kicad"],
        "command": "kicad",
        "tips": "Schematics and PCBs (KiCad 9). Headless: kicad-cli sch export pdf -o out.pdf in.kicad_sch; "
        "kicad-cli pcb export gerbers -o gerbers/ board.kicad_pcb",
        "size_mb": 170,
    },
    # ---------------------------------------------------------------- audio and video
    {
        "id": "audacity",
        "name": "Audacity",
        "aliases": [],
        "apt": ["audacity"],
        "command": "audacity",
        "tips": "space play/stop, r record, ctrl+shift+e Export Audio, ctrl+d duplicate, ctrl+k delete the "
        "selection. There is no sound device here: use it to edit and export.",
        "size_mb": 50,
    },
    {
        "id": "vlc",
        "name": "VLC",
        "aliases": ["vlc media player"],
        "apt": ["vlc"],
        "command": "vlc",
        "tips": "space pause, f fullscreen, ctrl+r Convert / Save (transcode), ctrl+q quit. cvlc plays without "
        "the GUI.",
        "size_mb": 100,
    },
    {
        "id": "mpv",
        "name": "mpv",
        "aliases": [],
        "apt": ["mpv"],
        "command": "mpv",
        "tips": "space pause, f fullscreen, left/right seek 5 s, up/down seek 1 min, s screenshot, q quit.",
        "size_mb": 115,
    },
    {
        "id": "obs",
        "name": "OBS Studio",
        "aliases": ["obs studio", "obs-studio"],
        "apt": ["obs-studio"],
        "command": "obs",
        "tips": "Screen recording: add a 'Display Capture (XSHM)' source, then Start Recording; files go to the "
        "path in Settings > Output. obs --startrecording starts recording at launch.",
        "size_mb": 185,
    },
    {
        "id": "kdenlive",
        "name": "Kdenlive",
        "aliases": [],
        "apt": ["kdenlive"],
        "command": "kdenlive",
        "tips": "Video editor: space play/pause, ctrl+return opens Render. Render a project headless: melt "
        "project.kdenlive -consumer avformat:out.mp4",
        "size_mb": 515,
    },
    {
        "id": "shotcut",
        "name": "Shotcut",
        "aliases": [],
        "apt": ["shotcut"],
        "command": "shotcut",
        "tips": "Video editor: ctrl+e Export Video panel, ctrl+shift+e exports the current frame. Quick cuts "
        "without re-encoding: ffmpeg -ss 10 -to 20 -i in.mp4 -c copy out.mp4 (minion-install ffmpeg).",
        "size_mb": 225,
    },
    {
        "id": "handbrake",
        "name": "HandBrake",
        "aliases": ["ghb"],
        "apt": ["handbrake"],
        "command": "ghb",
        "tips": "Video transcoder. Headless: minion-install handbrake-cli, then HandBrakeCLI -i in.mkv "
        "-o out.mp4 --preset 'Fast 1080p30'",
        "size_mb": 110,
    },
    {
        "id": "ardour",
        "name": "Ardour",
        "aliases": [],
        "apt": ["ardour"],
        "command": "ardour",
        "tips": "Digital audio workstation. There is no sound card here: in Audio/MIDI Setup choose the "
        "'None (Dummy)' audio system to start a session.",
        "size_mb": 160,
    },
    {
        "id": "lmms",
        "name": "LMMS",
        "aliases": [],
        "apt": ["lmms"],
        "command": "lmms",
        "tips": "Music production: ctrl+e exports the song. Headless: lmms render song.mmpz -o song.wav",
        "size_mb": 65,
    },
    {
        "id": "musescore",
        "name": "MuseScore 3",
        "aliases": ["musescore3", "musescore 3", "mscore"],
        "apt": ["musescore3"],
        "command": "musescore3",
        "tips": "n note input, a-g enter notes, 5 quarter / 4 eighth note. Headless: musescore3 -o score.pdf "
        "score.mscz (also .mid, .musicxml, .png)",
        "size_mb": 95,
    },
    # ---------------------------------------------------------------- browsers
    {
        "id": "chromium",
        "name": "Chromium",
        "aliases": ["chromium browser", "chromium-browser"],
        "apt": ["chromium"],
        "command": "chromium --no-sandbox --test-type --no-first-run --no-default-browser-check "
        "--force-renderer-accessibility --disable-dev-shm-usage --password-store=basic",
        "tips": "ctrl+l address bar, ctrl+t/ctrl+w tabs, ctrl+f find, alt+left back. Needs --no-sandbox in "
        "the container. Headless: chromium --headless --no-sandbox --screenshot=/tmp/s.png URL "
        "(or --print-to-pdf=/tmp/p.pdf URL)",
        "size_mb": 155,
    },
    {
        "id": "firefox",
        "name": "Firefox ESR",
        "aliases": ["firefox-esr", "mozilla firefox"],
        "apt": ["firefox-esr"],
        "command": "firefox-esr",
        "tips": "ctrl+l address bar, ctrl+t/ctrl+w tabs, ctrl+tab next tab, ctrl+f find, alt+left back, "
        "ctrl+shift+p private window. Web pages are readable with see.",
        "size_mb": 125,
    },
    {
        "id": "google-chrome",
        "name": "Google Chrome",
        "aliases": ["chrome", "google chrome", "google-chrome-stable"],
        "deb": {
            "amd64": "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb",
            "arm64": "https://dl.google.com/linux/direct/google-chrome-stable_current_arm64.deb",
        },
        "command": "google-chrome --no-sandbox --test-type --no-first-run --no-default-browser-check "
        "--force-renderer-accessibility --disable-dev-shm-usage --password-store=basic",
        "tips": "ctrl+l address bar, ctrl+t/ctrl+w tabs, ctrl+f find, alt+left back. Needs --no-sandbox in "
        "the container. Headless: google-chrome --headless --no-sandbox --print-to-pdf=/tmp/p.pdf URL",
        "size_mb": 160,
    },
    # ---------------------------------------------------------------- communication
    {
        "id": "thunderbird",
        "name": "Thunderbird",
        "aliases": ["mozilla thunderbird"],
        "apt": ["thunderbird"],
        "command": "thunderbird",
        "tips": "First start opens account setup. ctrl+n new message, ctrl+enter send, ctrl+r reply, "
        "ctrl+shift+r reply all, ctrl+l forward, F5 get messages, ctrl+shift+b address book.",
        "size_mb": 85,
    },
    {
        "id": "pidgin",
        "name": "Pidgin",
        "aliases": [],
        "apt": ["pidgin"],
        "command": "pidgin",
        "tips": "Chat (XMPP, IRC and more): ctrl+a Manage Accounts to add an account, ctrl+m new instant "
        "message, ctrl+c join a chat.",
        "size_mb": 200,
    },
    {
        "id": "hexchat",
        "name": "HexChat",
        "aliases": ["irc"],
        "apt": ["hexchat"],
        "command": "hexchat",
        "tips": "IRC: ctrl+s Network List, or type /server irc.libera.chat, then /join #channel and "
        "/msg nick text in the input box.",
        "size_mb": 25,
    },
    {
        "id": "zoom",
        "name": "Zoom",
        "aliases": ["zoom meetings", "zoom.us"],
        "deb": {"amd64": "https://zoom.us/client/latest/zoom_amd64.deb"},
        "command": "zoom",
        "tips": "Join with a meeting ID and passcode, or open an invite link. The desktop has no camera or microphone.",
        "size_mb": 360,
    },
    {
        "id": "discord",
        "name": "Discord",
        "aliases": [],
        "deb": {"amd64": "https://discord.com/api/download?platform=linux&format=deb"},
        "command": "discord --no-sandbox --force-renderer-accessibility",
        "tips": "First start downloads the Discord client into ~/.config/discord, then shows the login (email "
        "or QR code from the phone app). ctrl+k quick switcher.",
        "size_mb": 30,
    },
    {
        "id": "telegram",
        "name": "Telegram Web",
        "aliases": ["telegram desktop", "telegram-desktop", "telegram web", "telegram-web"],
        "url": "https://web.telegram.org/",
        "tips": "The Telegram desktop app is not packaged for Debian 13. Log in with the QR code from the phone "
        "app or with a phone number.",
    },
    # ---------------------------------------------------------------- development
    {
        "id": "vscode",
        "name": "Visual Studio Code",
        "aliases": ["code", "vs code", "visual studio code"],
        "deb": {
            "amd64": "https://update.code.visualstudio.com/latest/linux-deb-x64/stable",
            "arm64": "https://update.code.visualstudio.com/latest/linux-deb-arm64/stable",
        },
        "command": "code --no-sandbox --force-renderer-accessibility",
        "tips": "ctrl+shift+p command palette, ctrl+p quick open, ctrl+` terminal, ctrl+b sidebar, "
        "ctrl+shift+f search, ctrl+shift+x extensions. Open a folder: code --no-sandbox ~/work. "
        "Extensions: code --install-extension ms-python.python",
        "size_mb": 250,
    },
    {
        "id": "geany",
        "name": "Geany",
        "aliases": [],
        "apt": ["geany"],
        "command": "geany",
        "tips": "ctrl+e toggle comment, ctrl+l go to line, ctrl+h replace, F8 compile, F9 build, F5 run.",
        "size_mb": 15,
    },
    {
        "id": "emacs",
        "name": "GNU Emacs",
        "aliases": ["gnu emacs"],
        "apt": ["emacs"],
        "command": "emacs",
        "tips": "ctrl+x ctrl+f open, ctrl+x ctrl+s save, ctrl+g cancel, alt+x command, ctrl+x ctrl+c quit. "
        "Batch: emacs --batch -l script.el",
        "size_mb": 135,
    },
    {
        "id": "gvim",
        "name": "GVim",
        "aliases": ["vim", "vi", "vim-gtk3"],
        "apt": ["vim-gtk3"],
        "command": "gvim",
        "tips": "Modal editor: i insert, Escape normal mode, :w save, :q quit, :wq save and quit, /text search, "
        "u undo (type the : commands, then Return).",
        "size_mb": 45,
    },
    {
        "id": "meld",
        "name": "Meld",
        "aliases": [],
        "apt": ["meld"],
        "command": "meld",
        "tips": "Visual diff and merge: meld a.txt b.txt (or two folders; three files for a 3-way merge); "
        "alt+down / alt+up next / previous change. Text alternative: diff -u a b",
        "size_mb": 230,
    },
    {
        "id": "gitg",
        "name": "gitg",
        "aliases": [],
        "apt": ["gitg"],
        "command": "gitg",
        "tips": "Git history browser: gitg ~/work/repo; the Commit view stages and commits. In the shell: "
        "git log --oneline --graph",
        "size_mb": 45,
    },
    {
        "id": "git-cola",
        "name": "Git Cola",
        "aliases": ["cola", "git cola"],
        "apt": ["git-cola"],
        "command": "git-cola",
        "tips": "Git GUI: git-cola -r ~/work/repo; ctrl+s stages the selection, ctrl+enter commits from the "
        "message box, ctrl+r refreshes. git-dag shows the history.",
        "size_mb": 220,
    },
    {
        "id": "sqlitebrowser",
        "name": "DB Browser for SQLite",
        "aliases": ["db browser for sqlite", "sqlite browser", "db4s"],
        "apt": ["sqlitebrowser"],
        "command": "sqlitebrowser",
        "tips": "ctrl+o open database; Execute SQL tab: ctrl+return runs, shift+F5 runs the current line; "
        "ctrl+s Write Changes (commit). Shell: sqlite3 db.sqlite (minion-install sqlite3).",
        "size_mb": 30,
    },
    {
        "id": "dbeaver",
        "name": "DBeaver Community",
        "aliases": ["dbeaver ce", "dbeaver-ce"],
        "deb": {
            "amd64": "https://dbeaver.io/files/dbeaver-ce_latest_amd64.deb",
            "arm64": "https://dbeaver.io/files/dbeaver-ce_latest_arm64.deb",
        },
        "command": "dbeaver-ce",
        "tips": "First start shows a Product Configuration wizard (Apply closes it). ctrl+] new SQL script, "
        "ctrl+enter runs the statement, alt+x runs the script, F3 opens a script. Drivers download on first "
        "connect.",
        "size_mb": 130,
    },
    {
        "id": "postman",
        "name": "Postman",
        "aliases": [],
        "deb": {
            "amd64": "https://dl.pstmn.io/download/latest/linux_64",
            "arm64": "https://dl.pstmn.io/download/latest/linux_arm64",
        },
        "command": "~/apps/postman/Postman/Postman --no-sandbox --force-renderer-accessibility",
        "tips": "First screen: 'Continue without an account' opens the lightweight API client. ctrl+t new "
        "request tab, ctrl+enter sends.",
        "size_mb": 210,
    },
    {
        "id": "insomnia",
        "name": "Insomnia",
        "aliases": [],
        "github": {"repo": "Kong/insomnia", "amd64": r"^Insomnia\.Core-.+\.deb$"},
        "command": "insomnia --no-sandbox --force-renderer-accessibility",
        "tips": "API client for REST, GraphQL, gRPC and WebSockets; imports Postman collections, curl commands "
        "and OpenAPI specs.",
        "size_mb": 440,
    },
    {
        "id": "obsidian",
        "name": "Obsidian",
        "aliases": [],
        "github": {"repo": "obsidianmd/obsidian-releases", "amd64": r"_amd64\.deb$", "arm64": r"-arm64\.AppImage$"},
        "command": "obsidian --no-sandbox --force-renderer-accessibility",
        "tips": "First start asks for a vault: Create one, or Open folder as vault (notes are Markdown files). "
        "ctrl+n new note, ctrl+o quick switcher, ctrl+p command palette, ctrl+e reading/editing view.",
        "size_mb": 120,
    },
    {
        "id": "drawio",
        "name": "draw.io",
        "aliases": ["draw.io", "diagrams.net", "diagrams"],
        "github": {
            "repo": "jgraph/drawio-desktop",
            "amd64": r"^drawio-amd64-.+\.deb$",
            "arm64": r"^drawio-arm64-.+\.deb$",
        },
        "command": "drawio --no-sandbox --force-renderer-accessibility",
        "tips": "Diagrams (.drawio; imports .vsdx). Headless export: drawio --no-sandbox -x -f png -o out.png "
        "in.drawio (pdf, svg, jpg too).",
        "size_mb": 135,
    },
    {
        "id": "joplin",
        "name": "Joplin",
        "aliases": [],
        "github": {"repo": "laurent22/joplin", "amd64": r"^Joplin-.+\.deb$"},
        "command": "joplin --no-sandbox --force-renderer-accessibility",
        "tips": "Markdown notes: ctrl+n new note, ctrl+t new to-do, ctrl+p go to anything, F6 search, ctrl+s "
        "synchronise.",
        "size_mb": 175,
    },
    {
        "id": "logseq",
        "name": "Logseq",
        "aliases": [],
        "github": {
            "repo": "logseq/logseq",
            "amd64": r"^Logseq-linux-x86_64-.+\.AppImage$",
            "arm64": r"^Logseq-linux-arm64-.+\.AppImage$",
        },
        "command": "logseq --no-sandbox --force-renderer-accessibility",
        "tips": "Outliner for Markdown notes and journals: every line is a block; Enter adds a block, Tab indents it.",
        "size_mb": 190,
    },
    {
        "id": "marktext",
        "name": "MarkText",
        "aliases": ["mark text"],
        "github": {"repo": "marktext/marktext", "amd64": r"^marktext-linux-.+\.deb$"},
        "command": "marktext --no-sandbox --force-renderer-accessibility",
        "tips": "WYSIWYG Markdown editor for .md files; File > Export saves HTML or PDF.",
        "size_mb": 140,
    },
    {
        "id": "jupyter",
        "name": "Jupyter Notebook",
        "aliases": ["jupyter notebook", "jupyter-notebook"],
        "apt": ["jupyter-notebook", "jupyter-nbconvert"],
        "command": "jupyter-notebook",
        "tips": "Starts a server on http://localhost:8888 and opens it in the browser (a base desktop has none: "
        "open firefox first). shift+enter runs a cell; Escape then a/b adds a cell. Headless: jupyter "
        "nbconvert --to notebook --execute --inplace nb.ipynb",
        "size_mb": 200,
    },
    {
        "id": "spyder",
        "name": "Spyder",
        "aliases": [],
        "apt": ["spyder"],
        "command": "spyder",
        "tips": "Python IDE: F5 run file, F9 run selection or line, ctrl+enter run cell (cells start with # %%), "
        "shift+enter run cell and advance.",
        "size_mb": 340,
    },
    {
        "id": "octave",
        "name": "GNU Octave",
        "aliases": ["gnu octave"],
        "apt": ["octave"],
        "command": "octave --gui",
        "tips": "MATLAB-compatible language. Headless: octave-cli --eval 'disp(pi)' or octave-cli script.m",
        "size_mb": 195,
    },
    # ---------------------------------------------------------------- science and data
    {
        "id": "qgis",
        "name": "QGIS",
        "aliases": [],
        "apt": ["qgis"],
        "command": "qgis",
        "tips": "GIS: ctrl+l Data Source Manager, ctrl+shift+v add vector layer, ctrl+shift+r add raster layer, "
        "ctrl+s save project. Headless: qgis_process run native:buffer -- INPUT=in.gpkg DISTANCE=10 "
        "OUTPUT=out.gpkg",
        "size_mb": 500,
    },
    {
        "id": "labplot",
        "name": "LabPlot",
        "aliases": ["labplot2"],
        "apt": ["labplot"],
        "command": "labplot",
        "tips": "Plotting and data analysis: ctrl+shift+i imports data from a file (CSV and more).",
        "size_mb": 260,
    },
    # ---------------------------------------------------------------- utilities
    {
        "id": "keepassxc",
        "name": "KeePassXC",
        "aliases": ["keepass"],
        "apt": ["keepassxc"],
        "command": "keepassxc",
        "tips": "ctrl+b copy username, ctrl+c copy password, ctrl+n new entry, ctrl+e edit entry. CLI: "
        "keepassxc-cli ls db.kdbx; keepassxc-cli show -s db.kdbx 'Entry' (shows the password).",
        "size_mb": 40,
    },
    {
        "id": "filezilla",
        "name": "FileZilla",
        "aliases": [],
        "apt": ["filezilla"],
        "command": "filezilla",
        "tips": "FTP/SFTP: fill the Quickconnect bar (Host such as sftp://host, Username, Password, Port) and "
        "press Return; ctrl+s Site Manager. Shell alternatives: sftp, scp, curl.",
        "size_mb": 20,
    },
    {
        "id": "transmission",
        "name": "Transmission",
        "aliases": ["transmission-gtk"],
        "apt": ["transmission-gtk"],
        "command": "transmission-gtk",
        "tips": "BitTorrent: ctrl+o adds a .torrent file, ctrl+u adds a magnet link or URL.",
        "size_mb": 25,
    },
    {
        "id": "qbittorrent",
        "name": "qBittorrent",
        "aliases": [],
        "apt": ["qbittorrent"],
        "command": "qbittorrent",
        "tips": "BitTorrent: ctrl+o adds a .torrent file, ctrl+shift+o adds magnet links or URLs.",
        "size_mb": 40,
    },
    {
        "id": "galculator",
        "name": "Galculator",
        "aliases": ["calculator"],
        "apt": ["galculator"],
        "command": "galculator",
        "tips": "Type with the keyboard, e.g. 12*7 then = for the result. The View menu switches Basic, "
        "Scientific and Paper mode.",
        "size_mb": 10,
    },
    {
        "id": "xarchiver",
        "name": "Xarchiver",
        "aliases": ["archive manager"],
        "apt": ["xarchiver"],
        "command": "xarchiver",
        "tips": "Archive manager (zip, tar, 7z and more). Extract without the GUI: xarchiver --extract-to=DIR "
        "archive.zip, or tar -xf archive.tar.gz -C DIR.",
        "size_mb": 15,
    },
    {
        "id": "remmina",
        "name": "Remmina",
        "aliases": ["remote desktop"],
        "apt": ["remmina"],
        "command": "remmina",
        "tips": "RDP/VNC/SSH client: choose the protocol and type the server in the top bar, then Return. CLI: "
        "remmina -c rdp://user@host (vnc:// and ssh:// too).",
        "size_mb": 50,
    },
    {
        "id": "wireshark",
        "name": "Wireshark",
        "aliases": [],
        "apt": ["wireshark"],
        "command": "wireshark",
        "tips": "Open a capture: wireshark -r file.pcapng. Filters: http, ip.addr==10.0.0.1, tcp.port==443. "
        "Live capture needs root: sudo dumpcap -i any -w /tmp/c.pcapng. Terminal: tshark -r file "
        "(minion-install tshark).",
        "size_mb": 105,
    },
    # ---------------------------------------------------------------- notes, finance, learning
    {
        "id": "zim",
        "name": "Zim",
        "aliases": ["zim wiki"],
        "apt": ["zim"],
        "command": "zim",
        "tips": "Desktop wiki of plain-text pages: ctrl+n new page, ctrl+shift+n sub page, ctrl+j jump to page, "
        "ctrl+l insert link.",
        "size_mb": 15,
    },
    {
        "id": "cherrytree",
        "name": "CherryTree",
        "aliases": [],
        "apt": ["cherrytree"],
        "command": "cherrytree",
        "tips": "Hierarchical notes: ctrl+n add node, ctrl+shift+n add subnode, ctrl+shift+f search all nodes, "
        "ctrl+s save.",
        "size_mb": 20,
    },
    {
        "id": "gnucash",
        "name": "GnuCash",
        "aliases": [],
        "apt": ["gnucash"],
        "command": "gnucash",
        "tips": "Double-entry accounting: File > Import for QIF, OFX/QFX and CSV transactions; type a "
        "transaction in the blank row of an account register and press Return.",
        "size_mb": 425,
    },
    {
        "id": "homebank",
        "name": "HomeBank",
        "aliases": [],
        "apt": ["homebank"],
        "command": "homebank",
        "tips": "Personal finance: ctrl+i imports bank statements (CSV, OFX/QFX, QIF).",
        "size_mb": 15,
    },
    {
        "id": "anki",
        "name": "AnkiWeb",
        "aliases": ["ankiweb"],
        "url": "https://ankiweb.net/decks",
        "tips": "Study and add flashcards in the browser (needs an AnkiWeb account). The Anki desktop app is not "
        "packaged for Debian 13.",
    },
    # ---------------------------------------------------------------- web apps
    {
        "id": "google-docs",
        "name": "Google Docs",
        "aliases": ["google doc", "gdocs"],
        "url": "https://docs.google.com/document/",
        "tips": "Needs a Google sign-in. ctrl+alt+m comment, ctrl+k link, ctrl+shift+c word count, ctrl+/ lists "
        "all shortcuts. File > Download saves .docx or .pdf.",
    },
    {
        "id": "google-sheets",
        "name": "Google Sheets",
        "aliases": ["google sheet", "gsheets"],
        "url": "https://docs.google.com/spreadsheets/",
        "tips": "Needs a Google sign-in. F2 edits a cell, ctrl+shift+v pastes values only, ctrl+/ lists "
        "shortcuts. File > Download saves .xlsx or .csv.",
    },
    {
        "id": "google-slides",
        "name": "Google Slides",
        "aliases": ["gslides"],
        "url": "https://docs.google.com/presentation/",
        "tips": "Needs a Google sign-in. ctrl+m new slide, ctrl+/ lists shortcuts. File > Download saves .pptx "
        "or .pdf.",
    },
    {
        "id": "google-drive",
        "name": "Google Drive",
        "aliases": ["gdrive"],
        "url": "https://drive.google.com/",
        "tips": "Needs a Google sign-in. New > File upload adds files from the desktop; downloads land in ~/Downloads.",
    },
    {
        "id": "gmail",
        "name": "Gmail",
        "aliases": ["google mail"],
        "url": "https://mail.google.com/",
        "tips": "Needs a Google sign-in. ctrl+enter sends. Single-key shortcuts (c compose, / search, e archive) "
        "work only after turning them on in Settings.",
    },
    {
        "id": "google-calendar",
        "name": "Google Calendar",
        "aliases": ["gcal"],
        "url": "https://calendar.google.com/",
        "tips": "Needs a Google sign-in. c new event, t today, d / w / m day, week or month view.",
    },
    {
        "id": "google-maps",
        "name": "Google Maps",
        "aliases": ["maps"],
        "url": "https://www.google.com/maps",
        "tips": "Search places in the box at the top left; Directions for routes. The map is drawn on a canvas: "
        "read it with screenshots.",
    },
    {
        "id": "word-web",
        "name": "Word for the web",
        "aliases": ["word online", "word for the web", "microsoft word online"],
        "url": "https://word.cloud.microsoft/",
        "tips": "Needs a Microsoft account; files are stored in OneDrive. For local .docx files use LibreOffice "
        "Writer (open writer).",
    },
    {
        "id": "excel-web",
        "name": "Excel for the web",
        "aliases": ["excel online", "excel for the web", "microsoft excel online"],
        "url": "https://excel.cloud.microsoft/",
        "tips": "Needs a Microsoft account; files are stored in OneDrive. For local .xlsx files use LibreOffice "
        "Calc (open calc).",
    },
    {
        "id": "powerpoint-web",
        "name": "PowerPoint for the web",
        "aliases": ["powerpoint online", "powerpoint for the web", "microsoft powerpoint online"],
        "url": "https://powerpoint.cloud.microsoft/",
        "tips": "Needs a Microsoft account; files are stored in OneDrive. For local .pptx files use LibreOffice "
        "Impress (open impress).",
    },
    {
        "id": "outlook-web",
        "name": "Outlook on the web",
        "aliases": ["outlook online", "outlook on the web", "outlook.com", "hotmail"],
        "url": "https://outlook.office.com/mail/",
        "tips": "Sign in with a work, school or personal Microsoft account. ctrl+enter sends a message.",
    },
    {
        "id": "onenote-web",
        "name": "OneNote for the web",
        "aliases": ["onenote online", "onenote for the web"],
        "url": "https://onenote.cloud.microsoft/",
        "tips": "Needs a Microsoft account; notebooks are stored in OneDrive.",
    },
    {
        "id": "teams",
        "name": "Microsoft Teams",
        "aliases": ["microsoft teams", "ms teams"],
        "url": "https://teams.microsoft.com/",
        "tips": "On Linux, Teams is the web app: sign in with a Microsoft account. The desktop has no camera or "
        "microphone.",
    },
    {
        "id": "microsoft-365",
        "name": "Microsoft 365",
        "aliases": ["office 365", "office365", "m365", "office online", "office.com"],
        "url": "https://www.microsoft365.com/",
        "tips": "Microsoft 365 home: after signing in, open Word, Excel, PowerPoint and OneDrive files.",
    },
    {
        "id": "figma",
        "name": "Figma",
        "aliases": [],
        "url": "https://www.figma.com/files",
        "tips": "Needs a Figma account. The canvas is not in the accessibility tree: use screenshots. r rectangle, "
        "o ellipse, t text, f frame, shift+1 zoom to fit, ctrl+d duplicate.",
    },
    {
        "id": "canva",
        "name": "Canva",
        "aliases": [],
        "url": "https://www.canva.com/",
        "tips": "Needs a Canva account. The editor is mostly a canvas: use screenshots. Share > Download saves "
        "PNG, PDF or MP4.",
    },
    {
        "id": "photopea",
        "name": "Photopea",
        "aliases": [],
        "url": "https://www.photopea.com/",
        "tips": "Photoshop-like editor in the browser, no account needed; opens PSD, XCF and Sketch files. "
        "File > Export as (PNG, JPG, PSD), ctrl+t free transform.",
    },
    {
        "id": "notion",
        "name": "Notion",
        "aliases": [],
        "url": "https://www.notion.so/",
        "tips": "Needs a Notion account. Type / in a page to insert blocks; ctrl+p searches pages.",
    },
    {
        "id": "trello",
        "name": "Trello",
        "aliases": [],
        "url": "https://trello.com/",
        "tips": "Needs an Atlassian account. Press ? on a board for its keyboard shortcuts.",
    },
    {
        "id": "miro",
        "name": "Miro",
        "aliases": [],
        "url": "https://miro.com/app/dashboard/",
        "tips": "Needs a Miro account. Boards are drawn on a canvas: read them with screenshots.",
    },
    {
        "id": "slack",
        "name": "Slack",
        "aliases": ["slack web"],
        "url": "https://app.slack.com/client",
        "tips": "Sign in to a workspace. ctrl+k jumps to a channel or person.",
    },
    {
        "id": "discord-web",
        "name": "Discord (web)",
        "aliases": ["discord web"],
        "url": "https://discord.com/app",
        "tips": "Log in with email or the QR code from the phone app. ctrl+k quick switcher.",
    },
    {
        "id": "whatsapp",
        "name": "WhatsApp Web",
        "aliases": ["whatsapp web", "whatsapp-web"],
        "url": "https://web.whatsapp.com/",
        "tips": "Link it from the phone app (Linked devices > Link a device) by scanning the QR code on the page.",
    },
    {
        "id": "github",
        "name": "GitHub",
        "aliases": ["github.com"],
        "url": "https://github.com/",
        "tips": "/ focuses search, ? lists shortcuts, t finds a file in a repository, . opens the github.dev editor.",
    },
    # ---------------------------------------------------------------- not available on Linux
    {
        "id": "photoshop",
        "name": "Adobe Photoshop",
        "aliases": ["adobe photoshop"],
        "unavailable": "Adobe Photoshop does not run on Linux.",
        "alternatives": ["gimp", "krita", "photopea"],
    },
    {
        "id": "illustrator",
        "name": "Adobe Illustrator",
        "aliases": ["adobe illustrator"],
        "unavailable": "Adobe Illustrator does not run on Linux.",
        "alternatives": ["inkscape", "figma"],
    },
    {
        "id": "premiere-pro",
        "name": "Adobe Premiere Pro",
        "aliases": ["premiere", "adobe premiere", "adobe premiere pro"],
        "unavailable": "Adobe Premiere Pro does not run on Linux.",
        "alternatives": ["kdenlive", "shotcut"],
    },
    {
        "id": "after-effects",
        "name": "Adobe After Effects",
        "aliases": ["after effects", "adobe after effects"],
        "unavailable": "Adobe After Effects does not run on Linux.",
        "alternatives": ["blender", "kdenlive"],
    },
    {
        "id": "indesign",
        "name": "Adobe InDesign",
        "aliases": ["adobe indesign"],
        "unavailable": "Adobe InDesign does not run on Linux.",
        "alternatives": ["scribus"],
    },
    {
        "id": "lightroom",
        "name": "Adobe Lightroom",
        "aliases": ["adobe lightroom", "lightroom classic"],
        "unavailable": "Adobe Lightroom does not run on Linux.",
        "alternatives": ["darktable", "rawtherapee", "digikam"],
    },
    {
        "id": "acrobat",
        "name": "Adobe Acrobat",
        "aliases": ["adobe acrobat", "acrobat reader", "adobe reader", "adobe acrobat reader"],
        "unavailable": "Adobe Acrobat does not run on Linux.",
        "alternatives": ["okular", "xournalpp", "pdfarranger", "evince"],
    },
    {
        "id": "autocad",
        "name": "AutoCAD",
        "aliases": ["auto cad"],
        "unavailable": "AutoCAD does not run on Linux.",
        "alternatives": ["librecad", "freecad"],
    },
    {
        "id": "solidworks",
        "name": "SolidWorks",
        "aliases": ["solid works"],
        "unavailable": "SolidWorks does not run on Linux.",
        "alternatives": ["freecad", "openscad"],
    },
    {
        "id": "final-cut-pro",
        "name": "Final Cut Pro",
        "aliases": ["final cut", "final cut pro"],
        "unavailable": "Final Cut Pro runs only on macOS.",
        "alternatives": ["kdenlive", "shotcut"],
    },
    {
        "id": "logic-pro",
        "name": "Logic Pro",
        "aliases": ["logic pro x"],
        "unavailable": "Logic Pro runs only on macOS.",
        "alternatives": ["ardour", "lmms", "audacity"],
    },
    {
        "id": "word",
        "name": "Microsoft Word",
        "aliases": ["microsoft word", "ms word", "winword"],
        "unavailable": "Microsoft Word has no Linux version; use LibreOffice Writer or Word for the web.",
        "alternatives": ["writer", "word-web"],
    },
    {
        "id": "excel",
        "name": "Microsoft Excel",
        "aliases": ["microsoft excel", "ms excel"],
        "unavailable": "Microsoft Excel has no Linux version; use LibreOffice Calc or Excel for the web.",
        "alternatives": ["calc", "excel-web"],
    },
    {
        "id": "powerpoint",
        "name": "Microsoft PowerPoint",
        "aliases": ["microsoft powerpoint", "ms powerpoint", "power point"],
        "unavailable": "Microsoft PowerPoint has no Linux version; use LibreOffice Impress or PowerPoint for the web.",
        "alternatives": ["impress", "powerpoint-web"],
    },
    {
        "id": "outlook",
        "name": "Microsoft Outlook",
        "aliases": ["microsoft outlook", "ms outlook"],
        "unavailable": "Microsoft Outlook has no Linux version; use Outlook on the web or Thunderbird.",
        "alternatives": ["outlook-web", "thunderbird"],
    },
    {
        "id": "onenote",
        "name": "Microsoft OneNote",
        "aliases": ["microsoft onenote", "one note"],
        "unavailable": "Microsoft OneNote has no Linux version; use OneNote for the web.",
        "alternatives": ["onenote-web", "joplin", "xournalpp"],
    },
    {
        "id": "visio",
        "name": "Microsoft Visio",
        "aliases": ["microsoft visio", "ms visio"],
        "unavailable": "Microsoft Visio has no Linux version; draw.io can import .vsdx files.",
        "alternatives": ["drawio"],
    },
    {
        "id": "paint",
        "name": "Microsoft Paint",
        "aliases": ["ms paint", "mspaint", "microsoft paint"],
        "unavailable": "Microsoft Paint is a Windows app.",
        "alternatives": ["kolourpaint", "drawing"],
    },
    {
        "id": "notepad-plus-plus",
        "name": "Notepad++",
        "aliases": ["notepad++"],
        "unavailable": "Notepad++ is Windows-only; the windows profile can run it with Wine.",
        "alternatives": ["geany", "kate"],
    },
    {
        "id": "notepad",
        "name": "Notepad",
        "aliases": ["windows notepad"],
        "unavailable": "Notepad is a Windows app; the windows profile includes it (Wine).",
        "alternatives": ["mousepad", "gedit"],
    },
    {
        "id": "visual-studio",
        "name": "Visual Studio",
        "aliases": ["visual studio", "microsoft visual studio"],
        "unavailable": "Visual Studio (the IDE) is Windows-only; Visual Studio Code runs on Linux.",
        "alternatives": ["vscode"],
    },
    {
        "id": "matlab",
        "name": "MATLAB",
        "aliases": [],
        "unavailable": "MATLAB needs a MathWorks license and its own installer; GNU Octave runs most MATLAB code.",
        "alternatives": ["octave"],
    },
]
