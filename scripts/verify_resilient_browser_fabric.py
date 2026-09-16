#!/usr/bin/env python3
from pathlib import Path
import re, sys

root = Path(__file__).resolve().parents[1]
relay = root / 'android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimDirectRelay.kt'
manifest = root / 'android/hakim-companion/app/src/main/AndroidManifest.xml'
boot = root / 'android/hakim-companion/app/src/main/java/org/hakim/omega/companion/BootReceiver.kt'
service = root / 'android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimForegroundService.kt'
text = relay.read_text(encoding='utf-8')
manifest_text = manifest.read_text(encoding='utf-8')
boot_text = boot.read_text(encoding='utf-8')
service_text = service.read_text(encoding='utf-8')

checks = {
    'result_topic_contract': 'KEY_RESULT_TOPIC' in text and 'relay_result_topic' in text,
    'legacy_result_url_absent': 'result_url' not in text,
    'request_id_validation': 'REQUEST_ID.matches(requestId)' in text,
    'allowlist': 'ALLOWED_OPS' in text and 'unsupported_operation' in text,
    'expiry': 'request_expired' in text and 'expiresAt <= System.currentTimeMillis()' in text,
    'auth': 'HmacSHA256' in text and 'MessageDigest.isEqual' in text,
    'encrypted_carrier': 'AES/GCM/NoPadding' in text and 'HC1.' in text and 'HR1.' in text,
    'duplicate_guard': 'claimRemoteRequest' in text and 'duplicate_request' in text,
    'bounded_payload': 'MAX_PAYLOAD_B64' in text,
    'malformed_payload_fails_closed': 'decodePayload(envelope) == null' in text and 'invalid_payload' in text and 'getOrNull()' in text,
    'loop_backoff': 'coerceAtMost(60_000L)' in text,
    'loopback_control_only': '127.0.0.1' in text,
    'mutations_require_approval': 'READ_ONLY_OPS' in text and 'savePending' in text and 'showApproval' in text,
    'pending_not_removed_before_execution': 'readPending(context,requestId)' in text and 'clearPending(context,requestId)' in text and 'takePending' not in text,
    'durable_result_outbox': 'OUTBOX_PREFS' in text and 'queueResult' in text and '.commit()' in text,
    'result_retry_state': 'attempts' in text and 'next_attempt_ms' in text and 'flushOutbox(context)' in text,
    'bounded_result_retry_backoff': 'coerceAtMost(60000L)' in text,
    'outbox_restored_on_loop': re.search(r'flushOutbox\(context\).*KEY_LAST_MESSAGE_ID', text, re.S) is not None,
    'boot_permission_present': 'android.permission.RECEIVE_BOOT_COMPLETED' in manifest_text,
    'boot_receiver_registered': '.BootReceiver' in manifest_text and 'android.intent.action.BOOT_COMPLETED' in manifest_text and 'android.intent.action.MY_PACKAGE_REPLACED' in manifest_text,
    'boot_requires_existing_pairing': 'pair_token' in boot_text and 'HakimForegroundService.start(context)' in boot_text,
    'foreground_service_sticky': 'START_STICKY' in service_text and 'startForeground' in service_text,
    'local_supervisor_present': 'SUPERVISOR_INTERVAL_MS' in service_text and 'companion_heartbeat_ms' in service_text and 'RECOVERING' in service_text,
    'direct_relay_started_by_service': 'HakimDirectRelay(this)' in service_text and '.also { it.start() }' in service_text,
    'no_shell_operation': not re.search(r'"(?:shell|exec|terminal|adb)"', text),
    'no_new_manifest_permission_from_contract': 'HAKIM_BROWSER_RESILIENT_FABRIC' not in manifest_text,
}

failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items(): print(('PASS' if ok else 'FAIL') + ' ' + name)
if failed:
    print('FAILED: ' + ', '.join(failed), file=sys.stderr)
    raise SystemExit(1)
print('SOURCE_CONTRACT_PASS: relay recovery + boot continuity + fail-closed payload invariants present; FIELD not asserted.')
