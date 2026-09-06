# HAKIM Ω — Frozen Device Baseline

## Target
- Device: **TECNO POVA 7**
- Platform: **Android**
- Observed SDK: **35**
- Execution: **Termux / aarch64**
- Qualification scope: this exact device + Android/Termux/runtime/model combination only.

## Governing operating model
- Safe, reversible local work: AUTO.
- Consequential action: local Android notification approval is required.
- Silence, timeout or expired request is never approval.
- Remote Desktop Commander is only a temporary maintenance bridge and is never a runtime dependency.

## Proven field observations — 2026-09-06
- Termux installed successfully.
- A partial Termux package state caused new Node.js to fail with an OpenSSL symbol mismatch.
- Full package upgrade repaired the mismatch; Node.js and npm then executed successfully.
- Remote Desktop Commander 0.2.48 authenticated and registered the phone, but remote tool delivery remains transport-flaky.
- `tmux` and `termux-wake-lock` improve survival but do not by themselves prove Android 15/HiOS background persistence.

## Frozen Android bootstrap invariants
1. Perform a full Termux upgrade before installing new runtime packages such as Node.js.
2. Persist manufacturer, model, Android release, SDK and ABI into owned local evidence.
3. Treat battery/background/autostart behavior as a qualification gate, not a convenience setting.
4. Use Termux:API notification buttons for sovereign `سماح` / `رفض` approval.
5. Use Termux:Boot only after real reboot testing on this device.
6. Keep local inference loopback-only by default; cloud/remote bridges remain optional adapters.
7. Never label the device `LOCAL_DEVICE_RUNTIME_QUALIFIED` until notification, offline, model, recovery, backup, background and reboot gates all pass.

## Current blocker
The phone is authenticated with the remote bridge, but remote command delivery currently times out intermittently. Phone-side HAKIM installation and device qualification therefore remain **NOT PROVEN** until an actual command reaches Termux and the field gates are executed.

## Required next evidence
Execute the Android autonomy installer on the phone, record `device.json`, qualify the approval notification, then proceed through offline inference, crash/restart, LKG, backup/restore, screen-off/background, reboot and egress tests.