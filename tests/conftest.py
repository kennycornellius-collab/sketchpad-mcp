import pytest

import sketchpad_mcp.server as server


def _reset_state() -> None:
    server._session_active = False
    server._pending_future = None
    server._current_hint = ""
    server._current_call_id = ""
    server._last_heartbeat = 0.0


@pytest.fixture(autouse=True)
def reset_server_state():
    """server.py keeps session state in module globals; isolate every test.

    _runner and _port are deliberately left alone: tests never call the real
    ensure_server_running, so they stay at their import-time defaults.
    """
    _reset_state()
    yield
    _reset_state()
