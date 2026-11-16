"""Real-browser end-to-end tests. Install requirements-dev.txt before running.

Each run starts its own server.py on a free port, so it never collides with a
cockpit you already have open on :8765.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_server(port: int) -> subprocess.Popen:
    env = {**os.environ, "PORT": str(port), "COCKPIT_ADB": "/nonexistent-adb"}
    proc = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            if urlopen(f"http://127.0.0.1:{port}/health", timeout=0.3).status == 200:
                return proc
        except OSError:
            time.sleep(0.1)
    proc.terminate()
    raise RuntimeError("Local cockpit server did not start")


def make_browser() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    for arg in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1440,1000"):
        options.add_argument(arg)
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    binary = os.getenv("CHROME_BINARY") or (None if shutil.which("google-chrome") else shutil.which("chromium"))
    if binary:
        options.binary_location = binary
    driver = shutil.which("chromedriver")
    return webdriver.Chrome(options=options, service=Service(driver) if driver else None)


class CockpitBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = free_port()
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.server = start_server(cls.port)
        cls.browser = make_browser()
        cls.wait = WebDriverWait(cls.browser, 12)
        ARTIFACTS.mkdir(exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.quit()
        cls.server.terminate()
        cls.server.wait(timeout=5)

    def setUp(self):
        self.api("/api/events", {"event": "reset"})
        self.browser.get(self.base)
        self.wait.until(EC.text_to_be_present_in_element((By.ID, "projection-value"), "Android Auto"))
        self.settle()

    # ---------- helpers ----------

    def settle(self):
        """Wait for one-shot entry animations to finish (looping ones like the live pulse never end)."""
        self.wait.until(lambda b: b.execute_script(
            "return document.getAnimations().every(a => a.effect.getTiming().iterations === Infinity || a.playState !== 'running')"))

    def api(self, path, body):
        req = Request(self.base + path, data=json.dumps(body).encode(), method="POST",
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def css(self, selector):
        return self.browser.find_element(By.CSS_SELECTOR, selector)

    def click(self, selector):
        self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector))).click()

    def open_tab(self, name):
        self.click(f'[data-tab="{name}"]')
        self.wait.until(lambda b: "active" in self.css(f"#{name}-page").get_attribute("class"))
        self.settle()

    def run_scenario(self, scenario, fault=False):
        self.open_tab("validation")
        self.click(f'.scenario:has(input[value="{scenario}"])')
        if fault:
            self.click(".fault-option")
        before = self.report()
        self.click("#run-button")
        # The banner still shows the previous run's result until the next poll, so first wait for
        # the server to finish *this* run, then for the banner to show its status. Match against
        # the whole class list: a "pop" animation class can be appended after the status.
        finished = {"passed", "failed", "error"}
        self.wait.until(lambda b: (r := self.report())["status"] in finished and r != before)
        status = self.report()["status"]
        self.wait.until(lambda b: status in self.css("#run-banner").get_attribute("class").split())
        return status

    def report(self):
        with urlopen(self.base + "/api/report", timeout=5) as resp:
            return json.loads(resp.read())

    # ---------- tests ----------

    def test_branding_is_present(self):
        self.assertIn("BMW M4", self.css(".intro-row h2").text)
        for alt in ("act digital", "BMW", "BMW M"):
            with self.subTest(logo=alt):
                logo = self.css(f'img[alt="{alt}"]')
                self.assertTrue(self.browser.execute_script("return arguments[0].complete && arguments[0].naturalWidth > 0", logo))
        font = self.browser.execute_script("return getComputedStyle(document.body).fontFamily")
        self.assertIn("Satoshi", font)
        self.browser.save_screenshot(str(ARTIFACTS / "cockpit.png"))

    def test_reproducible_failure_is_reported(self):
        self.assertEqual(self.run_scenario("reconnect", fault=True), "failed")
        # Elements fade in, and Selenium's .text is empty while they are invisible, so wait for them.
        for selector, text in (("#run-banner strong", "Defect detected"), ("#test-steps", "FAIL"),
                               ("#result-summary", "2/3 checks passed")):
            with self.subTest(selector=selector):
                self.wait.until(EC.text_to_be_present_in_element((By.CSS_SELECTOR, selector), text))
        self.settle()
        self.browser.save_screenshot(str(ARTIFACTS / "failure-report.png"))

    def test_new_interlock_scenarios_pass_in_the_ui(self):
        for scenario in ("door_safety", "gear_interlock"):
            with self.subTest(scenario=scenario):
                self.assertEqual(self.run_scenario(scenario), "passed")
                self.assertNotIn("FAIL", self.css("#test-steps").text)

    def test_gear_buttons_drive_the_cluster(self):
        for gear in ("D", "N", "R", "P"):
            with self.subTest(gear=gear):
                self.click(f'[data-gear="{gear}"]')
                self.wait.until(EC.text_to_be_present_in_element((By.ID, "cluster-gear"), gear))
                self.assertEqual(self.css("#cluster-gear").get_attribute("data-current-gear"), gear)
                self.assertIn("active", self.css(f'[data-gear="{gear}"]').get_attribute("class"))

    def test_refused_gear_change_shows_an_error_toast(self):
        self.api("/api/events", {"event": "speed_set", "value": 60})
        self.click('[data-gear="P"]')
        self.wait.until(lambda b: "visible" in self.css("#toast").get_attribute("class"))
        self.assertIn("toast-error", self.css("#toast").get_attribute("class"))
        self.assertIn("Stop the vehicle", self.css("#toast").get_attribute("textContent"))

    def test_speed_readout_animates_to_the_target(self):
        self.api("/api/events", {"event": "speed_set", "value": 150})
        seen = set()
        deadline = time.time() + 5
        while time.time() < deadline:
            value = int(self.css("#cluster-speed").text or 0)
            seen.add(value)
            if value == 150:
                break
            time.sleep(0.03)
        self.assertIn(150, seen)
        self.assertTrue(any(0 < v < 150 for v in seen), f"no intermediate frames, saw {sorted(seen)}")

    def test_only_new_events_get_the_entry_animation(self):
        # The list re-renders while polling, so read it atomically in the page.
        classes = "return [...document.querySelectorAll('#event-list .event-item')].map(e => [e.className, e.textContent])"
        self.wait.until(lambda b: b.execute_script(classes))
        self.click('[data-event="door_toggle"]')
        self.wait.until(lambda b: "door" in b.execute_script(classes)[0][1].lower())
        items = self.browser.execute_script(classes)
        self.assertIn("enter", items[0][0])
        self.assertNotIn("enter", items[-1][0])

    def test_telemetry_values_are_colour_coded(self):
        self.api("/api/events", {"event": "door_set", "value": True})
        self.open_tab("telemetry")
        door = self.wait.until(lambda b: next((s for s in b.find_elements(By.CSS_SELECTOR, ".signal")
                                               if s.text.startswith("DRIVER DOOR") and "OPEN" in s.text), None))
        self.assertIn("tone-warn", door.get_attribute("class"))

    def test_tab_is_kept_in_the_url(self):
        self.open_tab("telemetry")
        self.assertTrue(self.browser.current_url.endswith("#telemetry"))
        self.browser.refresh()
        self.wait.until(lambda b: "active" in self.css("#telemetry-page").get_attribute("class"))

    def test_no_javascript_errors(self):
        self.open_tab("validation")
        self.open_tab("cockpit")
        # Refused commands answer 4xx by design; Chrome logs those as "Failed to load resource".
        errors = [e for e in self.browser.get_log("browser")
                  if e["level"] == "SEVERE" and "Failed to load resource" not in e["message"]]
        self.assertEqual(errors, [])


class OfflineDetectionTest(unittest.TestCase):
    def test_ui_reports_when_the_simulator_goes_away(self):
        port = free_port()
        server = start_server(port)
        browser = make_browser()
        try:
            browser.get(f"http://127.0.0.1:{port}")
            wait = WebDriverWait(browser, 12)
            wait.until(EC.text_to_be_present_in_element((By.ID, "lab-status-title"), "ONLINE"))
            server.terminate()
            server.wait(timeout=5)
            wait.until(EC.text_to_be_present_in_element((By.ID, "lab-status-title"), "OFFLINE"))
            self.assertIn("is-offline", browser.find_element(By.TAG_NAME, "body").get_attribute("class"))
        finally:
            browser.quit()
            if server.poll() is None:
                server.terminate()


if __name__ == "__main__":
    unittest.main()
