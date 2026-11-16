"""Read and interact with a running Android Automotive emulator through ADB."""

from __future__ import annotations

import os
import re
import shutil
import subprocess


ADB = os.getenv("COCKPIT_ADB") or shutil.which("adb") or "adb"


def _adb(*arguments: str, timeout: float = 4) -> bytes:
    result = subprocess.run([ADB, *arguments], capture_output=True, timeout=timeout, check=True)
    return result.stdout


def status() -> dict:
    try:
        devices = _adb("devices", timeout=3).decode(errors="replace")
        online = [line.split()[0] for line in devices.splitlines()[1:] if line.strip().endswith("device")]
        if not online:
            return {"online": False, "message": "Start the Android Automotive emulator"}
        preferred = os.getenv("COCKPIT_ANDROID_SERIAL", "emulator-5556")
        serial = preferred if preferred in online else online[0]
        device = ["-s", serial]
        booted = _adb(*device, "shell", "getprop", "sys.boot_completed", timeout=3).decode().strip()
        if booted != "1":
            return {"online": False, "message": "Android Automotive is still booting"}
        characteristics = _adb(*device, "shell", "getprop", "ro.build.characteristics", timeout=3).decode().strip()
        if "automotive" not in characteristics:
            return {"online": False, "message": "Connected Android device is not Automotive"}
        size_text = _adb(*device, "shell", "wm", "size", timeout=3).decode(errors="replace")
        match = re.search(r"(\d+)x(\d+)", size_text)
        width, height = (int(match.group(1)), int(match.group(2))) if match else (1024, 768)
        return {"online": True, "serial": serial, "width": width, "height": height, "message": "Android Automotive emulator online"}
    except (OSError, subprocess.SubprocessError):
        return {"online": False, "message": "ADB unavailable or emulator not ready"}


def screenshot() -> bytes:
    device = status()
    if not device["online"]:
        raise RuntimeError(device["message"])
    image = _adb("-s", device["serial"], "exec-out", "screencap", "-p", timeout=25)
    # Multi-display AAOS prints a text warning before the PNG on stdout.
    marker = image.find(b"\x89PNG\r\n\x1a\n")
    if marker < 0:
        raise RuntimeError("Android display is not ready for capture")
    return image[marker:]


def tap(x: int, y: int) -> None:
    device = status()
    if not device["online"]:
        raise RuntimeError(device["message"])
    if not 0 <= x < device["width"] or not 0 <= y < device["height"]:
        raise ValueError("Tap outside Android display")
    _adb("-s", device["serial"], "shell", "input", "tap", str(x), str(y), timeout=5)


def inject_speed(speed_kmh: int) -> str:
    """Set a coherent AAOS driving state through VHAL properties."""
    device = status()
    if not device["online"]:
        raise RuntimeError(device["message"])
    meters_per_second = f"{speed_kmh / 3.6:.3f}"
    base = ("-s", device["serial"], "shell", "cmd", "car_service", "inject-vhal-event")
    if speed_kmh:
        _adb(*base, "0x11400400", "8", timeout=6)  # GEAR_DRIVE
        _adb(*base, "0x11200402", "false", timeout=6)  # parking brake off
    output = _adb(*base, "0x11600207", meters_per_second, timeout=6)
    if not speed_kmh:
        _adb(*base, "0x11400400", "4", timeout=6)  # GEAR_PARK
        _adb(*base, "0x11200402", "true", timeout=6)  # parking brake on
    return output.decode(errors="replace").strip()


def read_speed_mps() -> float:
    device = status()
    if not device["online"]:
        raise RuntimeError(device["message"])
    output = _adb(
        "-s", device["serial"], "shell", "cmd", "car_service",
        "get-property-value", "0x11600207", timeout=6,
    ).decode(errors="replace")
    match = re.search(r"Value:\s*([-+]?\d+(?:\.\d+)?)\s+METER_PER_SEC", output)
    if not match:
        raise RuntimeError(f"Could not parse VHAL speed: {output.strip()}")
    return float(match.group(1))
