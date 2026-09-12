#!/system/bin/sh
# Disposable Android 15 proof that sovereign-local browser actions cannot replay.
# Pre-field evidence only; never qualifies physical-device behavior.
set -eu

PKG="org.hakim.omega.companion"
PORT="47651"
PAIR_TOKEN="emulator-only-qualification-token-0123456789"
BASE_URL="http://127.0.0.1:${PORT}"
AUTH="Authorization: Bearer ${PAIR_TOKEN}"
RID="emulator-replay-proof-0001"
ACTION='{"action":"local_proof","message":"اختبار منع إعادة التنفيذ"}'

adb forward "tcp:${PORT}" "tcp:${PORT}" >/dev/null
adb shell am start -W -n "$PKG/.MainActivity" >/dev/null

i=0
until curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-idempotency-status.json 2>/dev/null && grep -F '"attached":true' /tmp/hakim-idempotency-status.json >/dev/null; do
  i=$((i + 1)); [ "$i" -lt 30 ] || { echo 'Owned browser did not become ready for replay proof' >&2; cat /tmp/hakim-idempotency-status.json >&2 || true; exit 1; }; sleep 1
done
grep -F '"external_transport_enabled":false' /tmp/hakim-idempotency-status.json >/dev/null
echo 'STAGE_IDEMPOTENCY_BROWSER_PRECONDITION=PROVEN'

# Without a durable identity it must fail closed before execution.
code=$(curl -sS -o /tmp/hakim-no-rid.json -w '%{http_code}' -H "$AUTH" -H 'Content-Type: application/json' -d "$ACTION" "${BASE_URL}/v1/action")
[ "$code" = '400' ] || { echo "missing request identity expected 400 got $code" >&2; cat /tmp/hakim-no-rid.json >&2; exit 1; }
grep -F '"error":"request_id_required"' /tmp/hakim-no-rid.json >/dev/null || { cat /tmp/hakim-no-rid.json >&2; exit 1; }
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

i=0
until curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-idempotency-after-restart.json 2>/dev/null && grep -F '"attached":true' /tmp/hakim-idempotency-after-restart.json >/dev/null; do
  i=$((i + 1)); [ "$i" -lt 30 ] || { echo 'Companion/browser did not recover for replay proof' >&2; cat /tmp/hakim-idempotency-after-restart.json >&2 || true; exit 1; }; sleep 1
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
echo 'PHYSICAL_PHONE_IDEMPOTENCY_QUALIFICATION=NOT_PROVEN'
