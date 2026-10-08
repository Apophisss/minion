"""Minion-style MCP gateway: FastAPI app + low-level MCP Server mounted at /mcp (Streamable HTTP).

- Tools live in a plain dict that changes at runtime (raw JSON schemas, no pydantic signature magic).
- tools/list_changed is pushed to BOTH protocol eras:
    * 2026-07-28 clients -> subscriptions/listen stream (InMemorySubscriptionBus + ListenHandler)
    * 2025-xx (initialize-handshake) clients -> the session's standalone GET SSE stream
      (Connection.send_tool_list_changed()), connections tracked by a server middleware.
- Static bearer-token auth in front of /mcp (pure ASGI middleware; SSE-safe).

Run:  MINION_TOKEN=secret uvicorn gateway:app --host 0.0.0.0 --port 8765
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import weakref
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from mcp_types.version import MODERN_PROTOCOL_VERSIONS
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

import mcp.types as types
from mcp.server import NotificationOptions, Server, ServerRequestContext
from mcp.server.connection import Connection
from mcp.server.context import CallNext, HandlerResult
from mcp.server.models import InitializationOptions
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp, StreamableHTTPSessionManager
from mcp.server.subscriptions import InMemorySubscriptionBus, ListenHandler, ToolsListChanged

log = logging.getLogger("gateway")
TOKEN = os.environ.get("MINION_TOKEN", "secret")

# ----------------------------------------------------------------------------- registry

ToolFn = Callable[[dict[str, Any]], Awaitable[types.CallToolResult]]


@dataclass
class ToolEntry:
    tool: types.Tool
    fn: ToolFn


class ToolRegistry:
    """name -> (Tool, async fn). Any mutation notifies every connected MCP client."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}
        self.bus = InMemorySubscriptionBus()  # modern-era fan-out
        self.legacy_connections: weakref.WeakSet[Connection] = weakref.WeakSet()  # handshake-era sessions

    def list(self) -> list[types.Tool]:
        return [e.tool for e in self._tools.values()]

    def get(self, name: str) -> ToolEntry | None:
        return self._tools.get(name)

    async def add(self, tool: types.Tool, fn: ToolFn) -> None:
        self._tools[tool.name] = ToolEntry(tool, fn)
        await self.notify_changed()

    async def remove(self, name: str) -> bool:
        existed = self._tools.pop(name, None) is not None
        if existed:
            await self.notify_changed()
        return existed

    async def notify_changed(self) -> None:
        await self.bus.publish(ToolsListChanged())  # -> every open subscriptions/listen stream
        for conn in list(self.legacy_connections):  # -> every legacy session's standalone stream
            await conn.send_tool_list_changed()  # best-effort, never raises


registry = ToolRegistry()

# ----------------------------------------------------------------------------- MCP handlers


async def list_tools(ctx: ServerRequestContext, params: types.PaginatedRequestParams | None) -> types.ListToolsResult:
    # Simple cursor pagination over the dict (page size 50).
    tools = registry.list()
    start = int(params.cursor) if params and params.cursor else 0
    page = tools[start : start + 50]
    nxt = str(start + 50) if start + 50 < len(tools) else None
    return types.ListToolsResult(tools=page, next_cursor=nxt)


async def call_tool(ctx: ServerRequestContext, params: types.CallToolRequestParams) -> types.CallToolResult:
    entry = registry.get(params.name)
    if entry is None:
        # Low-level Server: an exception would become a JSON-RPC error (-32603). Return is_error so the model can read it.
        return types.CallToolResult(content=[types.TextContent(type="text", text=f"Unknown tool: {params.name}")], is_error=True)
    try:
        return await entry.fn(params.arguments or {})
    except Exception as exc:  # noqa: BLE001
        return types.CallToolResult(content=[types.TextContent(type="text", text=f"{type(exc).__name__}: {exc}")], is_error=True)


