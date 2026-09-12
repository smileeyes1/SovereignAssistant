#!/system/bin/sh
# Android 15 proof that owned-browser mutations cannot replay in the safe core.
# Pre-field evidence only; never qualifies physical TECNO/HiOS behavior.
set -eu

PKG="org.hakim.omega.companion"
PORT="47651"
PAIR_TOKEN="emulator-only-qualification-token-0123456789"
BASE_URL="http://127.0.0.1:${PORT}"
AUTH="Authorization: Bearer ${PAIR_TOKEN}"
RID="emulator-replay-proof-0001"
ACTION='{"action":"browser_reload"}'

adb forward "tcp:${PORT}" "tcp:${PORT}" >/dev/null
adb shell am start -W -n "$PKG/.MainActivity" >/dev/null

# Runtime status and WebView attachment are distinct readiness conditions.
i=0
until curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-idempotency-status.json 2>/dev/null && grep -F '"control_scope":"OWNED_BROWSER_ONLY"' /tmp/hakim-idempotency-status.json >/dev/null; do
  i=$((i + 1)); [ "$i" -lt 30 ] || { echo 'Safe-core control plane did not become ready for replay proof' >&2; cat /tmp/hakim-idempotency-status.json >&2 || true; exit 1; }; sleep 1
done

i=0
while [ "$i" -lt 30 ]; do
  code=$(curl -sS -o /tmp/hakim-idempotency-ui.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/ui")
  if [ "$code" = '200' ] && grep -F '"scope":"OWNED_BROWSER_ONLY"' /tmp/hakim-idempotency-ui.json >/dev/null; then break; fi
  i=$((i + 1)); sleep 1
done
[ "$i" -lt 30 ] || { echo 'Owned browser did not attach for replay proof' >&2; cat /tmp/hakim-idempotency-ui.json >&2 || true; exit 1; }
echo 'STAGE_IDEMPOTENCY_OWNED_BROWSER_PRECONDITION=PROVEN'

# Without a durable identity the mutation must fail closed before dispatch.
code=$(curl -sS -o /tmp/hakim-no-rid.json -w '%{http_code}' -H "$AUTH" -H 'Content-Type: application/json' -d "$ACTION" "${BASE_URL}/v1/action")
[ "$code" = '400' ] || { echo "missing request identity expected 400 got $code" >&2; cat /tmp/hakim-no-rid.json >&2; exit 1; }
grep -F '"error":"request_id_required"' /tmp/hakim-no-rid.json >/dev/null || { cat /tmp/hakim-no-rid.json >&2; exit 1; }
echo 'STAGE_IDEMPOTENCY_MISSING_ID_FAIL_CLOSED=PROVEN'

# Execute exactly once with a durable request identity.
code=$(curl -sS -o /tmp/hakim-rid-first.json -w '%{http_code}' -H "$AUTH" -H "X-Hakim-Request-Id: ${RID}" -H 'Content-Type: application/json' -d "$ACTION" "${BASE_URL}/v1/action")
[ "$code" = '200' ] || { echo "first identified browser action expected 200 got $code" >&2; cat /tmp/hakim-rid-first.json >&2; exit 1; }
grep -F '"ok":true' /tmp/hakim-rid-first.json >/dev/null || { cat /tmp/hakim-rid-first.json >&2; exit 1; }
echo 'STAGE_IDEMPOTENCY_FIRST_EXECUTION=PROVEN'

# Process death must not erase the replay ledger.
adb shell am force-stop "$PKG"
adb shell am start -W -n "$PKG/.MainActivity" >/dev/null

# Do not make an instantaneous pidof sample a release gate: Android process
# publication after am start is asynchronous. Bound it, then prove readiness by
# the authenticated control endpoint below.
i=0
until adb shell pidof "$PKG" >/dev/null 2>&1; do
  i=$((i + 1)); [ "$i" -lt 15 ] || { echo 'HAKIM process did not reappear after forced process death' >&2; exit 1; }; sleep 1
done

adb forward "tcp:${PORT}" "tcp:${PORT}" >/dev/null
i=0
until curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-idempotency-after-restart.json 2>/dev/null; do
  i=$((i + 1)); [ "$i" -lt 30 ] || { echo 'Safe core did not recover for replay proof' >&2; exit 1; }; sleep 1
done

# Duplicate rejection must remain durable. Wait for the owned browser so a 409 can
# only mean replay protection, not a transient browser-unavailable race.
i=0
while [ "$i" -lt 30 ]; do
  code=$(curl -sS -o /tmp/hakim-idempotency-ui-after-restart.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/ui")
  [ "$code" = '200' ] && break
  i=$((i + 1)); sleep 1
done
[ "$i" -lt 30 ] || { echo 'Owned browser did not recover after process death' >&2; cat /tmp/hakim-idempotency-ui-after-restart.json >&2 || true; exit 1; }

code=$(curl -sS -o /tmp/hakim-rid-replay.json -w '%{http_code}' -H "$AUTH" -H "X-Hakim-Request-Id: ${RID}" -H 'Content-Type: application/json' -d "$ACTION" "${BASE_URL}/v1/action")
[ "$code" = '409' ] || { echo "duplicate browser request expected 409 got $code" >&2; cat /tmp/hakim-rid-replay.json >&2; exit 1; }
grep -F '"error":"duplicate_request"' /tmp/hakim-rid-replay.json >/dev/null || { cat /tmp/hakim-rid-replay.json >&2; exit 1; }
grep -F "\"request_id\":\"${RID}\"" /tmp/hakim-rid-replay.json >/dev/null || { cat /tmp/hakim-rid-replay.json >&2; exit 1; }

if adb shell ps -A | grep -E 'llama-server|llama\.cpp'; then
  echo 'Unexpected resident local-model process during replay proof' >&2
  exit 1
fi

echo 'EMULATOR_ACTION_IDEMPOTENCY=PROVEN_OWNED_BROWSER_ONLY'
echo 'EMULATOR_ACTION_REPLAY_AFTER_PROCESS_DEATH=PROVEN'
echo 'PHYSICAL_TECNO_IDEMPOTENCY_QUALIFICATION=NOT_PROVEN'
