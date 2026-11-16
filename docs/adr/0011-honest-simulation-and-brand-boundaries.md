# 0011. Honest simulation and brand boundaries

- **Status:** Accepted
- **Date:** 2026-11-15

## Context

The bench uses the BMW M4 theme and act digital branding for a demonstration. Overstating what is real (a BMW head unit, real CAN IDs, CarPlay) would mislead reviewers; misuse of trademarks is a legal and credibility risk.

## Decision

- Label simulation everywhere: state reads `BMW M4 · simulated`, UI shows **LIVE SIMULATION**, README states what is and is not connected.
- Keep real integrations clearly separated and named ([ADR 0008](0008-real-aaos-via-adb-as-separate-track.md), [ADR 0009](0009-hardware-adapters-as-api-clients.md)); CarPlay and Android Auto DHU are listed as future hardware-backed tracks, never faked as passes.
- Ship brand assets locally with source and licence in `web/assets/CREDITS.md`; show a trademark disclaimer in the UI.
- Load no remote fonts or scripts.
- These rules are enforced by tests: `test_brand_assets_are_credited`, `test_trademark_disclaimer_is_visible`, `test_no_remote_fonts_or_scripts`.

## Consequences

**Positive**
- Every claim in a demo can be backed by code.
- Works offline and in locked-down networks; no third-party tracking.

**Negative / trade-offs**
- Visual polish is limited to self-hosted assets.
- Branding must be removed or replaced for any commercial use.

## Alternatives considered

- **Generic, unbranded theme** — safer but less relevant to the target audience.
- **CDN-hosted fonts and libraries** — simpler, but adds external requests and breaks offline demos.
