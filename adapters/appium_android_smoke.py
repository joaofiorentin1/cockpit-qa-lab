"""Android Automotive UI smoke test through Appium UiAutomator2.

Runs against the AAOS emulator, captures its real screen and XML hierarchy,
then sends an Android BACK key through Appium. This validates the actual
Android automation path; it does not claim to validate Android Auto projection.
"""

import os
from pathlib import Path

from appium import webdriver
from appium.options.android import UiAutomator2Options


def main():
    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.automation_name = "UiAutomator2"
    options.device_name = "cockpit_aaos"
    options.udid = os.getenv("ANDROID_UDID", "emulator-5556")
    options.no_reset = True
    options.set_capability("appium:skipDeviceInitialization", True)
    driver = webdriver.Remote(os.getenv("APPIUM_URL", "http://127.0.0.1:4723"), options=options)
    try:
        source = driver.page_source
        if "hierarchy" not in source:
            raise AssertionError("Android UI hierarchy was not returned")
        driver.press_keycode(4)
        artifact = Path(__file__).resolve().parents[1] / "artifacts" / "android-automotive.png"
        artifact.parent.mkdir(exist_ok=True)
        driver.save_screenshot(str(artifact))
        print(f"PASS: Android Automotive UI was automated through UiAutomator2. Screenshot: {artifact}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
