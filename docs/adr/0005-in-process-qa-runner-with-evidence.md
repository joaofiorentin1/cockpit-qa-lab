# 0005. In-process QA runner with expected-vs-actual evidence

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

The demo must show automated validation that a viewer can *watch* and a reviewer can *audit*: what was done, what was expected, what actually happened.

## Decision

`QARunner` (`qa.py`) runs inside the server process against the **same** `Cockpit` instance the HMI displays.

- Scenarios are a fixed catalogue (`SCENARIOS`: `reconnect`, `usb_fallback`, `reverse_camera`, `door_safety`, `gear_interlock`) validated by the API and mirrored by the web UI (checked by a contract test).
- Each step dispatches one event and records `{label, event, expected, actual, status, timestamp}`; only the keys listed in `expected` are compared.
- A run starts from `reset()`, executes in a background thread, and ends with `passed`/`failed`/`error`, a summary (`3/3 checks passed`) and the `final_state`.
- `step_delay` (0.75 s default, 0 in tests) paces the run so the HMI visibly changes.
- While a run is `running`, `POST /api/events` returns **409** so manual input cannot corrupt the evidence; a second run is refused.
- The report is downloadable as JSON (`/api/report/download`).

## Consequences

**Positive**
- Evidence is structured and machine-readable, ready for CI artifacts or a test-management tool.
- The viewer sees the cockpit react in real time while assertions run.
- Fast, deterministic unit tests with `step_delay=0`.

**Negative / trade-offs**
- Scenarios are Python code, not data; adding one means editing `qa.py` and the HTML card.
- Only one run at a time per server instance.

## Alternatives considered

- **pytest/Selenium as the only runner** — great for CI but invisible during a live demo and assertions would target the DOM, not system state.
- **Data-driven YAML scenarios** — more flexible, but premature for five scenarios.
