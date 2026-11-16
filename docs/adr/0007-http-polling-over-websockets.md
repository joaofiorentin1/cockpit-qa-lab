# 0007. HTTP polling instead of WebSockets

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

The HMI must reflect state changes made by other actors (QA runner, autopilot, CAN adapter) within a fraction of a second. The backend is standard-library only ([ADR 0002](0002-zero-dependency-python-backend.md)), which has no WebSocket server.

## Decision

The browser polls `GET /api/state` and `GET /api/report` every **450 ms**, the AAOS status every 3 s and the AAOS screenshot every 1.5 s while live mode is active. Responses carry `Cache-Control: no-store`. The client diffs each snapshot against the previous one so animations (gear "pop", new event rows) play only on real changes, using the never-reset event `id` ([ADR 0003](0003-deterministic-state-machine-single-source-of-truth.md)).

## Consequences

**Positive**
- Works with plain `http.server`, behind any proxy, and in Selenium without special handling.
- Stateless server; a reloaded page simply catches up on the next poll.

**Negative / trade-offs**
- Up to ~450 ms latency and constant requests even when idle — fine for one local viewer, wasteful at scale.
- Client must de-duplicate to avoid replaying animations on every poll.

## Alternatives considered

- **WebSockets** — lower latency, but requires a third-party server library or a hand-rolled protocol.
- **Server-Sent Events** — possible with stdlib, but threads blocked per client and more edge cases than the demo justifies. Natural next step if live latency matters.
