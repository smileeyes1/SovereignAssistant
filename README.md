# HAKIM Ω

**Sovereign, evidence-governed personal and professional AI assistant.**

This repository is the engineering source of truth for HAKIM Ω. The system is built around a small immutable governance core, explicit evidence handling, controlled execution, regression protection, provider independence, and a free-first resource policy.

## Engineering priorities

1. Core integrity over feature growth.
2. Evidence over confidence.
3. Explicit uncertainty over fabricated certainty.
4. Plan before execution.
5. Human approval for consequential actions.
6. Every release must be testable and rollback-ready.
7. External AI providers are replaceable adapters, not the system's identity.
8. **Local/offline and zero-cost capability before paid services; paid access is break-glass only with an explicit finite budget.**
9. Minimize provider calls, context, retries and output without sacrificing correctness.

The canonical cost/resource invariant is documented in [`docs/FREE_FIRST_AUTONOMY_POLICY.md`](docs/FREE_FIRST_AUTONOMY_POLICY.md).

## Current baseline

`hakim-foundation-v1` establishes the first executable governance kernel:

- structured claims with evidence and confidence
- decision gates that distinguish supported, uncertain, and blocked actions
- explicit action risk classes
- approval requirements for consequential actions
- deterministic audit events
- provider-agnostic core interfaces
- automated regression tests through GitHub Actions
- free-first provider routing with paid break-glass disabled by default

This is intentionally a foundation, not a finished assistant. Features are admitted only after the governance core remains intact.

## Target architecture

```text
User
  ↓
Intent / Context
  ↓
Reasoning Orchestrator
  ↓
Evidence + Source Guard
  ↓
Decision Gate
  ↓
Plan
  ↓
Approval Gate (when required)
  ↓
Free-First Resource / Provider Router
  ↓
Tool / Provider Adapters
  ↓
Execution
  ↓
Verification
  ↓
Audit + Memory
```

## Repository rule

The default branch is protected conceptually even before platform-level branch rules are added: changes to the governance kernel must pass automated tests and review before becoming a release candidate. Cost-policy regressions are release-blocking: paid providers must remain disabled by default and may never outrank an admitted local/free provider.
