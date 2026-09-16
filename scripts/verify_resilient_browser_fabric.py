#!/usr/bin/env python3
from pathlib import Path
import re, sys

root = Path(__file__).resolve().parents[1]
relay = root / 'android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimDirectRelay.kt'
manifest = root / 'android/hakim-companion/app/src/main/AndroidManifest.xml'
text = relay.read_text(encoding='utf-8')
manifest_text = manifest.read_text(encoding='utf-8')

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
    'loop_backoff': 'coerceAtMost(60_000L)' in text,
    'loopback_control_only': '127.0.0.1' in text,
    'mutations_require_approval': 'READ_ONLY_OPS' in text and 'savePending' in text and 'showApproval' in text,
    'no_shell_operation': not re.search(r'"(?:shell|exec|terminal|adb)"', text),
    'no_new_manifest_permission_from_contract': 'HAKIM_BROWSER_RESILIENT_FABRIC' not in manifest_text,
}

failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(('PASS' if ok else 'FAIL') + ' ' + name)
if failed:
    print('FAILED: ' + ', '.join(failed), file=sys.stderr)
    raise SystemExit(1)
print('SOURCE_CONTRACT_PASS: resilient browser fabric invariants present; FIELD not asserted.')
