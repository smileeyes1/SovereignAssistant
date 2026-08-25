# HAKIM Ω

**Sovereign, evidence-governed personal and professional AI assistant.**

This repository is the engineering source of truth for HAKIM Ω. The system is built around a small immutable governance core, explicit evidence handling, controlled execution, regression protection, and provider independence.

## Engineering priorities

1. Core integrity over feature growth.
2. Evidence over confidence.
3. Explicit uncertainty over fabricated certainty.
4. Plan before execution.
5. Human approval for consequential actions.
6. Every release must be testable and rollback-ready.
7. External AI providers are replaceable adapters, not the system's identity.

## Current baseline

`hakim-foundation-v1` establishes the first executable governance kernel:

- structured claims with evidence and confidence
- decision gates that distinguish supported, uncertain, and blocked actions
- explicit action risk classes
- approval requirements for consequential actions
- deterministic audit events
- provider-agnostic core interfaces
- automated regression tests through GitHub Actions

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
Tool / Provider Adapters
  ↓
Execution
  ↓
Verification
  ↓
Audit + Memory
```

## Repository rule

The default branch is protected conceptually even before platform-level branch rules are added: changes to the governance kernel must pass automated tests and review before becoming a release candidate.
