# 0009. Hardware adapters are thin API clients with a demo CAN contract

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

Automotive QA involves CAN and embedded signals. The bench should accept real bus input without coupling the simulator to Linux-only sockets or to a proprietary signal database.

## Decision

Hardware integrations live in `adapters/` as **separate processes** that translate external input into the same `POST /api/events` used by the HMI.

`socketcan_bridge.py` reads a SocketCAN interface (default `vcan0`) and decodes a **project-defined demo contract**:

| CAN ID | Payload | Event |
|---|---|---|
| `0x100` | uint16 LE, 0.1 km/h | `speed_set` |
| `0x101` | uint8, 0 = P, 1 = R | `gear_set` |
| `0x102` | uint8, 0 = closed, 1 = open | `door_set` |

Unknown IDs and out-of-range values are ignored. This is explicitly **not** a BMW DBC.

## Consequences

**Positive**
- Adapters inherit every interlock and log entry for free ([ADR 0003](0003-deterministic-state-machine-single-source-of-truth.md), [ADR 0004](0004-safety-interlocks-as-refused-commands.md)).
- The server stays cross-platform; SocketCAN is only needed where the adapter runs.
- Decoding is a pure function, unit-tested without a CAN interface.

**Negative / trade-offs**
- Extra HTTP hop per frame; not suitable for high-rate bus traffic.
- Signal set is minimal and hand-coded rather than generated from a DBC.

## Alternatives considered

- **Reading CAN inside the server** — Linux-only and couples transport to domain logic.
- **python-can + DBC (cantools)** — the right direction for real signals; deferred to keep the core dependency-free.
