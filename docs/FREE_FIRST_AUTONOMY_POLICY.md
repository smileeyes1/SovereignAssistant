# Ω FREE-FIRST AUTONOMY POLICY

Status: **RELEASE INVARIANT**

## Governing rule

Ω APEX must prefer, in order:

1. **Local/offline execution** with zero marginal API cost.
2. **Free/open-source tools and zero-cost/free-tier services** when local execution cannot satisfy the task.
3. **Paid services only as break-glass fallback** when the goal cannot reasonably be completed without them.

Paid capability is never enabled merely because credentials exist. It requires both explicit opt-in and a finite positive call budget. The default budget is zero.

## Consumption rule

Even when a provider is free or paid break-glass is explicitly enabled, the runtime minimizes consumption without sacrificing correctness:

- use the smallest sufficient context;
- bound repeated logs and model output;
- prefer deterministic/local processing before model calls;
- cache/reuse verified results where safe;
- do not repeat a failed call unchanged;
- route local before free remote, and free remote before paid;
- count paid attempts, including failed attempts, against the paid budget;
- fail closed when no admitted provider is available instead of silently spending money.

## Autonomy rule

The user is an end user, not an infrastructure operator. Internal provider selection, failover, budgeting, retries and diagnostics are runtime responsibilities. The system should request user intervention only when a genuinely external credential, legal authorization, or other non-inferable resource is indispensable.

## Release invariants

A change fails release if it causes any of the following:

- paid providers become enabled by default;
- a paid credential alone enables spend;
- an unlimited paid budget becomes possible through the default configuration;
- provider ordering can prefer paid over an admitted local/free provider;
- failed paid attempts are not charged against the configured call budget;
- cost-policy state is not auditable;
- the runtime silently falls back to a paid service after free-provider failure;
- the project becomes dependent on one external AI vendor for its identity or core governance.

## Scope and honesty

"Free" means zero direct service charge under the user's chosen execution path at the time of use. Free-tier terms can change, so the repository does not hard-code a remote vendor as permanently free. Each remote endpoint remains replaceable configuration.

This policy governs the Ω APEX project. It does not claim to modify account-level behavior of unrelated products or services outside the project's control.
