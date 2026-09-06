#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# HAKIM Ω local-only bootstrap for Android/Termux.
# This script installs no paid service and stores state under the user's home.

pkg update -y
pkg install -y python git cmake clang make curl

ROOT="${OMEGA_ROOT:-$HOME/hakim-workspace}"
mkdir -p "$ROOT" "$HOME/models" "$HOME/src"
python -m pip install --upgrade pip setuptools

cat <<'EOF'
HAKIM Ω local runtime prerequisites are ready.

Next, from the SovereignAssistant repository directory:
  python -m pip install -e .
  python -m app.hakim.run_local_sovereign --root ~/hakim-workspace init

For fully local AI reasoning, build/install llama.cpp and keep a GGUF model locally,
then start llama-server on 127.0.0.1:8080. The HAKIM core itself does not require
an API key or cloud account.
EOF
