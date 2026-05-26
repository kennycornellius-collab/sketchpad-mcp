import asyncio
import pathlib

from aiohttp import web
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

BASE_DIR = pathlib.Path(__file__).parent

app = Server("canvas-mcp")


# ---------------------------------------------------------------------------
# Ephemeral aiohttp canvas server
# ---------------------------------------------------------------------------

async def _serve_html(request: web.Request) -> web.Response:
    html = (BASE_DIR / "canvas.html").read_text(encoding="utf-8")
    return web.Response(text=html, content_type="text/html")


async def _serve_css(request: web.Request) -> web.Response:
    css = (BASE_DIR / "canvas.css").read_text(encoding="utf-8")
    return web.Response(text=css, content_type="text/css")


async def start_canvas_server() -> tuple[web.AppRunner, str, int]:
    """Start aiohttp on an OS-assigned port. Returns (runner, host, port)."""
    http_app = web.Application()
    http_app.router.add_get("/", _serve_html)
    http_app.router.add_get("/concept.css", _serve_css)

    runner = web.AppRunner(http_app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    port = runner.addresses[0][1]
    return runner, "127.0.0.1", port


async def stop_canvas_server(runner: web.AppRunner) -> None:
    await runner.cleanup()


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="open_canvas",
            description=(
                "Opens a drawing canvas in the user's browser for them to sketch. "
                "Use when the user's visual description is ambiguous, when they want "
                "to sketch a UI/layout, or when they explicitly ask to draw. "
                "Returns the resulting image."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "hint": {
                        "type": "string",
                        "description": "Optional reminder shown above the canvas.",
                    }
                },
            },
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.ContentBlock]:
    if name != "open_canvas":
        raise ValueError(f"Unknown tool: {name}")

    return [types.TextContent(type="text", text="[canvas stub — not yet implemented]")]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
