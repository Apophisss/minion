# Apps an agent can open by name

`open NAME` works for every app below, on any profile. An app that isn't installed yet is installed the first time
(this takes from a few seconds to a few minutes, depending on its size), and the first open answers with a few tips
for it. Web apps open in the desktop's browser (a browser is installed first on the `base` profile). Apps that don't
run on Linux answer with the alternatives listed here.

Any other Debian package also works by name (`open galculator`), and `minion-install` takes `.deb`, `.AppImage` and
archive URLs, `pip:` and `npm:` packages. Inside an app, `see --menus` lists its commands with their shortcuts.

This page is generated from [`minion/agent/catalog_data.py`](../minion/agent/catalog_data.py) by
`scripts/gen_apps_doc.py`.


## Office and documents

| App | Open with | How it gets there |
|---|---|---|
| LibreOffice | `libreoffice`, `libre office`, `soffice` | Debian package (~290 MB) |
| LibreOffice Writer | `writer`, `libreoffice writer`, `libreoffice-writer`, `lowriter` | Debian package (~280 MB) |
| LibreOffice Calc | `calc`, `libreoffice calc`, `libreoffice-calc`, `localc` | Debian package (~280 MB) |
| LibreOffice Impress | `impress`, `libreoffice impress`, `libreoffice-impress`, `loimpress` | Debian package (~270 MB) |
| LibreOffice Draw | `draw`, `libreoffice draw`, `libreoffice-draw`, `lodraw` | Debian package (~270 MB) |
| LibreOffice Math | `math`, `libreoffice math`, `libreoffice-math`, `lomath` | Debian package (~260 MB) |
| AbiWord | `abiword` | Debian package (~55 MB) |
| Gnumeric | `gnumeric` | Debian package (~260 MB) |
| Scribus | `scribus` | Debian package (~150 MB) |
| calibre | `calibre` | Debian package (~380 MB) |
| Evince (Document Viewer) | `evince`, `document viewer`, `pdf viewer` | Debian package (~60 MB) |
| Okular | `okular` | Debian package (~250 MB) |
| Xournal++ | `xournalpp`, `xournal`, `xournal++` | Debian package (~140 MB) |
| PDF Arranger | `pdfarranger`, `pdf arranger`, `pdf-arranger` | Debian package (~25 MB) |

## Text editors and files

| App | Open with | How it gets there |
|---|---|---|
| Mousepad | `mousepad`, `text editor` | Debian package (~15 MB) |
| gedit | `gedit` | Debian package (~245 MB) |
| Kate | `kate` | Debian package (~150 MB) |
| PCManFM (file manager) | `pcmanfm`, `file manager`, `files` | Debian package (~75 MB) |

## Graphics and photos

| App | Open with | How it gets there |
|---|---|---|
| GIMP | `gimp`, `gimp-3`, `gnu image manipulation program` | Debian package (~90 MB) |
| Inkscape | `inkscape` | Debian package (~105 MB) |
| Krita | `krita` | Debian package (~290 MB) |
| darktable | `darktable` | Debian package (~95 MB) |
| RawTherapee | `rawtherapee`, `raw therapee` | Debian package (~45 MB) |
| MyPaint | `mypaint` | Debian package (~25 MB) |
| digiKam | `digikam` | Debian package (~435 MB) |
| KolourPaint | `kolourpaint` | Debian package (~140 MB) |
| Drawing | `drawing`, `gnome drawing` | Debian package (~15 MB) |
| Ristretto (image viewer) | `ristretto`, `image viewer`, `photo viewer` | Debian package (~35 MB) |

## 3D and CAD

| App | Open with | How it gets there |
|---|---|---|
| Blender | `blender` | Debian package (~255 MB) |
| FreeCAD | `freecad`, `free cad` | Debian package (~475 MB) |
| LibreCAD | `librecad`, `libre cad` | Debian package (~35 MB) |
| OpenSCAD | `openscad` | Debian package (~40 MB) |
| KiCad | `kicad` | Debian package (~170 MB) |

## Audio and video

| App | Open with | How it gets there |
|---|---|---|
| Audacity | `audacity` | Debian package (~50 MB) |
| VLC | `vlc`, `vlc media player` | Debian package (~100 MB) |
| mpv | `mpv` | Debian package (~115 MB) |
| OBS Studio | `obs`, `obs studio`, `obs-studio` | Debian package (~185 MB) |
| Kdenlive | `kdenlive` | Debian package (~515 MB) |
| Shotcut | `shotcut` | Debian package (~225 MB) |
| HandBrake | `handbrake`, `ghb` | Debian package (~110 MB) |
| Ardour | `ardour` | Debian package (~160 MB) |
| LMMS | `lmms` | Debian package (~65 MB) |
| MuseScore 3 | `musescore`, `musescore3`, `musescore 3`, `mscore` | Debian package (~95 MB) |

## Browsers

