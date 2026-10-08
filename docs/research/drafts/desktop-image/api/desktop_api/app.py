"""Minion desktop control API: REST (FastAPI) + MCP (streamable HTTP at /mcp) on one port.

REST
  GET  /health                     liveness + display/VNC/noVNC status (no auth)
  GET  /screenshot?scale=&format=  PNG (default) or JPEG of the display
  POST /action   {action, params}  one computer_toolset_20260801 member
  POST /actions  {actions:[...]}   batch: in order, stop at first failure
  POST /bash     {cmd, timeout}    bash -c as the desktop user, DISPLAY set
  POST /open     {url|app}         launch browser/app, wait for its window
  GET  /windows                    wmctrl window list
MCP
  /mcp  (streamable HTTP, stateless, JSON responses) - same capabilities as tools.
Auth
  If API_TOKEN is set, every route except /health requires "Authorization: Bearer <token>".
"""

from __future__ import annotations

import asyncio
import hmac
import os
import socket
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import ToolAnnotations
from pydantic import BaseModel, Field

from . import procs
from .computer import MEMBERS, ActionError, Computer, run_batch

VERSION = "0.1.0"
API_TOKEN = os.environ.get("API_TOKEN", "")
VNC_PORT = int(os.environ.get("VNC_PORT", "5900"))
NOVNC_PORT = int(os.environ.get("NOVNC_PORT", "6080"))

computer = Computer()

# --------------------------------------------------------------------------- MCP
mcp = MCPServer(
    name="minion-desktop",
    title="Minion built-in desktop",
    version=VERSION,
    instructions=(
        "Controls a Linux desktop (X11, 1280x800 by default) running in a Docker container. "
        "Take a screenshot first, then act with pixel coordinates from that screenshot. "
        "Use open_url / open_app to launch a browser or programs, run_bash for shell commands "
        "(runs as the unprivileged desktop user with DISPLAY set)."
    ),
)

_READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)


def _mcp_result(res, extra_screenshot: bytes | None = None) -> list[Any]:
    out: list[Any] = []
    if res.output:
        out.append(res.output)
    if res.image is not None:
        out.append(Image(data=res.image, format=res.image_format))
    if extra_screenshot is not None:
        out.append(Image(data=extra_screenshot, format="png"))
    return out or ["OK"]


async def _act(action: str, params: dict[str, Any], screenshot_after: bool = False) -> list[Any]:
    try:
        res = await computer.run(action, params)
        shot = None
        if screenshot_after and action not in ("screenshot", "zoom"):
            await asyncio.sleep(0.3)
            shot, _, _ = await computer.screenshot()
        return _mcp_result(res, shot)
    except ActionError as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations=_READ_ONLY, structured_output=False)
async def screenshot() -> Image:
    """Capture the whole desktop as a PNG. Coordinates for other tools use this image's pixel space."""
    data, _, _ = await computer.screenshot()
    return Image(data=data, format="png")


@mcp.tool(annotations=_READ_ONLY, structured_output=False)
async def zoom(x0: int, y0: int, x1: int, y1: int) -> list[Any]:
    """Return the region [x0,y0]-[x1,y1] of the screen at full resolution, enlarged to screenshot size."""
    return await _act("zoom", {"region": [x0, y0, x1, y1]})


@mcp.tool(structured_output=False)
async def computer_action(
    action: Annotated[str, Field(description="One of: " + ", ".join(MEMBERS))],
    params: Annotated[
        dict[str, Any] | None,
        Field(description="Member input exactly as Claude's computer_toolset_20260801 uses it, e.g. "
                          '{"coordinate":[500,300]} or {"text":"ctrl+s","repeat":1}'),
    ] = None,
    screenshot_after: bool = False,
) -> list[Any]:
    """Run any Claude computer-use toolset action (left_click, type, key, scroll, left_click_drag, ...)."""
    return await _act(action, params or {}, screenshot_after)


@mcp.tool(structured_output=False)
async def click(
    x: int,
    y: int,
    button: Literal["left", "right", "middle"] = "left",
    clicks: Annotated[int, Field(ge=1, le=3)] = 1,
    modifiers: Annotated[str | None, Field(description="e.g. 'shift' or 'ctrl+shift'")] = None,
    screenshot_after: bool = False,
) -> list[Any]:
    """Click at (x, y). clicks=2/3 for double/triple left click."""
    if button == "left":
        action = {1: "left_click", 2: "double_click", 3: "triple_click"}[clicks]
    else:
        action = f"{button}_click"
    params: dict[str, Any] = {"coordinate": [x, y]}
    if modifiers:
        params["text"] = modifiers
    return await _act(action, params, screenshot_after)


