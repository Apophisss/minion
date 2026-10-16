# Windows apps

The `windows` profile runs Windows programs (`.exe` and `.msi`, 64-bit and 32-bit) through
[Wine](https://www.winehq.org/) 10 inside a normal Minion desktop. Firefox is included so agents can download
installers. Agents drive Windows programs the same way they drive Linux apps: `open`, `see`, `act`, screenshots.

It needs an **x86-64 (amd64)** machine. Wine runs x86 Windows code natively, so the image is not built for arm64.

```bash
minion up windows --name win
minion -d win open notepad                       # Wine's Notepad
minion -d win type "Hello from Windows Notepad"
minion -d win see                                # Wine windows are read with OCR
minion -d win shot -o notepad.png
```

## Running a real program

Download with Firefox or with `run`, then open the file. `.exe` and `.msi` files open with Wine.

```bash
minion -d win run "cd ~/Downloads && curl -fsSLO https://github.com/ip7z/7zip/releases/download/26.04/7z2604.exe"
minion -d win open '~/Downloads/7z2604.exe'      # the installer window appears
minion -d win see                                # → … @51 "Install" (619,463)
minion -d win click @51
minion -d win open "wine 'C:\Program Files (x86)\7-Zip\7zFM.exe'"
```

| Task | How |
|---|---|
| Run an installer or program | `open ~/Downloads/setup.exe` (or `.msi`), or `run wine ~/Downloads/setup.exe` |
| Install silently | NSIS: `run wine setup.exe /S` · Inno Setup: `run wine setup.exe /VERYSILENT /NORESTART` · MSI: `run wine msiexec /i app.msi /qn` |
| Portable app (zip) | `run unzip -q app.zip -d ~/Apps/app`, then `open "wine ~/Apps/app/app.exe"` |
| Start an installed program | `open "wine 'C:\Program Files\App\app.exe'"`. Installed programs live under `~/.wine/drive_c/Program Files/` and `Program Files (x86)/` |
| Close every Windows program | `run wineserver -k` |
| Missing runtime DLLs | `run winetricks -q vcrun2022` (Visual C++), `winetricks -q corefonts` (Arial, Times New Roman…) |
| Unpack an installer without running it | `run 7z x setup.exe -o/tmp/setup` (works for many NSIS and 7-Zip installers) |

Drive `C:` is `~/.wine/drive_c` and `Z:` is the Linux root, so `Z:\home\agent\Documents` is `~/Documents`.
Programs start in the home folder, and the Windows Desktop, Documents, Downloads and Pictures folders are the
Linux ones, so files saved by Windows programs land where `run`, `cp` and `files` see them.

**Snapshot after a long install**: `minion snapshot win app-installed`. Restoring it is faster than reinstalling.

## How agents see Wine windows

Wine doesn't expose an accessibility tree, so `see` falls back to **OCR** automatically. You still get `@ids`:

```text
$ minion see
Screen 1280x800 · 1 window
  [1] "Untitled - Notepad" — exe (focused) at 0,0 1280x770

Text on "Untitled - Notepad" (OCR):
  @3 "File" (16,37)
  @4 "Edit" (48,37)
  @5 "Search" (88,37)
  @6 "View Help" (149,37)
  @7 "Hello from Wine Notepad. The quick brown fox jumps over the lazy dog 1234567890." (281,58)
  @9 "Ln 2, Col 42" (34,756)
```

- **Click by text or `@id`.** `click "File"` works. If a text click misses, click the `@id` from the latest
  `see`. Misses happen when OCR misreads a label (`"Lanquage"` for *Language*) or when a small dialog sits on
  the dark wallpaper.
- **Use a screenshot for icons, toolbars and single letters.** OCR skips icon-only buttons and one-character
  menu items (Notepad++'s *Language → A…Z*). Click those by coordinates.
- **Use the keyboard.** Menus, mnemonics (`alt+f`), `ctrl+s`, `Tab` and `Return` work as on Windows.
- **Use full paths in file dialogs.** Press `ctrl+a` in the *File name* box and type a full path, then
  `Return`. Linux paths such as `/home/agent/Documents/report.txt` work. Windows paths work too, but see the
  backslash note below.
- **Read results with `run`, not with your eyes.** Check `ls ~/Documents` or `cat` the saved file. That's exact,
  while OCR text can contain small errors (`?-Zip` for *7-Zip*).
- **Backslashes in `act` strings.** In act steps `\n` is Return and `\t` is Tab, so a path such as
  `C:\temp\new` needs doubled backslashes there: `act "type C:\\temp\\new"`. `minion type 'C:\temp\new'` and
  JSON actions type the text exactly as given.

## What the profile sets up

| | |
|---|---|
| Wine | Debian trixie's Wine 10.0 (`wine`, `wine64`, `libwine`, `fonts-wine`) |
| 32-bit programs | Run in Wine's WoW64 mode: the 32-bit Windows DLLs from `libwine:i386` are added to the 64-bit Wine. No i386 Linux libraries are needed (`wine32:i386` would add ~850 MB), and 32-bit programs use the 64-bit Mesa for OpenGL. The wrapper's misleading "wine32 is missing" hint is removed |
| Wine prefix | `~/.wine` (Windows 10), created at build time, so the first program starts in about 3 s |
| No prompts | Created without the Mono and Gecko download prompts. No crash dialog: a crashing program just closes, and the backtrace goes to the log |
| Clean desktop | `winemenubuilder` is off, so installers can't add menu entries or take over file types |
| Steadier screens | No blinking caret in Windows programs |
| Fonts | Wine's fonts, plus Liberation fonts standing in for Arial, Times New Roman and Courier New (metric-compatible) |
| File types | `minion open` runs `.exe` and `.msi` files with Wine. Wine is also the `xdg-open` handler for `.exe`, `.msi`, `.lnk`, `.bat` and `.url` |
| Tools | `winetricks`, `7z`, `unzip`, `cabextract`, `file` |
| Apps | Explorer, Registry Editor, Command Prompt, Wine Settings (`winecfg`), Notepad |
| Size | Debian ships Wine's Windows DLLs with debug info, and every prefix copies them. Stripping it saves ~1.8 GB |

The registry defaults live in `/usr/local/share/minion/wine-agent.reg`. To use a second prefix, create it and
apply them: `WINEPREFIX=~/.wine2 wineboot -i && WINEPREFIX=~/.wine2 wine regedit /S /usr/local/share/minion/wine-agent.reg`.

## Measured

On a 2-vCPU VM. "Idle" means no Windows program has run yet: Wine's services start with the first one.

| | |
|---|---|
| Download | **717 MB** compressed (`browser` is 363 MB), 2.84 GB on disk |
| Build from `browser` | 2 min 21 s |
| Ready in | 1.5 s |
| Idle RAM | **56 MB** |
| RAM with Notepad open | 267 MB (Wine's services take about 200 MB) |
| RAM with 7-Zip File Manager or Notepad++ open | 362 MB / 378 MB |
| First Windows program (Notepad) | 2.8–3.2 s to its window |
| Later programs | 2–4 s (Registry Editor 2.0 s, 7-Zip File Manager 2.8 s, Notepad++ 3.8 s) |
| `see` of Notepad (OCR) | about 1 s, ~85 tokens |

## What was tested

| Status | |
|---|---|
| Works | Notepad: typing, menus, *Save As* into `~/Documents`. Explorer, Registry Editor, Command Prompt (`cmd`), Wine Settings |
| Works | **32-bit installer**: 7-Zip 26.04 (`7z2604.exe`, 7-Zip's own installer) opened with `open ~/Downloads/7z2604.exe`, installed with one click, then 7-Zip File Manager (32-bit) ran and *Help → About* was read with OCR |
| Works | **64-bit portable app**: Notepad++ 8.9.8.1 (x64 zip). Typed code, chose *Language → P → Python* from the menus, saved to `~/Documents` with a typed Linux path |
| Works | 32-bit PuTTY started from a 64-bit Wine process (WoW64 child processes) |
| Partly | **MSI**: `open ~/Downloads/7z2604-x64.msi` shows the setup wizard, and cancelling it works. A silent `msiexec /i … /qn` ran to the end (exit 0) but copied nothing, because the same 7-Zip version was already installed (normal MSI versioning). A clean silent MSI install is still unverified |
| Not tested | NSIS and Inno Setup installers, `.lnk` and `.bat` files, winetricks verbs, .NET programs, programs that embed Internet Explorer |

## Limitations

- **No accessibility tree.** Everything is OCR and screenshots. OCR is good on menus, dialogs and text areas,
  but it misreads some glyphs, skips single characters and icons, and reads selected (highlighted) text poorly.
- **amd64 only.** On arm64 hosts (Apple Silicon, Graviton) the image build stops with a clear message.
- **.NET programs** need Wine Mono, which isn't preinstalled (about 80 MB download, more on disk). Install it
  when needed (untested here):
  `run "curl -fsSLO https://dl.winehq.org/wine/wine-mono/9.4.0/wine-mono-9.4.0-x86.msi && wine msiexec /i wine-mono-9.4.0-x86.msi /qn"`.
  Programs that embed Internet Explorer (some installers, `.chm` help) need Wine Gecko 2.47.4
  (`wine-gecko-2.47.4-x86_64.msi` and `-x86.msi` from `https://dl.winehq.org/wine/wine-gecko/2.47.4/`), and Wine
  may offer to download it when one starts.
- **Some programs need more Wine components** (Visual C++ runtimes, fonts, .NET Framework). Use `winetricks`.
  Its built-in checksums can go stale; if a download is rejected, fetch the latest winetricks from
  `https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks`.
- **Won't work**: anti-cheat and DRM that need kernel drivers, apps that require a GPU (games run on the
  software renderer, if at all), UWP/Store apps, 16-bit programs (WoW64 mode can't run them), sound and printing.
- 32-bit programs log `starting … in experimental wow64 mode`. That's informational.
- Typing a drive-relative path such as `C:file.txt` into a Wine file dialog can crash the program (a Wine bug).
  Use full paths.

## Troubleshooting

| Symptom | Try |
|---|---|
| `open` says nothing appeared | Big installers can take longer than the 12 s wait: `see` again, or check `run "tail -50 $MINION_RUNTIME_DIR/apps.log"` |
| A program closed by itself | It crashed (there's no crash dialog). Look for `Unhandled` in `$MINION_RUNTIME_DIR/apps.log` |
| `err:module:import_dll Library X.dll not found` | A runtime is missing: `winetricks -q vcrun2022`, or the DLL that winetricks names for it |
| A program hangs | `run wineserver -k` closes every Windows program |
| More logging | `run "WINEDEBUG=+loaddll wine app.exe"` (default is `fixme-all`, which hides only the noise) |
| Start over | Restore a snapshot taken before installing. Rebuilding the prefix (`rm -rf ~/.wine`, then `WINEDLLOVERRIDES="mscoree,mshtml=" wineboot -i` and `wine regedit /S /usr/local/share/minion/wine-agent.reg`) is slow |
