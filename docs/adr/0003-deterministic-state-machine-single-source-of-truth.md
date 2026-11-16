# 0003. Deterministic state machine as the single source of truth

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

Vehicle and infotainment state (ignition, gear, speed, door, Bluetooth, USB, phone, projection, media) is read and written by several actors: the web HMI, the QA runner, the autopilot demo loop and optional hardware adapters. Tests are only meaningful if the same input always produces the same state.

## Decision

All state lives in one `Cockpit` object (`cockpit.py`), mutated **only** through `dispatch(event, value)`.

- A single `RLock` serialises every transition; readers get a `deepcopy` via `snapshot()`.
- Each accepted transition appends a timestamped entry to an event log (`SYSTEM`, `CAN`, `MEDIA`, `CONNECTIVITY`, `FAULT`, …) with a monotonically increasing `id` that is never reset, so clients can detect new events. The log is capped at 60 entries.
- Derived behaviour is explicit rule code, e.g. losing both Bluetooth and USB triggers `phone_disconnect`; turning ignition off forces `speed 0`, gear `P` and stops media.
- The autopilot runs in a background thread tagged with a *generation* number; `reset()` or toggling autopilot increments the generation, and the loop exits instead of fighting a QA scenario.

## Consequences

**Positive**
- Deterministic: scenarios and unit tests can assert exact state.
- One place to read the vehicle rules; the HMI is a pure view.
- The event log gives a root-cause trail for free.

**Negative / trade-offs**
- In-memory and process-local: state is lost on restart and the design does not scale horizontally (acceptable for a single-user bench).
- A long `if/elif` dispatcher; would be refactored into handlers if the event set grows significantly.

## Alternatives considered

- **State in the browser** — the Python runner could not drive or assert it.
- **Physics-based simulation** — realistic but non-deterministic and far beyond what the QA scenarios need; autopilot uses plateau speeds and leaves easing to the HMI.