| App | Open with | How it gets there |
|---|---|---|
| Chromium | `chromium`, `chromium browser`, `chromium-browser` | Debian package (~155 MB) |
| Firefox ESR | `firefox`, `firefox-esr`, `mozilla firefox` | Debian package (~125 MB) |
| Google Chrome | `google-chrome`, `chrome`, `google chrome`, `google-chrome-stable` | official download (~160 MB) |

## Communication

| App | Open with | How it gets there |
|---|---|---|
| Thunderbird | `thunderbird`, `mozilla thunderbird` | Debian package (~85 MB) |
| Pidgin | `pidgin` | Debian package (~200 MB) |
| HexChat | `hexchat`, `irc` | Debian package (~25 MB) |
| Zoom | `zoom`, `zoom meetings`, `zoom.us` | official download (~360 MB) (x86-64 only) |
| Discord | `discord` | official download (~30 MB) (x86-64 only) |
| Telegram Web | `telegram`, `telegram desktop`, `telegram-desktop`, `telegram web` | web app: https://web.telegram.org/ |

## Development

| App | Open with | How it gets there |
|---|---|---|
| Visual Studio Code | `vscode`, `code`, `vs code`, `visual studio code` | official download (~250 MB) |
| Geany | `geany` | Debian package (~15 MB) |
| GNU Emacs | `emacs`, `gnu emacs` | Debian package (~135 MB) |
| GVim | `gvim`, `vim`, `vi`, `vim-gtk3` | Debian package (~45 MB) |
| Meld | `meld` | Debian package (~230 MB) |
| gitg | `gitg` | Debian package (~45 MB) |
| Git Cola | `git-cola`, `cola`, `git cola` | Debian package (~220 MB) |
| DB Browser for SQLite | `sqlitebrowser`, `db browser for sqlite`, `sqlite browser`, `db4s` | Debian package (~30 MB) |
| DBeaver Community | `dbeaver`, `dbeaver ce`, `dbeaver-ce` | official download (~130 MB) |
| Postman | `postman` | official download (~210 MB) |
| Insomnia | `insomnia` | newest GitHub release (~440 MB) (x86-64 only) |
| Obsidian | `obsidian` | newest GitHub release (~120 MB) |
| draw.io | `drawio`, `draw.io`, `diagrams.net`, `diagrams` | newest GitHub release (~135 MB) |
| Joplin | `joplin` | newest GitHub release (~175 MB) (x86-64 only) |
| Logseq | `logseq` | newest GitHub release (~190 MB) |
| MarkText | `marktext`, `mark text` | newest GitHub release (~140 MB) (x86-64 only) |
| Jupyter Notebook | `jupyter`, `jupyter notebook`, `jupyter-notebook` | Debian package (~200 MB) |
| Spyder | `spyder` | Debian package (~340 MB) |
| GNU Octave | `octave`, `gnu octave` | Debian package (~195 MB) |

## Science and data

| App | Open with | How it gets there |
|---|---|---|
| QGIS | `qgis` | Debian package (~500 MB) |
| LabPlot | `labplot`, `labplot2` | Debian package (~260 MB) |

## Utilities

| App | Open with | How it gets there |
|---|---|---|
| KeePassXC | `keepassxc`, `keepass` | Debian package (~40 MB) |
| FileZilla | `filezilla` | Debian package (~20 MB) |
| Transmission | `transmission`, `transmission-gtk` | Debian package (~25 MB) |
| qBittorrent | `qbittorrent` | Debian package (~40 MB) |
| Galculator | `galculator`, `calculator` | Debian package (~10 MB) |
| Xarchiver | `xarchiver`, `archive manager` | Debian package (~15 MB) |
| Remmina | `remmina`, `remote desktop` | Debian package (~50 MB) |
| Wireshark | `wireshark` | Debian package (~105 MB) |

## Notes, finance, learning

| App | Open with | How it gets there |
|---|---|---|
| Zim | `zim`, `zim wiki` | Debian package (~15 MB) |
| CherryTree | `cherrytree` | Debian package (~20 MB) |
| GnuCash | `gnucash` | Debian package (~425 MB) |
| HomeBank | `homebank` | Debian package (~15 MB) |
| AnkiWeb | `anki`, `ankiweb` | web app: https://ankiweb.net/decks |

## Web apps

