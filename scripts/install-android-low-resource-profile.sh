#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PREFIX_DIR="/data/data/com.termux/files/usr"
HOME_DIR="${HOME:-/data/data/com.termux/files/home}"
OMEGA="$HOME_DIR/.omega"
BIN="$HOME_DIR/bin"
MODEL="${HAKIM_LOW_RESOURCE_MODEL:-$OMEGA/models/Qwen3-1.7B-Q4_K_M.gguf}"
mkdir -p "$OMEGA" "$BIN"

python "$PREFIX_DIR"/bin/python - <<'PY' 2>/dev/null || true
PY

"$PREFIX_DIR/bin/python" - <<'PY'
import json, os, subprocess
from pathlib import Path
home = Path(os.environ.get("HOME", "/data/data/com.termux/files/home"))
def prop(k):
    try: return subprocess.check_output(["getprop", k], text=True).strip()
    except Exception: return ""
mem_kib = 0
try:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemTotal:"):
            mem_kib = int(line.split()[1]); break
except Exception: pass
profile = {
  "profile": "LOW_RESOURCE_ANDROID",
  "device": prop("ro.product.model") or "Android",
  "android": prop("ro.build.version.release"),
  "ram_gib": round(mem_kib / 1024 / 1024, 2) if mem_kib else None,
  "persistent_model": False,
  "core_runtime": "deterministic_local",
  "background_daemon_required": False,
  "local_model_role": "optional_on_demand_language_only",
  "max_model_threads": 2,
  "max_context": 1024,
  "agent_planning_with_local_model": False,
  "preserve_battery_and_thermal_headroom": True
}
p = home / ".omega" / "device-profile.json"
p.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
os.chmod(p, 0o600)
PY

cat > "$BIN/hakim-local-language" <<'SH'
#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
P="/data/data/com.termux/files/usr"; H="${HOME:-/data/data/com.termux/files/home}"
M="${HAKIM_LOW_RESOURCE_MODEL:-$H/.omega/models/Qwen3-1.7B-Q4_K_M.gguf}"
[ -f "$M" ] || { echo '{"status":"MODEL_NOT_INSTALLED"}'; exit 2; }
[ "$#" -gt 0 ] || { echo 'usage: hakim-local-language <prompt>'; exit 2; }
PORT=$((18000 + ($$ % 1000))); LOG="$H/.omega/llama-ondemand.log"
"$P/bin/llama-server" -m "$M" --host 127.0.0.1 --port "$PORT" -c 1024 --parallel 1 -ngl 0 --threads 2 --threads-batch 2 --reasoning off >"$LOG" 2>&1 &
PID=$!; trap 'kill "$PID" 2>/dev/null || true; wait "$PID" 2>/dev/null || true' EXIT INT TERM
for _ in $(seq 1 45); do "$P/bin/curl" -fsS --max-time 1 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break; sleep 1; done
PROMPT="$*" PORT="$PORT" "$P/bin/python" - <<'PY'
import json, os, urllib.request
body=json.dumps({"model":"local","messages":[{"role":"user","content":os.environ["PROMPT"]}],"temperature":0,"max_tokens":192}).encode()
req=urllib.request.Request(f'http://127.0.0.1:{os.environ["PORT"]}/v1/chat/completions',data=body,headers={'Content-Type':'application/json'})
data=json.loads(urllib.request.urlopen(req,timeout=120).read().decode())
print(data['choices'][0]['message']['content'])
PY
SH
chmod 700 "$BIN/hakim-local-language"
echo '{"status":"PASS","profile":"LOW_RESOURCE_ANDROID","persistent_model":false,"agent_planning_with_local_model":false}'