@mcp.tool(structured_output=False)
async def mouse_move(x: int, y: int) -> list[Any]:
    """Move the mouse pointer to (x, y) without clicking (hover)."""
    return await _act("mouse_move", {"coordinate": [x, y]})


@mcp.tool(structured_output=False)
async def drag(start_x: int, start_y: int, end_x: int, end_y: int, screenshot_after: bool = False) -> list[Any]:
    """Press the left button at (start_x, start_y), drag to (end_x, end_y) and release."""
    return await _act("left_click_drag", {"start_coordinate": [start_x, start_y], "coordinate": [end_x, end_y]},
                      screenshot_after)


@mcp.tool(structured_output=False)
async def scroll(
    direction: Literal["up", "down", "left", "right"],
    amount: Annotated[int, Field(ge=1, le=100)] = 3,
    x: int | None = None,
    y: int | None = None,
    screenshot_after: bool = False,
) -> list[Any]:
    """Scroll the mouse wheel `amount` clicks, at (x, y) if given, else at the pointer."""
    params: dict[str, Any] = {"scroll_direction": direction, "scroll_amount": amount}
    if x is not None and y is not None:
        params["coordinate"] = [x, y]
    return await _act("scroll", params, screenshot_after)


@mcp.tool(structured_output=False)
async def type_text(text: str, screenshot_after: bool = False) -> list[Any]:
    """Type literal text (Unicode, incl. Hebrew) at the current keyboard focus."""
    return await _act("type", {"text": text}, screenshot_after)


@mcp.tool(structured_output=False)
async def press_key(
    keys: Annotated[str, Field(description="xdotool keysym or combo: 'Return', 'ctrl+l', 'alt+Tab', 'ctrl+a Delete'")],
    repeat: Annotated[int, Field(ge=1, le=100)] = 1,
    screenshot_after: bool = False,
) -> list[Any]:
    """Press a key or key combination."""
    return await _act("key", {"text": keys, "repeat": repeat}, screenshot_after)


@mcp.tool(annotations=_READ_ONLY, structured_output=False)
async def cursor_position() -> list[Any]:
    """Return the mouse pointer position as 'X=.., Y=..'."""
    return await _act("cursor_position", {})


@mcp.tool(structured_output=False)
async def wait(seconds: Annotated[float, Field(ge=0, le=300)] = 1.0, screenshot_after: bool = True) -> list[Any]:
    """Wait (e.g. for a page to load), then optionally return a screenshot."""
    return await _act("wait", {"duration": seconds}, screenshot_after)


@mcp.tool(structured_output=False)
async def run_bash(
    cmd: str,
    timeout: Annotated[float, Field(ge=1, le=3600)] = 60,
    background: bool = False,
) -> str:
    """Run a bash command inside the desktop container as the desktop user (DISPLAY set). Returns JSON."""
    import json

    try:
        return json.dumps(await procs.run_bash(cmd, timeout=timeout, background=background), ensure_ascii=False)
    except ActionError as e:
        raise ToolError(str(e)) from e


@mcp.tool(structured_output=False)
async def open_url(
    url: str,
    browser: Literal["chromium", "firefox"] | None = None,
    screenshot_after: bool = True,
) -> list[Any]:
    """Open a URL in the desktop browser (new window or tab) and bring it to front."""
    import json

    try:
        res = await procs.open_target(url=url, browser=browser)
    except ActionError as e:
        raise ToolError(str(e)) from e
    out: list[Any] = [json.dumps(res, ensure_ascii=False)]
    if screenshot_after:
        await asyncio.sleep(1.5)
        data, _, _ = await computer.screenshot()
        out.append(Image(data=data, format="png"))
    return out


@mcp.tool(structured_output=False)
async def open_app(
    app: Annotated[str, Field(description="chromium, firefox, terminal, editor, files, calc, writer, or a command")],
    args: list[str] | None = None,
    screenshot_after: bool = True,
) -> list[Any]:
    """Launch a desktop application and wait for its window."""
    import json

    try:
        res = await procs.open_target(app=app, args=args)
    except ActionError as e:
        raise ToolError(str(e)) from e
    out: list[Any] = [json.dumps(res, ensure_ascii=False)]
    if screenshot_after:
        await asyncio.sleep(0.8)
        data, _, _ = await computer.screenshot()
        out.append(Image(data=data, format="png"))
    return out


@mcp.tool(annotations=_READ_ONLY, structured_output=False)
async def list_windows() -> str:
    """List open windows (id, pid, wm_class, title)."""
    import json

    return json.dumps(await procs.list_windows(), ensure_ascii=False)