class GatewayServer(Server):
    """Advertise tools.listChanged=true to handshake-era clients too.

    The streamable-HTTP manager calls create_initialization_options() with no args
    (NotificationOptions() -> listChanged=False). For 2026-07-28 clients the flag is
    derived automatically from on_subscriptions_listen being set.
    """

    def create_initialization_options(
        self,
        notification_options: NotificationOptions | None = None,
        experimental_capabilities: dict[str, dict[str, Any]] | None = None,
        extensions: dict[str, dict[str, Any]] | None = None,
    ) -> InitializationOptions:
        return super().create_initialization_options(
            notification_options or NotificationOptions(tools_changed=True), experimental_capabilities, extensions
        )


async def track_legacy_connections(ctx: ServerRequestContext, call_next: CallNext) -> HandlerResult:
    """Server middleware: remember every handshake-era connection so we can push list_changed to it later."""
    if ctx.protocol_version not in MODERN_PROTOCOL_VERSIONS:
        conn: Connection = ctx.session._connection  # NOTE: private attr (no public accessor in 2.3.0)
        if conn not in registry.legacy_connections:
            registry.legacy_connections.add(conn)
            conn.exit_stack.callback(registry.legacy_connections.discard, conn)  # unwound when the session ends
    return await call_next(ctx)


server = GatewayServer(
    "minion-gateway",
    version="0.1.0",
    instructions="Minion aggregated MCP gateway",
    on_list_tools=list_tools,
    on_call_tool=call_tool,
    on_subscriptions_listen=ListenHandler(registry.bus),
)
server.middleware.append(track_legacy_connections)

session_manager = StreamableHTTPSessionManager(
    app=server,
    json_response=os.environ.get("MINION_JSON") == "1",  # False = SSE responses (needed for subscriptions/listen + request-scoped notifications)
    stateless=os.environ.get("MINION_STATELESS") == "1",  # False = legacy clients get Mcp-Session-Id + standalone GET stream (needed for list_changed push)
    security_settings=None,  # None = DNS-rebinding protection OFF (containers reach us by service name)
    session_idle_timeout=30 * 60,
)

# ----------------------------------------------------------------------------- auth (pure ASGI, SSE-safe)


class BearerAuth:
    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app, self.expected = app, f"Bearer {token}".encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and dict(scope["headers"]).get(b"authorization") != self.expected:
            resp = JSONResponse({"error": "unauthorized"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
            await resp(scope, receive, send)
            return
        await self.app(scope, receive, send)


# ----------------------------------------------------------------------------- FastAPI app


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with session_manager.run():  # REQUIRED: starts the manager's task group (and Server lifespan)
        yield


app = FastAPI(lifespan=lifespan)
# Exact path /mcp, no trailing-slash redirect; GET/POST/DELETE all go to the ASGI app.
app.router.routes.append(Route("/mcp", endpoint=BearerAuth(StreamableHTTPASGIApp(session_manager), TOKEN)))


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "tools": [t.name for t in registry.list()], "legacy_sessions": len(registry.legacy_connections)}


def _check(request: Request) -> None:
    if request.headers.get("authorization") != f"Bearer {TOKEN}":
        raise HTTPException(401)


@app.post("/admin/tools")
async def admin_add_tool(request: Request) -> dict[str, Any]:
    """Register a tool at runtime: {"name", "description", "input_schema", "template"}."""
    _check(request)
    body = await request.json()
    template: str = body.get("template", "{args}")

    async def fn(args: dict[str, Any]) -> types.CallToolResult:
        text = template.format(args=json.dumps(args), **args)
        return types.CallToolResult(content=[types.TextContent(type="text", text=text)], structured_content={"text": text, "args": args})

    tool = types.Tool(
        name=body["name"],
        description=body.get("description"),
        input_schema=body.get("input_schema") or {"type": "object", "properties": {}},
        output_schema={"type": "object", "properties": {"text": {"type": "string"}, "args": {"type": "object"}}, "required": ["text", "args"]},
    )
    await registry.add(tool, fn)
    return {"added": tool.name, "tools": [t.name for t in registry.list()]}


@app.delete("/admin/tools/{name}")
async def admin_remove_tool(name: str, request: Request) -> dict[str, Any]:
    _check(request)
    return {"removed": await registry.remove(name)}


# a built-in tool so the list is never empty
async def _echo(args: dict[str, Any]) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=str(args.get("text", "")))])


registry._tools["echo"] = ToolEntry(
    types.Tool(name="echo", description="Echo text back", input_schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}),
    _echo,
)
