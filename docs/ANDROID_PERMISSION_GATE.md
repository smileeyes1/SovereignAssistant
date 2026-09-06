# HAKIM Ω Android Permission Gate

## Purpose

Keep normal work autonomous while preserving human sovereignty for consequential actions. The gate is local-first: approval state lives under `ROOT/.omega/approvals`, not in ChatGPT memory or a cloud account.

## Flow

`SAFE WORK -> AUTO`

`CONSEQUENTIAL ACTION -> local approval request -> Android notification -> [سماح] / [رفض] -> one-time decision -> continue or stop`

Requests expire automatically and cannot be silently promoted. The approval token is not stored in plaintext in the request record; only its SHA-256 digest is persisted. Final decisions are immutable.

## Requirements

- Termux.
- `termux-api` package inside Termux.
- Termux:API Android app from a trusted source compatible with the installed Termux build.
- Android notification permission granted to Termux:API.

Current upstream `termux-notification` supports notification buttons and button actions. Android may require notification permission depending on OS version.

## Install

From the repository in Termux:

```bash
bash scripts/install-android-autonomy.sh
```

Then grant Android notification permission and run:

```bash
hakim-approval-test
```

PASS requires an Android notification with two explicit choices, then the CLI result must match the button pressed.

## Agent use

The Android runner adds a single gated tool:

```json
{"action":"tool","tool":"request_approval","args":{"action":"publish","summary":"نشر الإصدار النهائي","risk":"high","ttl_seconds":300},"reason":"External irreversible commitment"}
```

The agent must not interpret silence as approval. `rejected` and `expired` are authoritative.

## Remote ChatGPT bridge

`scripts/install-android-autonomy.sh` creates `pair-chatgpt-device`, which can start Remote Desktop Commander's remote MCP agent. This is optional and network-dependent. It exists only to let an authorized ChatGPT session reach the Termux terminal for setup/maintenance. It is not a runtime dependency and must never become the system of record.

Pairing requires an explicit OAuth/device-code confirmation by the user. Closing the remote agent disconnects the bridge.

## Reboot continuity

The installer prepares `~/.termux/boot/20-hakim-omega`. To use it, install/open Termux:Boot once and ensure Android battery restrictions do not kill the process. The boot script only starts the HAKIM daemon when the local model endpoint is healthy.

## Security invariants

- No arbitrary shell is added to HAKIM's agent tool surface.
- Notification buttons execute only the broker's fixed approve/reject decision command.
- Approval records are local and mode `0600` where supported.
- Requests expire.
- One request cannot approve another request.
- A wrong token does not change state.
- A final decision is not mutable.
- Remote Desktop Commander is optional and removable.
- Local SQLite/LKG/queue remain authoritative for runtime continuity.

## Qualification gate

Do not claim `ANDROID_PERMISSION_GATE_QUALIFIED` until all pass on the actual phone:

1. Notification appears.
2. Approve button produces `approved` for the same request.
3. Reject button produces `rejected` for a new request.
4. Timeout produces `expired`.
5. Airplane mode still permits the local notification gate.
6. Kill/restart preserves pending/final approval state.
7. Reboot + Termux:Boot restores daemon when configured.
8. No cloud connection is required for the approval gate itself.