def _mcp_security() -> TransportSecuritySettings:
    hosts = [h.strip() for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    if not hosts:  # private docker network: Host is e.g. "desktop:8000"
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    origins = [o.strip() for o in os.environ.get("MCP_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    return TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=hosts,
                                     allowed_origins=origins)


mcp_http_app = mcp.streamable_http_app(
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
    host="0.0.0.0",
    transport_security=_mcp_security(),
)


# -------------------------------------------------------------------------- REST
@asynccontextmanager
async def lifespan(_app: FastAPI):
    await computer.init()
    # Mounted Starlette sub-apps don't get lifespan events; run the MCP session manager here.
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Minion Desktop API", version=VERSION, lifespan=lifespan)


class BearerAuth:
    """Pure-ASGI auth so it also covers the mounted MCP app (and streaming responses)."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and API_TOKEN and scope.get("path") != "/health":
            headers = dict(scope.get("headers") or [])
            auth = headers.get(b"authorization", b"").decode()
            if not hmac.compare_digest(auth, f"Bearer {API_TOKEN}"):
                resp = JSONResponse({"detail": "unauthorized"}, status_code=401,
                                    headers={"WWW-Authenticate": "Bearer"})
                await resp(scope, receive, send)
                return
        await self.inner(scope, receive, send)


app.add_middleware(BearerAuth)


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def _x_up() -> bool:
    num = computer.display.lstrip(":").split(".")[0]
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(f"/tmp/.X11-unix/X{num}")
        return True
    except OSError:
        return False
    finally:
        s.close()


@app.get("/health")
async def health():
    comps = {"x11": _x_up(), "vnc": _port_open(VNC_PORT), "novnc": _port_open(NOVNC_PORT)}
    ok = all(comps.values())
    return JSONResponse(
        {"status": "ok" if ok else "degraded", "version": VERSION, "components": comps, **computer.info()},
        status_code=200 if ok else 503,
    )


@app.get("/screenshot", responses={200: {"content": {"image/png": {}, "image/jpeg": {}}}})
async def get_screenshot(
    scale: Annotated[float | None, Query(gt=0, le=4, description="explicit scale; default = model space")] = None,
    format: Literal["png", "jpeg"] = "png",
    quality: Annotated[int, Query(ge=10, le=95)] = 80,
):
    try:
        data, w, h = await computer.screenshot(scale=scale, fmt=format, quality=quality)
    except ActionError as e:
        raise HTTPException(503, str(e))
    return Response(
        data,
        media_type=f"image/{format}",
        headers={"X-Image-Width": str(w), "X-Image-Height": str(h),
                 "X-Screen-Width": str(computer.width), "X-Screen-Height": str(computer.height),
                 "Cache-Control": "no-store"},
    )


class ActionIn(BaseModel):
    action: str = Field(description="computer_toolset_20260801 member name, e.g. left_click")
    params: dict[str, Any] = Field(default_factory=dict, description="member input, e.g. {'coordinate':[10,20]}")
    screenshot_after: bool = False


@app.post("/action")
async def post_action(body: ActionIn):
    try:
        res = await computer.run(body.action, body.params)
    except ActionError as e:
        return JSONResponse({"ok": False, "is_error": True, "error": str(e)}, status_code=400)
    out = res.to_json()
    if body.screenshot_after and res.image is None:
        await asyncio.sleep(0.3)
        data, _, _ = await computer.screenshot()
        import base64

        out["image"] = {"media_type": "image/png", "data": base64.b64encode(data).decode()}
    return out


class ActionsIn(BaseModel):
    actions: list[ActionIn]


@app.post("/actions")
async def post_actions(body: ActionsIn):
    """Toolset batch semantics: run in order, stop at first failure, answer every item."""
    return {"results": await run_batch(computer, [a.model_dump() for a in body.actions])}


class BashIn(BaseModel):
    cmd: str
    timeout: float = Field(60, ge=1, le=3600)
    cwd: str | None = None
    env: dict[str, str] | None = None
    background: bool = False


@app.post("/bash")
async def post_bash(body: BashIn):
    try:
        return await procs.run_bash(body.cmd, body.timeout, body.cwd, body.env, body.background)
    except ActionError as e:
        raise HTTPException(400, str(e))


class OpenIn(BaseModel):
    url: str | None = None
    app: str | None = None
    args: list[str] | None = None
    browser: Literal["chromium", "firefox"] | None = None
    wait: bool = True
    timeout: float = Field(20, ge=1, le=120)
    maximize: bool = True


@app.post("/open")
async def post_open(body: OpenIn):
    try:
        return await procs.open_target(body.url, body.app, body.args, body.browser, body.wait, body.timeout,
                                       body.maximize)
    except ActionError as e:
        raise HTTPException(400, str(e))


@app.get("/windows")
async def get_windows():
    return {"windows": await procs.list_windows()}


# Must be last: catch-all mount that serves /mcp.
app.mount("/", mcp_http_app)
