"""Local integration test: requires running cockpit server and AAOS emulator."""

import unittest
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parents[1]


class AndroidLiveBrowserTest(unittest.TestCase):
    def test_actual_aaos_screen_embedded_in_multimedia(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1440,1000")
        browser = webdriver.Chrome(options=options)
        try:
            browser.get("http://127.0.0.1:8765")
            wait = WebDriverWait(browser, 15)
            switch = wait.until(EC.element_to_be_clickable((By.ID, "android-mode")))
            self.assertIn("AAOS READY", switch.text)
            switch.click()
            wait.until(lambda driver: driver.find_element(By.ID, "android-screen").get_attribute("naturalWidth") != "0")
            self.assertTrue(browser.find_element(By.CSS_SELECTOR, ".infotainment-panel").get_attribute("class").find("aaos-active") >= 0)
            artifacts = ROOT / "artifacts"
            artifacts.mkdir(exist_ok=True)
            browser.save_screenshot(str(artifacts / "cockpit-aaos-live.png"))
        finally:
            browser.quit()


if __name__ == "__main__":
    unittest.main()
