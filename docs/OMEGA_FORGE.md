# Ω FORGE

## Sovereign Intent-to-Software Platform

Ω Forge is the software creation and execution layer of Ω APEX SOVEREIGN. Its product goal is not to copy Replit's interface. Its goal is to let an end user express an outcome such as “build me this app” while the platform owns specification, workspace creation, coding, testing, preview, repair, versioning, deployment, monitoring, and future upgrades.

## Constitutional requirement

The platform must survive replacement of any cloud, model, IDE, runtime, database, or deployment provider. External systems are adapters. Workspace state, user relationship, orchestration, policies, evaluations, memory, and project history remain owned by Ω APEX.

## End-user experience

The normal user sees four concepts only:

1. Intent — what they want built or changed.
2. Progress — what is happening at a useful human level.
3. Preview — the running result.
4. Result — the verified artifact/application and simple controls to continue.

Model selection, runtime selection, container images, ports, Git operations, build commands, agent topology, retries, deployments, secrets, and infrastructure are hidden unless an owner explicitly opens advanced controls.

## Architecture

User Intent
→ Ω APEX Intent Engine
→ Software Goal Compiler
→ Ω Forge Meta-Controller
→ Project/Workspace Control Plane
→ Coding Agent Fabric
→ Tool Bus
→ Sandbox Runtime
→ Build/Test Engine
→ Preview Gateway
→ Verification/Red Team
→ Version/Checkpoint Store
→ Deployment Router
→ Runtime Monitoring
→ Memory/Learning

Cross-cutting: governance, least privilege, secret isolation, audit, quotas, observability, rollback, cost control, and provider independence.

## Owned control plane

Ω Forge owns the canonical records for projects, workspaces, executions, tasks, artifacts, previews, deployments, checkpoints, evaluations, and permissions. Runtime backends implement a small adapter contract and never become the source of truth.

## Replaceable runtime ladder

Phase 1: local/Docker-compatible runtime for development and validation.
Phase 2: gVisor-isolated containers for stronger multi-tenant isolation.
Phase 3: Firecracker microVM runtime for high-risk or public multi-tenant workloads.
Phase 4: Kubernetes or another scheduler only when scale justifies its operational cost.

The Meta-Controller selects the simplest adequate runtime by risk, workload, cost, latency, and availability.

## Development environment

Use an open browser IDE layer rather than developing a proprietary editor from scratch. OpenVSCode Server or Eclipse Theia can be branded and integrated behind Ω Forge's own authentication, workspace routing, preview proxy, agent controls, and project state. The editor is replaceable; Ω Forge is the product.

## Portable environments

Adopt the open Development Containers specification as the preferred project environment contract when useful. A project may define language/runtime/tooling once, and Ω Forge can realize it on any compatible backend.

## Coding intelligence

Coding agents are model-agnostic workers. The system may integrate our own agent runtime and selectively reuse open components such as OpenHands SDK where they save engineering effort. Agent choice is internal. The end user never has to choose Codex, Gemini, Claude, or another worker.

## Core product capabilities

- Create/import a project from plain-language intent, archive, or Git repository.
- Ephemeral and persistent workspaces.
- Browser IDE and terminal for optional advanced access.
- AI agent that edits real files, executes commands, and tests results.
- Git-compatible version history with automatic checkpoints.
- Live preview with port discovery and secure routing.
- Build logs translated to useful end-user status.
- Autonomous diagnosis, retry, repair, and rollback.
- Secret vault; secrets never appear in ordinary model context or client code.
- File/object artifact store.
- Build cache and reusable environment images.
- Deployment adapters rather than one compulsory host.
- Scheduled/background engineering tasks.
- Multi-agent parallel work only when dependency analysis makes it beneficial.
- Security/evidence/quality gates before high-impact deployment.
- Owner-level capability registry and health matrix.

## Provider classes

Every external dependency belongs to a replaceable provider class:

- ModelProvider
- RuntimeBackend
- SourceControlProvider
- ObjectStore
- DatabaseProvider
- SearchProvider
- DeploymentProvider
- DNSProvider
- IdentityProvider
- NotificationProvider

At least one portable/self-hostable path is the strategic target for every critical class.

## Failure behavior

No false success is permitted. If a runtime, model, deployment host, or integration fails, Ω Forge marks the capability degraded, attempts an allowed fallback, restores the last verified checkpoint if necessary, and exposes only the minimum actionable blocker to the end user.

## Self-improvement

Production does not rewrite itself directly. Runtime metrics, failed builds, repair outcomes, model performance, user interventions, cost, and latency feed the Ω APEX Improvement Lab. Candidate routing/workflow/agent/runtime changes are benchmarked against the current champion, adversarially tested, canaried, and rolled back automatically on regression.

## Release ladder

### R0 — Control-plane kernel
Portable workspace specification, lifecycle, backend routing, fail-closed behavior, tests.

### R1 — Local sovereign workspace
Real runtime adapter, persistence, project storage, command execution, logs, preview endpoint, owner-only configuration.

### R2 — Intent-to-app vertical slice
Plain-language project creation, coding agent, file editing, test/run/repair loop, preview, checkpoint, verified completion.

### R3 — Replit-class core
Browser IDE, Git, secrets, databases, background jobs, deployment routing, reusable environments, collaboration foundations.

### R4 — APEX advantage
Multi-model router, autonomous parallel engineering, deep verification, proactive maintenance, self-improvement lab, mobile-first zero-config experience.

### R5 — Sovereign scale
Multi-tenant microVM isolation, scheduling, distributed caching/builds, regional control plane/data plane separation, high availability, metering, policy and organizational tenancy.

## Non-goals

- Rebuilding VS Code from zero.
- Training a frontier foundation model before the platform creates value.
- Kubernetes before it is operationally justified.
- Exposing infrastructure choices to ordinary users.
- Claiming parity or superiority without benchmarks.

## Definition of success

Ω Forge succeeds when a non-developer can say “build/change this,” receive a running verified result, and continue using it without knowing which editor, model, sandbox, build system, Git operation, or deployment provider performed the work — while the owner can replace those components without losing the platform, projects, memory, or user relationship.
