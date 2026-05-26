import asyncio
import pathlib
import webbrowser

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


async def _handle_submit(request: web.Request) -> web.Response:
    result_future: asyncio.Future[str] = request.app["result_future"]

    if result_future.done():
        return web.Response(status=409, text="Already submitted")

    try:
        body = await request.json()
    except Exception:
        return web.Response(status=400, text="Invalid JSON")

    image = body.get("image")
    if not isinstance(image, str) or not image:
        return web.Response(status=400, text="Missing or empty 'image' field")

    result_future.set_result(image)
    return web.Response(status=200, text="OK")


async def start_canvas_server() -> tuple[web.AppRunner, str, int, "asyncio.Future[str]"]:
    """Start aiohttp on an OS-assigned port. Returns (runner, host, port, result_future)."""
    result_future: asyncio.Future[str] = asyncio.get_event_loop().create_future()

    http_app = web.Application()
    http_app["result_future"] = result_future
    http_app.router.add_get("/", _serve_html)
    http_app.router.add_get("/canvas.css", _serve_css)
    http_app.router.add_post("/submit", _handle_submit)

    runner = web.AppRunner(http_app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    port = runner.addresses[0][1]
    return runner, "127.0.0.1", port, result_future


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

    hint = (arguments or {}).get("hint", "")
    url = ""
    runner = None

    try:
        runner, host, port, result_future = await start_canvas_server()
        url = f"http://{host}:{port}/"
        if hint:
            url += f"?hint={hint}"

        webbrowser.open(url)

        base64_png = await asyncio.wait_for(result_future, timeout=600)
    finally:
        if runner:
            await stop_canvas_server(runner)

    return [
        types.ImageContent(type="image", data=base64_png, mimeType="image/png")
    ]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
