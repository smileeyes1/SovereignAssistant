#!/system/bin/sh
# Disposable Android 15 proof that non-idempotent Companion UI actions cannot replay.
# Pre-field evidence only; never qualifies physical TECNO/HiOS behavior.
set -eu

PKG="org.hakim.omega.companion"
ACCESSIBILITY_SERVICE="${PKG}/.HakimAccessibilityService"
PORT="47651"
PAIR_TOKEN="emulator-only-qualification-token-0123456789"
BASE_URL="http://127.0.0.1:${PORT}"
AUTH="Authorization: Bearer ${PAIR_TOKEN}"
RID="emulator-replay-proof-0001"
ACTION='{"action":"tap","x":540,"y":1200}'

adb forward "tcp:${PORT}" "tcp:${PORT}" >/dev/null

# Earlier gates intentionally exercise reboot/revocation and may leave
# Accessibility disconnected. Establish this gate's own explicit precondition
# instead of depending on mutable state from another test.
adb shell settings put secure enabled_accessibility_services "$ACCESSIBILITY_SERVICE"
adb shell settings put secure accessibility_enabled 1
i=0
until curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-idempotency-status.json 2>/dev/null && grep -F '"accessibility":true' /tmp/hakim-idempotency-status.json >/dev/null; do
  i=$((i + 1)); [ "$i" -lt 30 ] || { echo 'Accessibility did not become ready for replay proof' >&2; cat /tmp/hakim-idempotency-status.json >&2 || true; exit 1; }; sleep 1
done
echo 'STAGE_IDEMPOTENCY_ACCESSIBILITY_PRECONDITION=PROVEN'

# Use a bounded gesture rather than BACK: BACK success depends on whatever
# screen a previous gate happened to leave active, while dispatching a tap is
# itself the non-idempotent side effect whose replay protection we need to prove.
# Without a durable identity it must fail closed before dispatch.
code=$(curl -sS -o /tmp/hakim-no-rid.json -w '%{http_code}' -H "$AUTH" -H 'Content-Type: application/json' -d "$ACTION" "${BASE_URL}/v1/action")
[ "$code" = '400' ] || { echo "missing request identity expected 400 got $code" >&2; cat /tmp/hakim-no-rid.json >&2; exit 1; }
grep -F '"error":"request_id_required"' /tmp/hakim-no-rid.json >/dev/null || { echo 'missing request identity response lacked request_id_required' >&2; cat /tmp/hakim-no-rid.json >&2; exit 1; }
echo 'STAGE_IDEMPOTENCY_MISSING_ID_FAIL_CLOSED=PROVEN'

# Execute once with an explicit durable request identity.
code=$(curl -sS -o /tmp/hakim-rid-first.json -w '%{http_code}' -H "$AUTH" -H "X-Hakim-Request-Id: ${RID}" -H 'Content-Type: application/json' -d "$ACTION" "${BASE_URL}/v1/action")
[ "$code" = '200' ] || { echo "first identified action expected 200 got $code" >&2; cat /tmp/hakim-rid-first.json >&2; exit 1; }
grep -F '"ok":true' /tmp/hakim-rid-first.json >/dev/null || { cat /tmp/hakim-rid-first.json >&2; exit 1; }
echo 'STAGE_IDEMPOTENCY_FIRST_EXECUTION=PROVEN'

# Kill the process to prove the replay ledger survives process death.
adb shell am force-stop "$PKG"
adb shell am start -W -n "$PKG/.MainActivity" >/dev/null
adb shell pidof "$PKG" >/dev/null
adb forward "tcp:${PORT}" "tcp:${PORT}" >/dev/null

# A replay proof must not depend on a race between process restart and
# Accessibility service rebinding. Re-establish and observe the same authority
# precondition before asserting that duplicate rejection wins before execution.
adb shell settings put secure enabled_accessibility_services "$ACCESSIBILITY_SERVICE"
adb shell settings put secure accessibility_enabled 1
i=0
until curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-idempotency-after-restart.json 2>/dev/null && grep -F '"accessibility":true' /tmp/hakim-idempotency-after-restart.json >/dev/null; do
  i=$((i + 1)); [ "$i" -lt 30 ] || { echo 'Companion/Accessibility did not recover for replay proof' >&2; cat /tmp/hakim-idempotency-after-restart.json >&2 || true; exit 1; }; sleep 1
done
echo 'STAGE_IDEMPOTENCY_POST_RESTART_PRECONDITION=PROVEN'

# Replay of the same request identity must be rejected before execution.
code=$(curl -sS -o /tmp/hakim-rid-replay.json -w '%{http_code}' -H "$AUTH" -H "X-Hakim-Request-Id: ${RID}" -H 'Content-Type: application/json' -d "$ACTION" "${BASE_URL}/v1/action")
[ "$code" = '409' ] || { echo "duplicate request expected 409 got $code" >&2; cat /tmp/hakim-rid-replay.json >&2; exit 1; }
grep -F '"error":"duplicate_request"' /tmp/hakim-rid-replay.json >/dev/null || { cat /tmp/hakim-rid-replay.json >&2; exit 1; }
grep -F "\"request_id\":\"${RID}\"" /tmp/hakim-rid-replay.json >/dev/null || { cat /tmp/hakim-rid-replay.json >&2; exit 1; }

if adb shell ps -A | grep -E 'llama-server|llama\.cpp'; then
  echo 'Unexpected resident local-model process during replay proof' >&2
  exit 1
fi

echo 'EMULATOR_ACTION_IDEMPOTENCY=PROVEN'
echo 'EMULATOR_ACTION_REPLAY_AFTER_PROCESS_DEATH=PROVEN'
echo 'PHYSICAL_TECNO_IDEMPOTENCY_QUALIFICATION=NOT_PROVEN'
