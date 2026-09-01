# Ω Forge R2 — Intent-to-App Vertical Slice

R2 proves the complete minimal product loop without requiring OpenAI, Replit, or any other AI vendor.

## Flow

Human intent → internal AppPlan → replaceable CodingWorker → real project files → independent verification → bounded repair loop → verified checkpoint → local preview.

## Acceptance criteria

- A non-empty end-user intent can create a real project artifact.
- The coding worker is a replaceable protocol, not a vendor-specific dependency.
- No result is written as complete until independent verification passes.
- A failed first attempt can enter a bounded repair loop.
- Persistent failure becomes NO-GO and does not write the failed candidate into the project.
- Every successful build creates a content-addressed checkpoint.
- Every successful build produces a working local preview handle.
- Existing R0/R1 governance and workspace tests must continue to pass.

## Provenance boundary

The built-in TemplateCodingWorker is intentionally deterministic and vendor-free. It proves orchestration semantics only. Future model-backed workers (OpenAI, Anthropic, Google, open-weight/local models, or other engines) must implement the same CodingWorker contract and remain replaceable.

## Next safe target after verified R2

R2.1/R3 foundation: persistent SQLite-backed project/checkpoint/execution metadata, explicit task state machine, provider registry, and an HTTP control-plane API suitable for an owned web/mobile client. The first public multi-tenant sandbox remains deferred until stronger isolation is implemented and verified.
