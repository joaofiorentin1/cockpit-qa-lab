# 0002. Zero-dependency Python standard-library backend

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

The bench must start in seconds on any laptop, in CI and on a free Render instance, with no setup beyond Python. The project focuses on QA automation in Python, so the backend should be readable Python, not framework configuration.

## Decision

`server.py` is built only on the standard library: `http.server.ThreadingHTTPServer` with a `SimpleHTTPRequestHandler` subclass that serves `web/` statically and exposes a small JSON API (`/api/state`, `/api/events`, `/api/scenarios`, `/api/report`, `/api/android/*`, `/health`). Configuration is via environment variables (`HOST`, `PORT`, `COCKPIT_ADB`). Third-party packages are confined to optional extras: `requirements-dev.txt` (Selenium) and `requirements-android.txt` (Appium client).

## Consequences

**Positive**
- `python3 server.py` is the whole install; `render.yaml` uses `buildCommand: "true"`.
- No supply-chain surface for the core app; nothing to pin or upgrade.
- Every line of request handling is visible and easy to walk through.

**Negative / trade-offs**
- Hand-written routing, JSON handling and body limits (`Content-Length > 4096 → 413`).
- No schema validation, OpenAPI docs or async I/O; not intended for production load.

## Alternatives considered

- **Flask / FastAPI** — nicer routing and validation, but adds an install step and hides the HTTP contract behind framework magic.
- **Node.js backend** — the simulator and QA runner are the Python showcase; splitting languages adds friction.
