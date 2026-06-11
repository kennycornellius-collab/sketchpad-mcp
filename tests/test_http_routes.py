import asyncio
import base64

import pytest

import canvas_mcp.server as server

TOKEN_HEADER = {"X-Canvas-Token": server._SESSION_TOKEN}
WRONG_TOKEN_HEADER = {"X-Canvas-Token": "0" * 32}
VALID_PNG_B64 = base64.b64encode(server._PNG_MAGIC + b"\x00" * 16).decode()


@pytest.fixture
async def client(aiohttp_client):
    return await aiohttp_client(server._build_app())


@pytest.fixture
async def pending_future():
    """Install a fresh pending future as the active canvas session."""
    fut = asyncio.get_running_loop().create_future()
    server._pending_future = fut
    return fut


# ---------------------------------------------------------------------------
# Static routes — no token required
# ---------------------------------------------------------------------------

async def test_index_serves_html_without_token(client):
    resp = await client.get("/")
    assert resp.status == 200
    assert "text/html" in resp.headers["Content-Type"]


async def test_css_served_without_token(client):
    resp = await client.get("/canvas.css")
    assert resp.status == 200
    assert "text/css" in resp.headers["Content-Type"]


# ---------------------------------------------------------------------------
# Token enforcement on stateful routes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method,route", [
    ("get", "/state"),
    ("post", "/submit"),
    ("post", "/cancel"),
])
async def test_missing_token_is_403(client, pending_future, method, route):
    resp = await getattr(client, method)(route)
    assert resp.status == 403
    assert not pending_future.done()


@pytest.mark.parametrize("method,route", [
    ("get", "/state"),
    ("post", "/submit"),
    ("post", "/cancel"),
])
async def test_wrong_token_is_403(client, pending_future, method, route):
    resp = await getattr(client, method)(route, headers=WRONG_TOKEN_HEADER)
    assert resp.status == 403
    assert not pending_future.done()


async def test_token_accepted_as_query_param(client, pending_future):
    # The /cancel beacon cannot set headers, so the token rides the query string.
    resp = await client.post(f"/cancel?token={server._SESSION_TOKEN}")
    assert resp.status == 200
    assert pending_future.result() is None


# ---------------------------------------------------------------------------
# /submit
# ---------------------------------------------------------------------------

async def test_submit_without_session_is_409(client):
    resp = await client.post("/submit", headers=TOKEN_HEADER, json={"image": VALID_PNG_B64})
    assert resp.status == 409


async def test_submit_after_resolution_is_409(client, pending_future):
    pending_future.set_result(VALID_PNG_B64)
    resp = await client.post("/submit", headers=TOKEN_HEADER, json={"image": VALID_PNG_B64})
    assert resp.status == 409


@pytest.mark.parametrize("body", [
    b"not json at all",
    b"{truncated",
])
async def test_submit_invalid_json_is_400(client, pending_future, body):
    resp = await client.post("/submit", headers=TOKEN_HEADER, data=body)
    assert resp.status == 400
    assert not pending_future.done()


@pytest.mark.parametrize("payload", [
    [1, 2, 3],
    "just a string",
    42,
])
async def test_submit_non_object_json_is_400(client, pending_future, payload):
    resp = await client.post("/submit", headers=TOKEN_HEADER, json=payload)
    assert resp.status == 400
    assert not pending_future.done()


@pytest.mark.parametrize("payload", [
    {},
    {"image": ""},
    {"image": 12345},
    {"image": None},
])
async def test_submit_missing_or_non_string_image_is_400(client, pending_future, payload):
    resp = await client.post("/submit", headers=TOKEN_HEADER, json=payload)
    assert resp.status == 400
    assert not pending_future.done()


async def test_submit_invalid_base64_is_400(client, pending_future):
    resp = await client.post("/submit", headers=TOKEN_HEADER, json={"image": "!!!not-base64!!!"})
    assert resp.status == 400
    assert not pending_future.done()


async def test_submit_base64_but_not_png_is_400(client, pending_future):
    not_png = base64.b64encode(b"GIF89a definitely not a png").decode()
    resp = await client.post("/submit", headers=TOKEN_HEADER, json={"image": not_png})
    assert resp.status == 400
    assert not pending_future.done()


async def test_submit_valid_png_resolves_future(client, pending_future):
    resp = await client.post("/submit", headers=TOKEN_HEADER, json={"image": VALID_PNG_B64})
    assert resp.status == 200
    assert pending_future.result() == VALID_PNG_B64


# ---------------------------------------------------------------------------
# /cancel
# ---------------------------------------------------------------------------

async def test_cancel_resolves_future_with_none(client, pending_future):
    resp = await client.post("/cancel", headers=TOKEN_HEADER)
    assert resp.status == 200
    assert pending_future.result() is None


async def test_cancel_without_session_is_noop_200(client):
    resp = await client.post("/cancel", headers=TOKEN_HEADER)
    assert resp.status == 200


# ---------------------------------------------------------------------------
# /state
# ---------------------------------------------------------------------------

async def test_state_returns_hint_and_call_id(client):
    server._current_hint = "draw a cat"
    server._current_call_id = "abc123"
    resp = await client.get("/state", headers=TOKEN_HEADER)
    assert resp.status == 200
    assert await resp.json() == {"hint": "draw a cat", "call_id": "abc123"}


async def test_state_refreshes_heartbeat(client):
    assert server._last_heartbeat == 0.0
    resp = await client.get("/state", headers=TOKEN_HEADER)
    assert resp.status == 200
    assert server._last_heartbeat > 0.0
