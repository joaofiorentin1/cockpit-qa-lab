# 0012. Use pytest as the test runner and deploy through CI/CD with a Deploy Hook

- **Status:** Accepted
- **Date:** 2026-11-16

## Context

[0010](0010-layered-test-strategy.md) kept the suite on `unittest` to avoid a dependency in the core tests. Two things changed. The slow layers (Selenium, Appium, live AAOS) need selection by marker and shared fixtures, and Render redeployed on every push to `main`, even when tests were failing.

## Decision

- **pytest is the runner.** The app itself still has no dependencies (see [0002](0002-zero-dependency-python-backend.md)); pytest is a development dependency in `requirements-dev.txt`. Existing `unittest` suites run unchanged. `tests/conftest.py` adds the markers `selenium`, `appium` and `aaos_live` and the fixtures `cockpit`, `live_server` and `api`. New tests use native pytest style (functions, `parametrize`, `pytest.raises`).
- **CI** (`.github/workflows/ci.yml`) runs the fast suite on Python 3.11 and 3.12 with coverage, then the Selenium job. Appium and live AAOS tests are skipped without a server or emulator.
- **CD** (`.github/workflows/cd.yml`) runs only after CI succeeds on `main`. Render auto-deploy is off (`autoDeploy: false`), so a Render Deploy Hook, stored as the secret `RENDER_DEPLOY_HOOK_URL`, is the only release path. A smoke test then checks `/health`, `/api/scenarios` and `/api/state` on the public URL.

## Consequences

**Positive**
- A failing test can no longer reach production.
- Markers keep the default run fast and let each layer run on its own.
- Parametrized tests are shorter than the `unittest` equivalents.

**Negative / trade-offs**
- Development now needs `pip install -r requirements-dev.txt`.
- The smoke test only proves the service answers. It cannot tell the new version from the old one while Render is still building; exposing the commit SHA in `/health` would close that gap.
- The scenario count is checked in `cd.yml`, so adding a scenario means updating that number.

## Alternatives considered

- **Stay on unittest** — no dependency, but no markers or fixtures and more boilerplate.
- **Render "After CI Checks Pass"** — simpler, but configured in the dashboard instead of the repository.
- **Keep auto-deploy on every push** — fast, but untested code reached production.
