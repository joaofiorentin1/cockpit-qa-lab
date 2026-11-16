# 0004. Safety interlocks as refused commands

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

Real vehicles reject unsafe requests: reverse with a door open, Park or Reverse while moving, playback without a phone. A QA bench needs to prove both that valid actions succeed **and** that unsafe actions are refused.

## Decision

Interlocks are enforced inside `Cockpit.dispatch()` by raising `ValueError` with a human-readable reason **before** any state is changed. Examples:

| Request | Refused when | Message |
|---|---|---|
| `gear_set R` / `reverse_toggle` | driver door open | Cannot engage reverse while a door is open |
| `gear_set P` or `R`, `reverse_toggle` | `speed_kmh > 0` | Stop the vehicle before selecting P/R |
| `gear_set D` | reversing (`R`, `speed_kmh > 0`) | Stop the vehicle before changing direction |
| `speed_set` > 15 | gear `R` | Reverse speed is limited to 15 km/h |
| `gear_set` ≠ P, `speed_set` > 0 | ignition off | Ignition must be on |
| `play` | phone not connected | Cannot play projected media without a connected phone |
| `phone_connect` | Bluetooth and USB both off | Enable Bluetooth or connect USB before pairing |

The HTTP layer maps `ValueError` to **400** with `{"error": message}`; the HMI shows it as an error toast. The QA runner has `_step_rejected()`, a step that **passes** when the command is refused.

## Consequences

**Positive**
- Negative testing is first-class: scenarios `door_safety`, `gear_interlock` and `reverse_camera` assert refusals.
- A refused command leaves state untouched, so there is nothing to roll back.
- The same rule protects every client (HMI, runner, CAN adapter).

**Negative / trade-offs**
- `ValueError` is used for both validation errors and interlocks; a dedicated exception type would let clients distinguish them.

## Alternatives considered

- **Enforce in the UI only (disabled buttons)** — the API and adapters could bypass it, and there would be nothing to test.
- **Silently clamp to a safe value** — hides the defect the tester should see.
