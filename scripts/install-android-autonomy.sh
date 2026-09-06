#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# HAKIM Ω Android autonomy bootstrap.
# Core runtime remains local/offline. Node/Remote Desktop Commander are only an
# optional temporary bridge for ChatGPT device access and are not runtime deps.

if [[ ! -d /data/data/com.termux/files/usr ]]; then
  echo 'ERROR: run this script inside Termux.' >&2
  exit 2
fi

# Termux is rolling-release. Never install a new runtime on top of stale core
# libraries: partial upgrades can produce linker/OpenSSL symbol mismatches.
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get -o Dpkg::Options::="--force-confold" full-upgrade -y
pkg install -y python git cmake clang make curl termux-api nodejs tmux

REPO="${OMEGA_REPO:-$HOME/SovereignAssistant}"
ROOT="${OMEGA_ROOT:-$HOME/hakim-workspace}"
mkdir -p "$ROOT" "$HOME/bin" "$HOME/models" "$HOME/.termux/boot" "$ROOT/.omega"

if [[ -d "$REPO/.git" ]]; then
  git -C "$REPO" fetch --all --prune
  git -C "$REPO" checkout main
  git -C "$REPO" pull --ff-only
else
  git clone https://github.com/smileeyes1/SovereignAssistant.git "$REPO"
fi

python -m pip install --upgrade pip setuptools
python -m pip install -e "$REPO"

# Persist exact device/runtime identity as owned evidence. Qualification applies
# only to this exact combination; never generalize a PASS to all Android devices.
python - "$ROOT/.omega/device.json" <<'PY'
import json, platform, subprocess, sys
from pathlib import Path

def getprop(key: str) -> str:
    try:
        return subprocess.check_output(["getprop", key], text=True).strip()
    except Exception:
        return ""

payload = {
    "manufacturer": getprop("ro.product.manufacturer"),
    "brand": getprop("ro.product.brand"),
    "model": getprop("ro.product.model"),
    "device": getprop("ro.product.device"),
    "android_release": getprop("ro.build.version.release"),
    "android_sdk": getprop("ro.build.version.sdk"),
    "abi": getprop("ro.product.cpu.abi"),
    "python": platform.python_version(),
}
path = Path(sys.argv[1])
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
path.chmod(0o600)
PY

cat > "$HOME/bin/hakim-android" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
exec python -m app.hakim.run_android_sovereign --root "$ROOT" "\$@"
EOF
chmod 700 "$HOME/bin/hakim-android"

cat > "$HOME/bin/hakim-approval-test" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
exec python -m app.hakim.run_android_sovereign --root "$ROOT" approval-test --ttl 120
EOF
chmod 700 "$HOME/bin/hakim-approval-test"

cat > "$HOME/bin/pair-chatgpt-device" <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cat <<'MSG'
This is an OPTIONAL temporary remote bridge. It uses Remote Desktop Commander
and the network. HAKIM Ω does not need it for local runtime. Continue only when
you intentionally want ChatGPT to reach this Termux device.
MSG
termux-wake-lock >/dev/null 2>&1 || true
tmux kill-session -t dc >/dev/null 2>&1 || true
tmux new-session -d -s dc 'npx -y @wonderwhy-er/desktop-commander@latest remote --persist-session >>"$HOME/dc-remote.log" 2>&1'
echo 'Remote bridge started in tmux session: dc'
echo 'Log: ~/dc-remote.log'
tail -n 30 "$HOME/dc-remote.log" 2>/dev/null || true
EOF
chmod 700 "$HOME/bin/pair-chatgpt-device"

cat > "$HOME/bin/open-hakim-permissions" <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
# Android must grant notification permission to Termux:API for the approval gate.
am start -a android.settings.APPLICATION_DETAILS_SETTINGS -d package:com.termux.api >/dev/null 2>&1 || true
EOF
chmod 700 "$HOME/bin/open-hakim-permissions"

cat > "$HOME/bin/open-hakim-background-settings" <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
# Standard Android entry points. OEM/HiOS labels may differ.
am start -a android.settings.APPLICATION_DETAILS_SETTINGS -d package:com.termux >/dev/null 2>&1 || true
sleep 1
am start -a android.settings.IGNORE_BATTERY_OPTIMIZATION_SETTINGS >/dev/null 2>&1 || true
EOF
chmod 700 "$HOME/bin/open-hakim-background-settings"

# Make helper commands available in every Termux shell without requiring the
# user's profile to add ~/bin to PATH. Keep canonical scripts under ~/bin and
# expose stable symlinks through Termux's standard executable directory.
for tool in hakim-android hakim-approval-test pair-chatgpt-device open-hakim-permissions open-hakim-background-settings; do
  ln -sfn "$HOME/bin/$tool" "$PREFIX/bin/$tool"
done

cat > "$HOME/.termux/boot/20-hakim-omega" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock >/dev/null 2>&1 || true
sleep 8
if curl -fsS --max-time 2 http://127.0.0.1:8080/v1/models >/dev/null 2>&1; then
  nohup python -m app.hakim.run_android_sovereign --root "$ROOT" --model "\${OMEGA_MODEL:-local}" daemon --interval 2 >>"$ROOT/.omega/daemon.log" 2>&1 &
fi
EOF
chmod 700 "$HOME/.termux/boot/20-hakim-omega"

python -m app.hakim.run_android_sovereign --root "$ROOT" init >/dev/null
python -m app.hakim.run_android_sovereign --root "$ROOT" doctor

for tool in hakim-android hakim-approval-test pair-chatgpt-device open-hakim-permissions open-hakim-background-settings; do
  command -v "$tool" >/dev/null
 done

cat <<'EOF'

HAKIM Ω Android autonomy core is installed.

ONE-TIME Android prerequisites that require your tap/consent:
1) Install/open Termux:API Android app from the same trusted source family as Termux.
2) Grant Termux:API notification permission. Run: open-hakim-permissions
3) Test the local human gate: hakim-approval-test
4) Set Termux battery/background mode to unrestricted where Android/HiOS exposes it.
   Helper: open-hakim-background-settings
5) Optional: install/open Termux:Boot once if you want reboot auto-start.
6) Optional temporary ChatGPT bridge: pair-chatgpt-device

The remote bridge is NOT required for HAKIM Ω to run locally.
Device qualification is not PASS until real notification, background, reboot,
offline, local-model and recovery tests pass on the exact phone.
EOF
