"""Aggregation: connect to a downstream MCP server (stdio here; URL/SSE work the same way), re-export its tools
through gateway.registry with a prefix, and re-sync when the downstream tool list changes (both eras).

Pattern: one OWNER TASK per downstream server. The task enters `async with Client(...)` and exits it itself
(anyio cancel scopes must be exited by the task that entered them), so servers can be added/removed at runtime
from a long-lived task group (e.g. the FastAPI lifespan) without AsyncExitStack scope violations.
"""
import sys
from pathlib import Path
from typing import Any

import anyio
from anyio.abc import TaskStatus

import mcp.types as types
from mcp import Client, StdioServerParameters
from mcp.client.subscriptions import ToolsListChanged

import gateway  # gateway.registry, gateway.server

HERE = Path(__file__).parent


class Downstream:
    def __init__(self, prefix: str, target: Any) -> None:
        self.prefix, self.target = prefix, target  # target: URL str | StdioServerParameters | Transport
        self.client: Client | None = None
        self.names: set[str] = set()
        self._stop = anyio.Event()

    async def _on_message(self, msg) -> None:  # legacy-era (initialize handshake) downstream servers push here
        if not isinstance(msg, Exception) and msg.method == "notifications/tools/list_changed":
            await self.sync()

    async def run(self, *, task_status: TaskStatus[None] = anyio.TASK_STATUS_IGNORED) -> None:
        async with Client(self.target, message_handler=self._on_message, read_timeout_seconds=60) as client:
            self.client = client
            await self.sync()
            async with anyio.create_task_group() as tg:
                caps = client.server_capabilities.tools
                if client.protocol_version == "2026-07-28" and caps and caps.list_changed:
                    await tg.start(self._listen)
                task_status.started()
                await self._stop.wait()
                tg.cancel_scope.cancel()
        for name in self.names:
            await gateway.registry.remove(name)
        self.names.clear()

    def stop(self) -> None:
        self._stop.set()

    async def _listen(self, *, task_status: TaskStatus[None] = anyio.TASK_STATUS_IGNORED) -> None:
        assert self.client
        async with self.client.listen(tools_list_changed=True) as sub:  # entered => acknowledged
            task_status.started()
            async for ev in sub:
                if isinstance(ev, ToolsListChanged):
                    await self.sync()

    async def sync(self) -> None:
        assert self.client
        tools: list[types.Tool] = []
        cursor = None
        while True:
            page = await self.client.list_tools(cursor=cursor, cache_mode="refresh")
            tools += page.tools
            if (cursor := page.next_cursor) is None:
                break
        new = {f"{self.prefix}__{t.name}": t for t in tools}
        for gone in self.names - new.keys():
            await gateway.registry.remove(gone)
        for name, t in new.items():
            await gateway.registry.add(t.model_copy(update={"name": name}), self._forwarder(t.name))
        self.names = set(new)

    def _forwarder(self, remote_name: str):
        async def fn(args: dict[str, Any]) -> types.CallToolResult:
            assert self.client
            return await self.client.call_tool(remote_name, args)  # CallToolResult passes through untouched

        return fn


async def main() -> None:
    ds = Downstream("user", StdioServerParameters(command=sys.executable, args=[str(HERE / "stdio_tool_server.py")]))
    async with anyio.create_task_group() as tg:  # in Minion: a task group owned by the FastAPI lifespan
        await tg.start(ds.run)
        print("downstream era:", ds.client.protocol_version)
        async with Client(gateway.server) as gw:  # in-process client against the gateway's low-level Server
            print("gateway tools:", [t.name for t in (await gw.list_tools()).tools])
            print("user__add ->", (await gw.call_tool("user__add", {"a": 1, "b": 2})).structured_content)
            await gw.call_tool("user__enable_late_tool", {})  # downstream adds a tool + notifies
            with anyio.fail_after(5):
                while "user__late_tool" not in ds.names:
                    await anyio.sleep(0.05)
            print("after downstream change:", [t.name for t in (await gw.list_tools(cache_mode="refresh")).tools])
            print("user__late_tool ->", (await gw.call_tool("user__late_tool", {"x": 7})).structured_content)
        ds.stop()  # runtime removal: owner task exits its Client and unregisters the tools
    print("after stop:", [t.name for t in gateway.registry.list()])


anyio.run(main)
