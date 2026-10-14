"""Generates the JWM window manager configuration: one light process for windows and the taskbar."""

from __future__ import annotations

from xml.sax.saxutils import escape

FONT = "DejaVu Sans-9"


def config(
    apps: list[dict],
    wallpaper: str | None,
    terminal: str = "x-terminal-emulator",
    maximize: bool = True,
    tray_height: int = 30,
) -> str:
    items = []
    seen = set()
    for app in apps:
        name, cmd = app.get("name"), app.get("command")
        if not name or not cmd or name.lower() in seen:
            continue
        seen.add(name.lower())
        items.append(f'    <Program label="{escape(name)}">{escape(cmd)}</Program>')
    if "terminal" not in seen:
        items.append(f'    <Program label="Terminal">{escape(terminal)}</Program>')
    menu = "\n".join(items)
    background = (
        f'<Background type="scale">{escape(wallpaper)}</Background>'
        if wallpaper
        else '<Background type="solid">#0f172a</Background>'
    )
    groups = """
  <Group><Type>dialog</Type><Option>centered</Option></Group>"""
    if maximize:
        groups = (
            """
  <Group><Type>normal</Type><Option>maximized</Option></Group>"""
            + groups
        )
    return f"""<?xml version="1.0"?>
<JWM>
  <RootMenu onroot="3" label="Applications">
{menu}
  </RootMenu>
{groups}
  <Tray x="0" y="-1" height="{tray_height}" autohide="off" layer="above">
    <TrayButton label="  ◆ minion  " popup="Applications">root:3</TrayButton>
    <Spacer width="6"/>
    <TaskList maxwidth="260"/>
    <Clock format="%H:%M"><Button mask="123">exec:true</Button></Clock>
    <Spacer width="6"/>
  </Tray>

  <WindowStyle decorations="flat">
    <Font>{FONT}:bold</Font>
    <Width>3</Width>
    <Height>26</Height>
    <Corner>0</Corner>
    <Foreground>#cbd5e1</Foreground>
    <Background>#1e293b</Background>
    <Outline>#0f172a</Outline>
    <Opacity>1.0</Opacity>
    <Active>
      <Foreground>#ffffff</Foreground>
      <Background>#4f46e5</Background>
      <Outline>#312e81</Outline>
      <Opacity>1.0</Opacity>
    </Active>
  </WindowStyle>
  <TrayStyle decorations="flat">
    <Font>{FONT}</Font>
    <Background>#0b1020</Background>
    <Foreground>#e2e8f0</Foreground>
    <Opacity>1.0</Opacity>
  </TrayStyle>
  <TaskListStyle list="all" group="false" decorations="flat">
    <Font>{FONT}</Font>
    <Foreground>#cbd5e1</Foreground>
    <Background>#0b1020</Background>
    <Active>
      <Foreground>#ffffff</Foreground>
      <Background>#312e81</Background>
    </Active>
    <Minimized>
      <Foreground>#64748b</Foreground>
      <Background>#0b1020</Background>
    </Minimized>
  </TaskListStyle>
  <MenuStyle decorations="flat">
    <Font>{FONT}</Font>
    <Foreground>#e2e8f0</Foreground>
    <Background>#111827</Background>
    <Outline>#312e81</Outline>
    <Active>
      <Foreground>#ffffff</Foreground>
      <Background>#4f46e5</Background>
    </Active>
    <Opacity>1.0</Opacity>
  </MenuStyle>
  <PopupStyle>
    <Font>{FONT}</Font>
    <Foreground>#e2e8f0</Foreground>
    <Background>#111827</Background>
  </PopupStyle>

  <Desktops width="1" height="1">
    {background}
  </Desktops>

  <DoubleClickSpeed>400</DoubleClickSpeed>
  <DoubleClickDelta>3</DoubleClickDelta>
  <FocusModel>click</FocusModel>
  <SnapMode distance="8">border</SnapMode>
  <MoveMode>opaque</MoveMode>
  <ResizeMode>opaque</ResizeMode>

  <Key mask="A" key="Tab">nextstacked</Key>
  <Key mask="A" key="F4">close</Key>
  <Key mask="A" key="F10">maximize</Key>
  <Key mask="4" key="d">showdesktop</Key>

  <Mouse context="title" button="1">move</Mouse>
  <Mouse context="title" button="3">window</Mouse>
  <Mouse context="title" button="11">maximize</Mouse>
  <Mouse context="icon" button="1">window</Mouse>
  <Mouse context="border" button="1">resize</Mouse>
  <Mouse context="close" button="-1">close</Mouse>
  <Mouse context="maximize" button="-1">maximize</Mouse>
  <Mouse context="minimize" button="-1">minimize</Mouse>
</JWM>
"""
