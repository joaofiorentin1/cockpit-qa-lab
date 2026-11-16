"""HTTP contract tests for server.py, against an isolated server on a free port."""

import json
import threading
import time
import unittest
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import server


class ServerApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # No adb / emulator in unit tests: the Android bridge always reports offline.
        cls.adb_patch = mock.patch.object(server.android_bridge, "status", return_value={"online": False, "message": "test"})
        cls.adb_patch.start()
        cls.httpd = server.make_server("127.0.0.1", 0, isolated=True, step_delay=0.05)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.adb_patch.stop()

    def setUp(self):
        self.wait_for_idle_runner()
        self.post("/api/events", {"event": "reset"})

    # ---------- helpers ----------

    def request(self, method, path, body=None, raw=None, headers=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = Request(self.base + path, data=data, method=method, headers=headers or {"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=5) as resp:
                return resp.status, resp.headers, resp.read()
        except HTTPError as err:
            return err.code, err.headers, err.read()

    def get(self, path):
        status, headers, body = self.request("GET", path)
        return status, headers, body

    def get_json(self, path):
        status, _, body = self.get(path)
        return status, json.loads(body)

    def post(self, path, body=None, raw=None):
        status, _, payload = self.request("POST", path, body=body, raw=raw)
        return status, json.loads(payload)

    def wait_for_idle_runner(self, timeout=10):
        deadline = time.time() + timeout
        while self.get_json("/api/report")[1]["status"] == "running":
            if time.time() > deadline:
                raise AssertionError("QA runner did not finish")
            time.sleep(0.02)

    # ---------- read endpoints ----------

    def test_health(self):
        self.assertEqual(self.get_json("/health"), (200, {"status": "ok"}))

    def test_state_shape(self):
        status, state = self.get_json("/api/state")
        self.assertEqual(status, 200)
        for key in ("speed_kmh", "gear", "door_open", "bluetooth", "phone_connected", "projection", "events"):
            self.assertIn(key, state)

    def test_state_is_never_cached(self):
        _, headers, _ = self.get("/api/state")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("application/json", headers["Content-Type"])

    def test_scenario_catalog(self):
        status, scenarios = self.get_json("/api/scenarios")
        self.assertEqual(status, 200)
        ids = [s["id"] for s in scenarios]
        self.assertIn("gear_interlock", ids)
        self.assertTrue(all(s["title"] for s in scenarios))

    def test_report_download_is_an_attachment(self):
        _, headers, body = self.get("/api/report/download")
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertIn("status", json.loads(body))

    def test_android_status_is_reported(self):
        self.assertEqual(self.get_json("/api/android/status")[1]["online"], False)

    # ---------- events ----------

    def test_event_updates_state(self):
        status, state = self.post("/api/events", {"event": "speed_set", "value": 88})
        self.assertEqual(status, 200)
        self.assertEqual((state["speed_kmh"], state["gear"]), (88, "D"))
        self.assertEqual(self.get_json("/api/state")[1]["speed_kmh"], 88)

    def test_gear_selector_over_http(self):
        for gear in ("D", "N", "R", "P"):
            with self.subTest(gear=gear):
                self.assertEqual(self.post("/api/events", {"event": "gear_set", "value": gear})[1]["gear"], gear)

    def test_refused_event_returns_400_with_reason(self):
        self.post("/api/events", {"event": "speed_set", "value": 40})
        status, body = self.post("/api/events", {"event": "gear_set", "value": "P"})
        self.assertEqual(status, 400)
        self.assertIn("Stop the vehicle", body["error"])

    def test_unknown_event_returns_400(self):
        status, body = self.post("/api/events", {"event": "launch_rockets"})
        self.assertEqual(status, 400)
        self.assertIn("Unknown event", body["error"])

    def test_malformed_json_returns_400(self):
        status, body = self.post("/api/events", raw=b"{not json")
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_oversized_body_returns_413(self):
        status, body = self.post("/api/events", raw=b"{" + b" " * 5000 + b"}")
        self.assertEqual(status, 413)

    def test_unknown_post_endpoint_returns_404(self):
        self.assertEqual(self.post("/api/nope", {})[0], 404)

    def test_unknown_static_path_returns_404(self):
        self.assertEqual(self.get("/does-not-exist.html")[0], 404)

    # ---------- scenarios over HTTP ----------

    def test_scenario_runs_and_locks_manual_controls(self):
        status, report = self.post("/api/scenarios", {"scenario": "reconnect"})
        self.assertEqual(status, 200)
        self.assertEqual(report["status"], "running")
        status, body = self.post("/api/events", {"event": "door_toggle"})
        self.assertEqual(status, 409)
        self.assertIn("locked", body["error"])
        self.wait_for_idle_runner()
        self.assertEqual(self.get_json("/api/report")[1]["status"], "passed")

    def test_scenario_with_fault_fails(self):
        self.post("/api/scenarios", {"scenario": "reconnect", "inject_fault": True})
        self.wait_for_idle_runner()
        report = self.get_json("/api/report")[1]
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["summary"], "2/3 checks passed")

    def test_unknown_scenario_returns_400(self):
        status, body = self.post("/api/scenarios", {"scenario": "nope"})
        self.assertEqual(status, 400)
        self.assertIn("Unknown scenario", body["error"])

    # ---------- static UI ----------

    def test_index_and_brand_assets_are_served(self):
        expected = {
            "/": "text/html",
            "/brand.css": "text/css",
            "/app.js": "javascript",
            "/assets/logos/bmw.svg": "image/svg+xml",
            "/assets/logos/act-digital.svg": "image/svg+xml",
            "/assets/fonts/satoshi-500.woff2": "font/woff2",
        }
        for path, content_type in expected.items():
            with self.subTest(path=path):
                status, headers, body = self.get(path)
                self.assertEqual(status, 200)
                self.assertIn(content_type, headers["Content-Type"])
                self.assertTrue(body)


if __name__ == "__main__":
    unittest.main()
