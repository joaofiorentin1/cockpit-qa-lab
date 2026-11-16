# 0010. Layered test strategy with isolated servers

- **Status:** Accepted
- **Date:** 2026-11-15

## Context

The project is itself a QA showcase, so its own tests must be fast, reliable and show a sensible test pyramid. Browser tests are slow and flaky if they share state with a developer's running cockpit.

## Decision

Layers, all on `unittest`; every layer except the local AAOS test runs in GitHub Actions on every push and pull request:

| Layer | File | What it proves | Needs |
|---|---|---|---|
| Unit | `test_cockpit.py` | state transitions, interlocks, autopilot | stdlib |
| Runner | `test_qa_runner.py` | scenarios pass/fail, evidence shape | stdlib |
| API contract | `test_server_api.py` | routes, status codes (400/404/409/413), headers | stdlib |
| Adapter | `test_socketcan_bridge.py` | CAN frame decoding, unknown IDs ignored | stdlib |
| Static web contract | `test_web_contract.py` | HTML/JS/CSS agree with backend events and scenarios, assets exist, alt text, reduced-motion, no remote fonts/scripts | stdlib |
| End-to-end | `test_ui_selenium.py` | real Chromium: branding, run scenario, defect report, toasts, telemetry, no JS errors | Selenium |
| Local integration | `test_android_live_selenium.py` | live AAOS screen inside the HMI (not in CI) | Selenium + AAOS emulator |

Rules:
- Each server-level suite starts its **own server on a free port** (`make_server(isolated=True)` or a subprocess with `PORT`), never `:8765`.
- AAOS is disabled in tests (`COCKPIT_ADB=/nonexistent-adb`).
- Browser waits are condition-based (e.g. "all one-shot animations finished"), not `sleep`.
- Screenshots are uploaded as CI artifacts, even on failure.

## Consequences

**Positive**
- Most regressions are caught by stdlib tests in seconds, before the browser starts.
- The static contract layer catches HTML/backend drift without a browser.
- CI evidence (screenshots) matches the product's own evidence philosophy.

**Negative / trade-offs**
- `unittest` is more verbose than pytest.
- E2E still depends on UI timing; a race on the run-banner class (`pop` animation appended after the status) was found and fixed by matching against the full class list.

## Alternatives considered

- **Only Selenium tests** — slow, flaky, and poor at pinpointing which layer broke.
- **pytest** — nicer fixtures, but adds a dependency to the core suite.
