#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# HAKIM Ω Android autonomy bootstrap.
# Core runtime remains local/offline. Node/Remote Desktop Commander are only an
# optional temporary bridge for ChatGPT device access and are not runtime deps.

if [[ ! -d /data/data/com.termux/files/usr ]]; then
  echo 'ERROR: run this script inside Termux.' >&2
  exit 2
fi

pkg update -y
pkg install -y python git cmake clang make curl termux-api nodejs

REPO="${OMEGA_REPO:-$HOME/SovereignAssistant}"
ROOT="${OMEGA_ROOT:-$HOME/hakim-workspace}"
mkdir -p "$ROOT" "$HOME/bin" "$HOME/models" "$HOME/.termux/boot"

if [[ -d "$REPO/.git" ]]; then
  git -C "$REPO" fetch --all --prune
else
  git clone https://github.com/smileeyes1/SovereignAssistant.git "$REPO"
fi

python -m pip install --upgrade pip setuptools
python -m pip install -e "$REPO"

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
exec npx @wonderwhy-er/desktop-commander@latest remote
EOF
chmod 700 "$HOME/bin/pair-chatgpt-device"

cat > "$HOME/bin/open-hakim-permissions" <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
# Android must grant notification permission to Termux:API for the approval gate.
am start -a android.settings.APPLICATION_DETAILS_SETTINGS -d package:com.termux.api >/dev/null 2>&1 || true
EOF
chmod 700 "$HOME/bin/open-hakim-permissions"

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

cat <<'EOF'

HAKIM Ω Android autonomy core is installed.

ONE-TIME Android prerequisites that require your tap/consent:
1) Install/open the Termux:API Android app from the same trusted source family as Termux.
2) Grant Termux:API notification permission. Run: open-hakim-permissions
3) Test the local human gate: hakim-approval-test
4) Optional: install/open Termux:Boot once if you want reboot auto-start.
5) Optional temporary ChatGPT bridge: pair-chatgpt-device

The remote bridge is NOT required for HAKIM Ω to run locally.
EOF
