"""Zero-dependency local server for the simulated cockpit and QA runner."""

from __future__ import annotations

import json
import os
import subprocess
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import android_bridge
from cockpit import Cockpit
from qa import SCENARIOS, QARunner

ROOT = Path(__file__).resolve().parent
COCKPIT = Cockpit()
QA = QARunner(COCKPIT)


class Handler(SimpleHTTPRequestHandler):
    # Swappable so tests can run an isolated simulator per server (see make_server).
    cockpit = COCKPIT
    qa = QA
    quiet = False

    def log_message(self, format, *args):
        if not self.quiet:
            super().log_message(format, *args)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "web"), **kwargs)

    def end_headers(self):
        # Static files (incl. the Unity WebGL build) only carry Last-Modified, which lets
        # browsers cache them heuristically and mix an old framework with a new wasm after a
        # deploy. "no-cache" keeps caching but forces a cheap revalidation (304) every load.
        if not any(line.lower().startswith(b"cache-control:") for line in getattr(self, "_headers_buffer", [])):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def _json(self, payload, status=200, download=False):
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if download:
            self.send_header("Content-Disposition", 'attachment; filename="cockpit-qa-report.json"')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/state":
            return self._json(self.cockpit.snapshot())
        if path == "/api/report":
            return self._json(self.qa.report())
        if path == "/api/report/download":
            return self._json(self.qa.report(), download=True)
        if path == "/api/android/status":
            return self._json(android_bridge.status())
        if path == "/api/android/screen":
            try:
                body = android_bridge.screenshot()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
                self._json({"error": str(exc)}, 503)
            return
        if path == "/api/scenarios":
            return self._json([{"id": key, "title": title} for key, title in SCENARIOS.items()])
        if path == "/health":
            return self._json({"status": "ok"})
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in {"/api/events", "/api/scenarios", "/api/android/tap"}:
            return self._json({"error": "Unknown endpoint"}, 404)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 4096:
                return self._json({"error": "Request too large"}, 413)
            body = json.loads(self.rfile.read(length) or b"{}")
            if path == "/api/android/tap":
                android_bridge.tap(int(body.get("x")), int(body.get("y")))
                return self._json({"ok": True})
            if path == "/api/events":
                if self.qa.report()["status"] == "running":
                    return self._json({"error": "Controls are locked during a test"}, 409)
                event = body.get("event")
                state = self.cockpit.dispatch(event, body.get("value"))
                if event == "speed_set" and android_bridge.status()["online"]:
                    try:
                        state["aaos_vhal"] = android_bridge.inject_speed(state["speed_kmh"])
                    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
                        state["aaos_vhal_error"] = str(exc)
                return self._json(state)
            return self._json(self.qa.start(body.get("scenario"), bool(body.get("inject_fault", False))))
        except (ValueError, TypeError, json.JSONDecodeError, RuntimeError, subprocess.SubprocessError) as exc:
            return self._json({"error": str(exc)}, 400)


def make_server(host: str = "127.0.0.1", port: int = 0, isolated: bool = False,
                step_delay: float = 0.75) -> ThreadingHTTPServer:
    """Build the HTTP server. isolated=True gives it a fresh Cockpit/QARunner (tests)."""
    handler = Handler
    if isolated:
        cockpit = Cockpit()
        handler = type("IsolatedHandler", (Handler,), {"cockpit": cockpit, "qa": QARunner(cockpit, step_delay), "quiet": True})
    return ThreadingHTTPServer((host, port), handler)


def main():
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8765"))
    server = make_server(host, port)
    print(f"Cockpit QA Lab: http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
