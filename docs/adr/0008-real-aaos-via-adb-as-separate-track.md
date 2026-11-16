# 0008. Real Android Automotive via ADB, as a separate track

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

Infotainment QA increasingly targets Android Automotive OS (AAOS), with Appium and UI Automator. A purely simulated media screen does not demonstrate that. However, the AAOS emulator is a large download, slow without `/dev/kvm`, and unavailable in CI.

## Decision

Integrate the official AAOS emulator through **ADB only** (`android_bridge.py`), as an optional layer:

- `status()` requires an online device with `sys.boot_completed = 1` and `ro.build.characteristics` containing `automotive`; it prefers `emulator-5556` (`COCKPIT_ANDROID_SERIAL`).
- The HMI shows the live screen via `exec-out screencap -p` and forwards clicks as `input tap`, bounds-checked against `wm size`.
- Cockpit speed is mirrored into VHAL with `cmd car_service inject-vhal-event` (`PERF_VEHICLE_SPEED`, `GEAR_SELECTION`, `PARKING_BRAKE_ON`), keeping gear and parking brake coherent.
- Appium/UiAutomator2 has its own smoke test (`adapters/appium_android_smoke.py`).
- Python QA scenarios assert **simulated** state only; AAOS is never silently mixed into pass/fail.

## Consequences

**Positive**
- Real AAOS UI and VHAL, not a mock, demonstrated inside the cockpit.
- The core bench and CI keep working with no emulator (`COCKPIT_ADB=/nonexistent-adb` in tests).
- Clear boundary between what is simulated and what is real.

**Negative / trade-offs**
- Screenshot polling is low frame-rate and CPU-heavy compared with a video stream.
- ADB shell parsing is brittle across Android versions (e.g. multi-display warning before the PNG is stripped explicitly).
- AAOS behaviour has no automated assertions yet.

## Alternatives considered

- **scrcpy / video streaming** — smoother, but another native dependency and harder to embed.
- **Asserting AAOS state in scenarios** — valuable next step, but would make the core suite depend on a heavy emulator.
