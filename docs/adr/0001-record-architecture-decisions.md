# 0001. Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-11-15

## Context

Cockpit QA Lab is shared and demonstrated to other engineers. Reviewers ask *why* something was built a certain way as often as *how*. The reasons behind choices such as "no framework", "polling", or "AAOS is not asserted" are not visible in the code and would otherwise live only in the author's head.

## Decision

Keep Architecture Decision Records in `docs/adr/`, one Markdown file per decision, numbered sequentially, using a lightweight MADR format (Context → Decision → Consequences → Alternatives). Records are immutable once accepted; reversals are new ADRs marked *Supersedes*.

## Consequences

**Positive**
- Design rationale is reviewable in the same pull request as the code.
- The ADR index doubles as a walkthrough for demos and onboarding.

**Negative / trade-offs**
- Small upkeep cost: a significant change needs an ADR alongside the code.

## Alternatives considered

- **Wiki / external docs** — drifts from the code and is not versioned with it.
- **Long README** — mixes usage with rationale; hard to see what changed and when.
