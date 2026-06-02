import asyncio
import pathlib
import urllib.parse
import webbrowser

from aiohttp import web
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

BASE_DIR = pathlib.Path(__file__).parent

app = Server("canvas-mcp")

_session_active = False


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
        ),
        types.Tool(
            name="describe_sketch",
            description=(
                "Opens a drawing canvas in the user's browser, then runs the sketch "
                "through a vision model and returns a text description. Use instead of "
                "open_canvas when the agent cannot accept images, or when a reusable "
                "text description is more useful than the raw PNG."
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
        ),
    ]



@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.ContentBlock]:
    global _session_active

    if name not in ("open_canvas", "describe_sketch"):
        raise ValueError(f"Unknown tool: {name}")

    if _session_active:
        raise RuntimeError(
            "A canvas session is already open. "
            "Please submit or close the existing canvas before opening a new one."
        )

    _session_active = True
    runner = None

    try:
        runner, host, port, result_future = await start_canvas_server()

        hint = (arguments or {}).get("hint", "")
        qs = ("?" + urllib.parse.urlencode({"hint": hint})) if hint else ""
        url = f"http://{host}:{port}/{qs}"

        webbrowser.open(url)

        try:
            base64_png = await asyncio.wait_for(result_future, timeout=600)
        except asyncio.TimeoutError:
            raise RuntimeError(
                "Canvas timed out after 600 seconds with no submission."
            )
    finally:
        if runner:
            await stop_canvas_server(runner)
        _session_active = False

    if name == "open_canvas":
        return [types.ImageContent(type="image", data=base64_png, mimeType="image/png")]

    return [
        types.ImageContent(type="image", data=base64_png, mimeType="image/png"),
        types.TextContent(
            type="text",
            text=(
                "The user has submitted a sketch. "
                "Please describe it in detail — focus on the layout, shapes, labels, "
                "and any visual intent that would help understand what they want to build or communicate."
            ),
        ),
    ]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
