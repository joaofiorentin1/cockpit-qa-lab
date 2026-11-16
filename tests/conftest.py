"""Shared pytest configuration: markers for the slow layers and reusable fixtures.

The existing unittest suites keep working unchanged; pytest only collects them and
adds selection by marker (`pytest -m "not selenium"`).
"""

import json
import os
import threading
from urllib.request import Request, urlopen

import pytest

import server
from cockpit import Cockpit

# Test files that belong to a slow layer, tagged here so the files themselves stay untouched.
FILE_MARKERS = {
    "test_ui_selenium.py": "selenium",
    "test_android_live_selenium.py": "aaos_live",
}


def pytest_collection_modifyitems(config, items):
    skip_live = pytest.mark.skip(
        reason="needs live AAOS emulator; set RUN_AAOS_LIVE=1 to run"
    )
    for item in items:
        marker = FILE_MARKERS.get(item.path.name)
        if marker:
            item.add_marker(getattr(pytest.mark, marker))
        if marker == "aaos_live" and os.getenv("RUN_AAOS_LIVE") != "1":
            item.add_marker(skip_live)


@pytest.fixture
def cockpit():
    """A fresh deterministic cockpit simulator."""
    return Cockpit()


@pytest.fixture(scope="module")
def live_server():
    """An isolated HTTP server on a free port; yields its base URL."""
    httpd = server.make_server("127.0.0.1", 0, isolated=True, step_delay=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def api(live_server):
    """Tiny JSON client against the live_server fixture: api('/api/events', {...})."""

    def call(path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(
            live_server + path,
            data=data,
            method="POST" if body is not None else "GET",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    return call
