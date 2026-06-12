import asyncio
import base64
import time

import pytest
from mcp import types

import sketchpad_mcp.server as server

VALID_PNG_B64 = base64.b64encode(server._PNG_MAGIC + b"\x00" * 16).decode()


@pytest.fixture
def no_browser(monkeypatch):
    """Stub out the real side effects: never open a browser or bind a port.

    Returns the list of URLs call_tool attempted to open.
    """
    opened: list[str] = []
    monkeypatch.setattr(server.webbrowser, "open", lambda url: opened.append(url) or True)

    async def fake_ensure_server_running() -> None:
        return None

    monkeypatch.setattr(server, "ensure_server_running", fake_ensure_server_running)
    return opened


async def _call_and_resolve(name: str, arguments: dict, result: str | None):
    """Run call_tool and resolve its pending future as the browser would."""
    task = asyncio.create_task(server.call_tool(name, arguments))
    for _ in range(1000):
        fut = server._pending_future
        if fut is not None and not fut.done():
            break
        await asyncio.sleep(0)
    else:
        task.cancel()
        raise AssertionError("call_tool never created a pending future")
    fut.set_result(result)
    return await task


async def test_unknown_tool_is_rejected(no_browser):
    with pytest.raises(ValueError, match="Unknown tool"):
        await server.call_tool("not_a_tool", {})


async def test_concurrent_call_is_rejected(no_browser):
    server._session_active = True
    with pytest.raises(RuntimeError, match="already open"):
        await server.call_tool("open_canvas", {})


async def test_open_canvas_returns_image_content(no_browser):
    result = await _call_and_resolve("open_canvas", {}, VALID_PNG_B64)
    assert len(result) == 1
    assert isinstance(result[0], types.ImageContent)
    assert result[0].data == VALID_PNG_B64
    assert result[0].mimeType == "image/png"


async def test_describe_sketch_returns_image_and_prompt(no_browser):
    result = await _call_and_resolve("describe_sketch", {}, VALID_PNG_B64)
    assert len(result) == 2
    assert isinstance(result[0], types.ImageContent)
    assert result[0].data == VALID_PNG_B64
    assert isinstance(result[1], types.TextContent)
    assert "describe" in result[1].text.lower()


async def test_cancelled_canvas_returns_text_content(no_browser):
    result = await _call_and_resolve("open_canvas", {}, None)
    assert len(result) == 1
    assert isinstance(result[0], types.TextContent)
    assert "closed the canvas" in result[0].text


async def test_session_flag_resets_after_call(no_browser):
    await _call_and_resolve("open_canvas", {}, VALID_PNG_B64)
    assert server._session_active is False


async def test_browser_url_carries_token_and_hint(no_browser):
    await _call_and_resolve("open_canvas", {"hint": "draw a cat"}, VALID_PNG_B64)
    assert len(no_browser) == 1
    assert server._SESSION_TOKEN in no_browser[0]
    assert "draw+a+cat" in no_browser[0]


async def test_browser_not_reopened_while_tab_alive(no_browser):
    server._last_heartbeat = time.monotonic()
    await _call_and_resolve("open_canvas", {}, VALID_PNG_B64)
    assert no_browser == []
