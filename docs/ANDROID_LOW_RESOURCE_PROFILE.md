# HAKIM Ω — Android Low-Resource Profile

This profile is for Android phones where persistent local inference or long-lived Termux background work is not reliable enough to be a runtime root.

## Field evidence that caused this profile

On the qualified TECNO LJ6 / Android 15 field device:

- Human permission gate: PASS for approve, reject, expiry, and wrong-token rejection.
- Screen-off background survival: FAIL. The measured five-minute test produced 4 heartbeats with a maximum gap of about 356 seconds.
- Qwen3-1.7B-Q4_K_M direct semantic smoke: PASS when run on demand with two CPU threads; the check `٣ + ٤` returned `٣ + ٤ = ٧`.
- The same 1.7B model as an autonomous local planning agent: NO_GO on this device because latency and tool-selection reliability were not acceptable.
- Queue crash/restart recovery: PASS using an expired lease recovered by a fresh process.
- Verified backup and restore: PASS with checkpoint and queue equality after restore into a clean directory.

## Runtime policy

The deterministic local HAKIM core remains authoritative. It owns SQLite state, queue, evidence, checkpoints, approval records, backup, restore, and guarded reversible tools without requiring a model.

A local LLM is optional and language-only. It MUST NOT be kept resident as a daemon on this profile. When explicitly needed, it is started on demand, bound only to `127.0.0.1`, protected by an ephemeral API key, limited to one parallel slot, two CPU threads and 1024 context, then terminated immediately after the request.

Local-model autonomous planning is disabled for this profile unless a later field qualification supersedes this evidence.

## Acceptance rule

Do not mark full Android device qualification PASS while any of these gates remain open:

- background/screen-off continuity,
- end-to-end offline operation,
- reboot continuity.

A failure in those gates does not invalidate the already proven low-resource local core. Preserve the last verified checkpoint and use explicit `PASS`, `FAIL`, `NO_GO`, `NOT_PROVEN`, or `CONDITIONAL_PASS` states rather than optimistic inference.
