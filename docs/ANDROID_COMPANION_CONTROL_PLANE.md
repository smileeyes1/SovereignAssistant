# HAKIM Ω Android Companion Control Plane

## Goal
Provide the highest practical user-authorized control plane on Android without root or factory reset. The companion is not the sovereign brain; it is a local actuator/sensor bridge for the deterministic HAKIM core.

## Security contract
- Server binds to `127.0.0.1`/loopback only.
- Requests require a random bearer token generated and stored by Termux with mode `0600`.
- Pairing occurs through the local `hakim://pair` deep link; the token is stored only in app-private preferences and Termux private storage.
- UI control exists only after the user enables Android Accessibility for HAKIM.
- Notification content exists only after the user grants Notification Listener access.
- The foreground service is not exported.
- Consequential actions remain subject to the existing HAKIM human approval gate; the companion does not grant authority by itself.

## Capabilities
- Read a bounded accessibility UI tree.
- Global navigation: Home, Back, Recents, Notifications, Quick Settings.
- Click by visible text, set text, coordinate tap, swipe.
- Launch an installed app by package name.
- Capture a screenshot through Accessibility on supported Android versions.
- Read a bounded recent notification buffer after explicit OS grant.
- Restart local control service after boot where Android/HiOS allows it.

## Resource policy for TECNO / constrained devices
The companion contains no LLM and should remain lightweight. Qwen3-1.7B remains on-demand only with the `LOW_RESOURCE_ANDROID` profile; it is not a persistent planner or daemon.

## Deliberate limits
This is not root and does not bypass Android security prompts. Installation, Accessibility, Notification Access, Shizuku/ADB authorization, Device Owner provisioning, and root remain sovereign user/OS decisions. Device Owner/root are not default because they materially increase blast radius and may require destructive provisioning.
