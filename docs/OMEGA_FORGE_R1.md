# Ω Forge R1 — Local Sovereign Workspace

R1 establishes the first provider-independent executable workspace slice: owned project storage, command execution, execution logs, local preview, and safe continuation selection.

## Acceptance
- Project files remain under an owned root and path traversal is rejected.
- Commands execute from the project workspace with bounded timeout and captured output.
- Every execution produces a local log record.
- Static project output can be previewed through an owned local preview server.
- The continuation engine may automatically select only ready, safe, reversible next steps.
- Consequential, unsafe, or irreversible steps remain behind the higher governance/approval layer.

## Continuation policy
After a verified stage succeeds, Ω APEX should generate ranked candidate next steps. The continuation engine starts the highest-value candidate automatically only when it is safe, reversible, within granted authority, and its prerequisites are satisfied. Otherwise it records the blocker and waits for the required authority/resource rather than fabricating progress.

## Next target after R1
R2: intent-to-app vertical slice — goal compiler, coding worker interface, real file editing loop, test/run/repair cycle, checkpoints, preview verification, and provider-independent model/tool adapters.
