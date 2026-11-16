# 0006. Reproducible fault injection as simulator state

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

A test suite that only ever passes proves little. The demo needs to show a failure being caught and diagnosed — reproducibly, on demand, without editing code.

## Decision

Faults are part of the simulator state (`state["fault"]`), toggled by the `fault_toggle` event and exposed in the UI as **Inject a reproducible defect**. The first fault, `resume_failure`, makes `phone_connect` skip media recovery and logs `FAULT: Injected fault: playback failed to recover`.

With the fault on, `reconnect` fails deterministically at step 3 (`2/3 checks passed`) with `expected media_playing: true`, `actual: false`.

## Consequences

**Positive**
- Failure path is demonstrable in seconds and identical on every run.
- Shows the full RCA loop: failed assertion → event timeline → `FAULT` entry → root cause.
- Telemetry highlights the active fault, so the cause is visible, not hidden.

**Negative / trade-offs**
- Fault logic lives in production paths of the simulator (guarded by a flag).
- Only one fault type today; more faults should be modelled as a named set, not more `if`s.

## Alternatives considered

- **Mock/monkeypatch in tests** — invisible in the UI and not usable in a live demo.
- **Random/chaos faults** — realistic but not reproducible, which defeats the demonstration.
