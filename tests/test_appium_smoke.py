"""Appium UiAutomator2 smoke test as a pytest test.

Skipped automatically when the Appium client, the Appium server or the AAOS emulator is missing,
so it never breaks the default run. Run it with: pytest -m appium
"""

import os
from pathlib import Path
from urllib.request import urlopen

import pytest

pytestmark = pytest.mark.appium

APPIUM_URL = os.getenv("APPIUM_URL", "http://127.0.0.1:4723")
ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts"


@pytest.fixture
def android_driver():
    pytest.importorskip(
        "appium", reason="Appium-Python-Client not installed (requirements-android.txt)"
    )
    from appium import webdriver
    from appium.options.android import UiAutomator2Options

    try:
        urlopen(f"{APPIUM_URL}/status", timeout=2)
    except OSError:
        pytest.skip(f"Appium server not reachable at {APPIUM_URL}")

    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.automation_name = "UiAutomator2"
    options.device_name = "cockpit_aaos"
    options.udid = os.getenv("ANDROID_UDID", "emulator-5556")
    options.no_reset = True
    options.set_capability("appium:skipDeviceInitialization", True)
    try:
        driver = webdriver.Remote(APPIUM_URL, options=options)
    except Exception as exc:  # no device/emulator attached
        pytest.skip(f"Could not start an Appium session: {exc}")
    yield driver
    driver.quit()


def test_android_ui_hierarchy_is_automatable(android_driver):
    assert "hierarchy" in android_driver.page_source
    android_driver.press_keycode(4)  # BACK
    ARTIFACTS.mkdir(exist_ok=True)
    assert android_driver.save_screenshot(str(ARTIFACTS / "android-automotive.png"))
