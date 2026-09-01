# Ω APEX Event-Driven Continuation

The target is not a five-minute polling loop. The target is immediate continuation from concrete events.

## Core flow

Event → deduplicate → generate candidate actions → safety/reversibility/authority gate → rank by value → execute → record outcome → emit/follow next event.

## First-class events

- CI succeeded / failed
- PR merged
- task completed / failed
- checkpoint saved
- capability changed
- explicit owner signal

## Invariants

- Duplicate delivery must not duplicate a successful action.
- Failed execution is not marked processed, so transient failures can be retried.
- Unsafe, irreversible, unauthorized, or unready actions never execute automatically.
- Highest-value eligible action wins; model/provider choice is not exposed to the end user.
- The event core is transport-independent. GitHub webhooks, runtime queues, local processes, MCP/A2A adapters, and future owned infrastructure can feed the same contract.

## Deployment ladder

1. In-process EventRouter for deterministic development and tests.
2. Durable event/outbox store so state survives restarts.
3. GitHub webhook/workflow adapter for CI/PR signals.
4. Runtime/task event adapter.
5. Owned always-on worker consuming the durable queue.
6. Scheduler remains only a watchdog/fallback, not the primary continuation mechanism.

## Security boundary

Event-driven does not mean unrestricted. Consequential or irreversible operations remain behind governance/authority gates. LocalRuntime is still a trusted development runtime and is not a hardened public multi-tenant sandbox.