| App | Open with | How it gets there |
|---|---|---|
| Google Docs | `google-docs`, `google doc`, `gdocs` | web app: https://docs.google.com/document/ |
| Google Sheets | `google-sheets`, `google sheet`, `gsheets` | web app: https://docs.google.com/spreadsheets/ |
| Google Slides | `google-slides`, `gslides` | web app: https://docs.google.com/presentation/ |
| Google Drive | `google-drive`, `gdrive` | web app: https://drive.google.com/ |
| Gmail | `gmail`, `google mail` | web app: https://mail.google.com/ |
| Google Calendar | `google-calendar`, `gcal` | web app: https://calendar.google.com/ |
| Google Maps | `google-maps`, `maps` | web app: https://www.google.com/maps |
| Word for the web | `word-web`, `word online`, `word for the web`, `microsoft word online` | web app: https://word.cloud.microsoft/ |
| Excel for the web | `excel-web`, `excel online`, `excel for the web`, `microsoft excel online` | web app: https://excel.cloud.microsoft/ |
| PowerPoint for the web | `powerpoint-web`, `powerpoint online`, `powerpoint for the web`, `microsoft powerpoint online` | web app: https://powerpoint.cloud.microsoft/ |
| Outlook on the web | `outlook-web`, `outlook online`, `outlook on the web`, `outlook.com` | web app: https://outlook.office.com/mail/ |
| OneNote for the web | `onenote-web`, `onenote online`, `onenote for the web` | web app: https://onenote.cloud.microsoft/ |
| Microsoft Teams | `teams`, `microsoft teams`, `ms teams` | web app: https://teams.microsoft.com/ |
| Microsoft 365 | `microsoft-365`, `office 365`, `office365`, `m365` | web app: https://www.microsoft365.com/ |
| Figma | `figma` | web app: https://www.figma.com/files |
| Canva | `canva` | web app: https://www.canva.com/ |
| Photopea | `photopea` | web app: https://www.photopea.com/ |
| Notion | `notion` | web app: https://www.notion.so/ |
| Trello | `trello` | web app: https://trello.com/ |
| Miro | `miro` | web app: https://miro.com/app/dashboard/ |
| Slack | `slack`, `slack web` | web app: https://app.slack.com/client |
| Discord (web) | `discord-web`, `discord web` | web app: https://discord.com/app |
| WhatsApp Web | `whatsapp`, `whatsapp web`, `whatsapp-web` | web app: https://web.whatsapp.com/ |
| GitHub | `github`, `github.com` | web app: https://github.com/ |

## Not available on Linux

| App | Open with | How it gets there |
|---|---|---|
| Adobe Photoshop | `photoshop`, `adobe photoshop` | not on Linux; instead: `open gimp`, `open krita`, `open photopea` |
| Adobe Illustrator | `illustrator`, `adobe illustrator` | not on Linux; instead: `open inkscape`, `open figma` |
| Adobe Premiere Pro | `premiere-pro`, `premiere`, `adobe premiere`, `adobe premiere pro` | not on Linux; instead: `open kdenlive`, `open shotcut` |
| Adobe After Effects | `after-effects`, `after effects`, `adobe after effects` | not on Linux; instead: `open blender`, `open kdenlive` |
| Adobe InDesign | `indesign`, `adobe indesign` | not on Linux; instead: `open scribus` |
| Adobe Lightroom | `lightroom`, `adobe lightroom`, `lightroom classic` | not on Linux; instead: `open darktable`, `open rawtherapee`, `open digikam` |
| Adobe Acrobat | `acrobat`, `adobe acrobat`, `acrobat reader`, `adobe reader` | not on Linux; instead: `open okular`, `open xournalpp`, `open pdfarranger`, `open evince` |
| AutoCAD | `autocad`, `auto cad` | not on Linux; instead: `open librecad`, `open freecad` |
| SolidWorks | `solidworks`, `solid works` | not on Linux; instead: `open freecad`, `open openscad` |
| Final Cut Pro | `final-cut-pro`, `final cut`, `final cut pro` | not on Linux; instead: `open kdenlive`, `open shotcut` |
| Logic Pro | `logic-pro`, `logic pro x` | not on Linux; instead: `open ardour`, `open lmms`, `open audacity` |
| Microsoft Word | `word`, `microsoft word`, `ms word`, `winword` | not on Linux; instead: `open writer`, `open word-web` |
| Microsoft Excel | `excel`, `microsoft excel`, `ms excel` | not on Linux; instead: `open calc`, `open excel-web` |
| Microsoft PowerPoint | `powerpoint`, `microsoft powerpoint`, `ms powerpoint`, `power point` | not on Linux; instead: `open impress`, `open powerpoint-web` |
| Microsoft Outlook | `outlook`, `microsoft outlook`, `ms outlook` | not on Linux; instead: `open outlook-web`, `open thunderbird` |
| Microsoft OneNote | `onenote`, `microsoft onenote`, `one note` | not on Linux; instead: `open onenote-web`, `open joplin`, `open xournalpp` |
| Microsoft Visio | `visio`, `microsoft visio`, `ms visio` | not on Linux; instead: `open drawio` |
| Microsoft Paint | `paint`, `ms paint`, `mspaint`, `microsoft paint` | not on Linux; instead: `open kolourpaint`, `open drawing` |
| Notepad++ | `notepad-plus-plus`, `notepad++` | not on Linux; instead: `open geany`, `open kate` |
| Notepad | `notepad`, `windows notepad` | not on Linux; instead: `open mousepad`, `open gedit` |
| Visual Studio | `visual-studio`, `visual studio`, `microsoft visual studio` | not on Linux; instead: `open vscode` |
| MATLAB | `matlab` | not on Linux; instead: `open octave` |
