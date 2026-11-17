# 0013. Seeded monkey testing for safety invariants

- **Status:** Accepted
- **Date:** 2026-11-16

## Context

Unit tests check each interlock with one hand-picked example. Real defects tend to hide in
*sequences* nobody scripted: ignition off while reversing, a door opened mid-manoeuvre,
Bluetooth toggled during a reconnection. Automotive teams use random "monkey" testing for
exactly this reason.

## Decision

`tests/test_monkey.py` sends 20,000 random commands (8 seeds × 2,500), including invalid
values on purpose, and after **every** command asserts a list of invariants:

- gear R ⇒ speed ≤ 15 km/h; gear P ⇒ speed 0; ignition off ⇒ stopped in P
- reverse only entered at standstill with the door closed; no R ↔ D change while moving
- media playing ⇒ phone connected ⇒ Bluetooth or USB available
- call in progress ⇒ media paused and phone connected
- rear camera ⇔ gear R; curve warning ⇔ speed above the curve's advisory speed
- a refused command leaves the state unchanged (ADR 0004)

Seeds are fixed, so a failure prints the seed, the step and the last commands, and replays
identically.

## Consequences

**Positive**
- Finds ordering bugs that example-based tests miss, at a cost of a few seconds in CI.
  First catch: once phone-call events were added, the monkey found that a `phone_connect`
  during an active call resumed media over the call (seed 0, step 971). Fixed in
  `cockpit.py` and pinned by `test_reconnecting_during_a_call_keeps_media_paused`.
- Invariants double as an executable specification of the safety rules.
- The test asserts it exercised both accepted and refused paths (>1,000 each), so it cannot pass vacuously.

**Negative / trade-offs**
- Random sequences are not a coverage guarantee; a rare state may still need a dedicated test.
- Background threads (autopilot) are excluded to keep runs deterministic.

## Alternatives considered

- **Property-based testing with Hypothesis** — better shrinking of failing cases, but adds a dependency (see ADR 0002).
- **Only example-based tests** — cheaper, but blind to unexpected sequences.
