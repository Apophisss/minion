import anyio, traceback
from mcp import Client
async def main():
    for mode in ("legacy", "auto"):
        try:
            async with Client("http://127.0.0.1:8765/mcp", mode=mode) as c:
                await c.list_tools()
        except BaseException as e:
            def walk(e, d=0):
                print("  "*d, mode, type(e).__module__, type(e).__name__, str(e)[:150], getattr(e, "code", None))
                for s in getattr(e, "exceptions", []) or []: walk(s, d+1)
            walk(e)
anyio.run(main)
