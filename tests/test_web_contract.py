"""Static contract tests for web/: the page, its scripts, styles and the backend agree.

Runs without a browser, so it is fast enough for every commit.
"""

import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

from cockpit import Cockpit
from qa import SCENARIOS

WEB = Path(__file__).resolve().parents[1] / "web"


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.refs, self.events, self.gears, self.scenarios, self.imgs = set(), [], [], [], [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        for key in ("href", "src"):
            if a.get(key):
                self.refs.append(a[key])
        if "data-event" in a:
            self.events.append(a["data-event"])
        if "data-gear" in a:
            self.gears.append(a["data-gear"])
        if tag == "input" and a.get("name") == "scenario":
            self.scenarios.append(a["value"])
        if tag == "img":
            self.imgs.append(a)


class WebContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (WEB / "index.html").read_text(encoding="utf-8")
        cls.js = (WEB / "app.js").read_text(encoding="utf-8")
        cls.page = _Collector()
        cls.page.feed(cls.html)

    def local(self, ref):
        return WEB / ref.split("?")[0].split("#")[0].lstrip("/")

    def test_every_local_reference_exists(self):
        for ref in self.page.refs:
            if ref.startswith(("http", "data:", "#")) or ref.startswith("/api/"):
                continue
            with self.subTest(ref=ref):
                target = self.local(ref)
                if ref.endswith("/"):
                    target = target / "index.html"  # e.g. /unity/ -> the WebGL build
                self.assertTrue(target.is_file(), f"missing {ref}")

    def test_every_css_url_exists(self):
        for css in WEB.glob("*.css"):
            for url in re.findall(r"url\(['\"]?([^)'\"]+)", css.read_text(encoding="utf-8")):
                if url.startswith(("http", "data:")):
                    continue
                with self.subTest(css=css.name, url=url):
                    self.assertTrue(self.local(url).is_file(), f"{css.name} references missing {url}")

    def test_no_remote_fonts_or_scripts(self):
        # The demo must run offline (e.g. in a meeting room without Wi-Fi).
        for name in ("index.html", "styles.css", "brand.css", "motion.css", "android.css"):
            text = (WEB / name).read_text(encoding="utf-8")
            with self.subTest(file=name):
                self.assertNotRegex(text, r"https?://(fonts\.googleapis|fonts\.gstatic|cdn)")

    def test_buttons_only_send_events_the_simulator_knows(self):
        events = set(self.page.events) | {"pause", "phone_connect", "gear_set", "speed_set"}  # set dynamically by app.js
        for event in sorted(events):
            with self.subTest(event=event):
                try:
                    Cockpit().dispatch(event, "D" if event == "gear_set" else 0 if event == "speed_set" else None)
                except ValueError as exc:
                    self.assertNotIn("Unknown event", str(exc))

    def test_gear_buttons_cover_prnd(self):
        self.assertEqual(self.page.gears, ["P", "R", "N", "D"])

    def test_data_gear_is_reserved_for_selector_buttons(self):
        # app.js binds clicks and the "active" state to every [data-gear]; tagging any
        # other element with it turns that element into a phantom gear button.
        self.assertEqual(len(re.findall(r"<button data-gear=", self.html)), len(self.page.gears))
        assignment = re.search(r"dataset\.gear\s*=(?!=)", self.js)
        self.assertIsNone(assignment, "app.js must not tag non-button elements with data-gear")

    def test_scenario_cards_match_the_backend_catalog(self):
        self.assertEqual(self.page.scenarios, list(SCENARIOS))

    def test_every_id_used_by_app_js_exists(self):
        used = set(re.findall(r"\$\('#([\w-]+)'\)", self.js))
        used |= {"bt-status", "usb-status", "phone-status"}  # built as `#${id}` from a list in renderState
        for element_id in sorted(used):
            with self.subTest(id=element_id):
                self.assertIn(element_id, self.page.ids)

    def test_images_have_alt_text(self):
        for img in self.page.imgs:
            with self.subTest(src=img.get("src")):
                self.assertIn("alt", img)

    def test_brand_assets_are_credited(self):
        credits = (WEB / "assets" / "CREDITS.md").read_text(encoding="utf-8")
        for asset in list((WEB / "assets" / "logos").iterdir()) + [WEB / "assets" / "fonts"]:
            with self.subTest(asset=asset.name):
                self.assertIn(asset.name if asset.is_file() else "satoshi", credits)

    def test_trademark_disclaimer_is_visible(self):
        self.assertIn("marcas de seus respectivos titulares", self.html)

    def test_motion_respects_reduced_motion(self):
        self.assertIn("prefers-reduced-motion", (WEB / "motion.css").read_text(encoding="utf-8"))
        self.assertIn("prefers-reduced-motion", self.js)


if __name__ == "__main__":
    unittest.main()
