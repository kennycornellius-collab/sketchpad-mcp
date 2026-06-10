import asyncio
import time
import urllib.parse
import uuid
import webbrowser
from importlib.resources import files

from aiohttp import web
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

_PACKAGE_FILES = files("canvas_mcp")

app = Server(
    "canvas-mcp",
    instructions=(
        "This server opens a drawing canvas in the user's browser and returns the sketch "
        "to the agent. Use open_canvas to receive the raw image, or describe_sketch to "
        "receive a text description. Invoke either tool when the user's visual intent is "
        "ambiguous, when they want to sketch a UI layout or diagram, annotate an image, "
        "or communicate anything that is faster to draw than to describe in words."
    ),
)

_session_active: bool = False
_runner: web.AppRunner | None = None
_port: int = 0
_pending_future: "asyncio.Future[str] | None" = None
_current_hint: str = ""
_current_call_id: str = ""
_last_heartbeat: float = 0.0


# ---------------------------------------------------------------------------
# Persistent aiohttp canvas server
# ---------------------------------------------------------------------------

async def _serve_html(request: web.Request) -> web.Response:
    html = (_PACKAGE_FILES / "canvas.html").read_text(encoding="utf-8")
    return web.Response(text=html, content_type="text/html")


async def _serve_css(request: web.Request) -> web.Response:
    css = (_PACKAGE_FILES / "canvas.css").read_text(encoding="utf-8")
    return web.Response(text=css, content_type="text/css")


async def _handle_submit(request: web.Request) -> web.Response:
    global _pending_future

    if _pending_future is None or _pending_future.done():
        return web.Response(status=409, text="No active canvas session")

    try:
        body = await request.json()
    except Exception:
        return web.Response(status=400, text="Invalid JSON")

    image = body.get("image")
    if not isinstance(image, str) or not image:
        return web.Response(status=400, text="Missing or empty 'image' field")

    _pending_future.set_result(image)
    return web.Response(status=200, text="OK")


async def _handle_state(request: web.Request) -> web.Response:
    global _last_heartbeat
    _last_heartbeat = time.monotonic()
    return web.json_response({"hint": _current_hint, "call_id": _current_call_id})


async def ensure_server_running() -> None:
    """Start the persistent aiohttp server on first call; no-op thereafter."""
    global _runner, _port
    if _runner is not None:
        return
    http_app = web.Application()
    http_app.router.add_get("/", _serve_html)
    http_app.router.add_get("/canvas.css", _serve_css)
    http_app.router.add_post("/submit", _handle_submit)
    http_app.router.add_get("/state", _handle_state)
    _runner = web.AppRunner(http_app)
    await _runner.setup()
    site = web.TCPSite(_runner, "127.0.0.1", 0)
    await site.start()
    _port = _runner.addresses[0][1]



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
    global _session_active, _current_hint, _current_call_id, _pending_future

    if name not in ("open_canvas", "describe_sketch"):
        raise ValueError(f"Unknown tool: {name}")

    if _session_active:
        raise RuntimeError(
            "A canvas session is already open. "
            "Please submit or close the existing canvas before opening a new one."
        )

    _session_active = True

    try:
        await ensure_server_running()

        hint = (arguments or {}).get("hint", "")
        _current_hint = hint
        _current_call_id = uuid.uuid4().hex
        _pending_future = asyncio.get_running_loop().create_future()

        tab_alive = (time.monotonic() - _last_heartbeat) < 8.0
        if not tab_alive:
            qs = ("?" + urllib.parse.urlencode({"hint": hint})) if hint else ""
            webbrowser.open(f"http://127.0.0.1:{_port}/{qs}")

        try:
            base64_png = await asyncio.wait_for(_pending_future, timeout=600)
        except asyncio.TimeoutError:
            raise RuntimeError(
                "Canvas timed out after 600 seconds with no submission."
            )
    finally:
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


def cli() -> None:
    """Synchronous entry point for the canvas-mcp console script."""
    asyncio.run(main())


if __name__ == "__main__":
    cli()
