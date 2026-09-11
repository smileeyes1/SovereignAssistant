#!/data/data/com.termux/files/usr/bin/python
"""HAKIM signed remote bridge for Termux + Android Wireless Debugging.

No custom Android APK is required. Remote commands arrive over an outbound-only
ntfy stream, are authenticated with HMAC-SHA256, replay/expiry checked, and are
executed through a paired local adb connection with a strict allowlist.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

HOME = Path.home()
OMEGA = HOME / ".omega"
CONFIG = OMEGA / "hakim-termux-adb.json"
SEEN = OMEGA / "hakim-termux-seen.json"
CONTROL_UNTIL = OMEGA / "hakim-control-until"
LOG = OMEGA / "hakim-termux-adb.log"
REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
SIGNATURE = re.compile(r"^[0-9a-fA-F]{64}$")
PKG = re.compile(r"^[A-Za-z][A-Za-z0-9_.]{2,180}$")
ALLOWED = {"status", "ui", "screenshot", "notifications", "action", "launch"}
READ_ONLY = {"status", "ui", "screenshot", "notifications"}
MAX_MESSAGE = 65536


def now_ms() -> int:
    return int(time.time() * 1000)


def log(msg: str) -> None:
    OMEGA.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {msg}\n"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json_atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def run(cmd: list[str], timeout: int = 20, binary: bool = False):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    if binary:
        return p.returncode, p.stdout, p.stderr
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def adb_target(cfg: dict) -> str:
    target = str(cfg.get("adb_target", "")).strip()
    if not target:
        raise RuntimeError("adb_target_missing")
    return target


def adb(cfg: dict, args: list[str], timeout: int = 20, binary: bool = False):
    return run(["adb", "-s", adb_target(cfg), *args], timeout=timeout, binary=binary)


def adb_ok(cfg: dict) -> bool:
    try:
        rc, out, _ = adb(cfg, ["get-state"], timeout=6)
        return rc == 0 and out.strip() == "device"
    except Exception:
        return False


def canonical(envelope: dict) -> bytes:
    return f"{envelope.get('request_id','')}\n{envelope.get('op','')}\n{int(envelope.get('expires_at_ms',0))}\n{envelope.get('payload_b64','')}".encode()


def valid_signature(key: str, envelope: dict) -> bool:
    sig = str(envelope.get("signature", ""))
    if not SIGNATURE.fullmatch(sig):
        return False
    expected = hmac.new(key.encode(), canonical(envelope), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig.lower())


def decode_payload(envelope: dict) -> dict:
    s = str(envelope.get("payload_b64", ""))
    if not s:
        return {}
    if len(s) > 32768:
        raise ValueError("payload_too_large")
    pad = "=" * (-len(s) % 4)
    raw = base64.urlsafe_b64decode((s + pad).encode())
    obj = json.loads(raw.decode("utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("payload_not_object")
    return obj


def claim(request_id: str) -> bool:
    seen = load_json(SEEN, {})
    if request_id in seen:
        return False
    seen[request_id] = now_ms()
    cutoff = now_ms() - 7 * 24 * 3600 * 1000
    seen = {k: v for k, v in seen.items() if isinstance(v, int) and v >= cutoff}
    if len(seen) > 5000:
        seen = dict(sorted(seen.items(), key=lambda kv: kv[1])[-5000:])
    save_json_atomic(SEEN, seen)
    return True


def control_window_open() -> bool:
    try:
        return int(CONTROL_UNTIL.read_text().strip()) > now_ms()
    except Exception:
        return False


def status(cfg: dict) -> dict:
    ok = adb_ok(cfg)
    result = {"ok": ok, "adb": "device" if ok else "offline", "control_window": control_window_open()}
    if ok:
        rc, out, err = adb(cfg, ["shell", "getprop", "ro.product.manufacturer"])
        if rc == 0:
            result["manufacturer"] = out.strip()
        rc, out, err = adb(cfg, ["shell", "getprop", "ro.product.model"])
        if rc == 0:
            result["model"] = out.strip()
        rc, out, err = adb(cfg, ["shell", "getprop", "ro.build.version.release"])
        if rc == 0:
            result["android"] = out.strip()
    return result


def ui(cfg: dict) -> dict:
    if not adb_ok(cfg):
        return {"ok": False, "error": "adb_offline"}
    adb(cfg, ["shell", "uiautomator", "dump", "/sdcard/hakim-window.xml"], timeout=15)
    rc, out, err = adb(cfg, ["exec-out", "cat", "/sdcard/hakim-window.xml"], timeout=10)
    if rc != 0:
        return {"ok": False, "error": "ui_dump_failed", "detail": err[-500:]}
    return {"ok": True, "xml": out[:250000]}


def screenshot(cfg: dict) -> dict:
    if not adb_ok(cfg):
        return {"ok": False, "error": "adb_offline"}
    rc, data, err = adb(cfg, ["exec-out", "screencap", "-p"], timeout=20, binary=True)
    if rc != 0 or not data.startswith(b"\x89PNG"):
        return {"ok": False, "error": "screenshot_failed"}
    # Keep result payload bounded. The full file is retained locally for recovery.
    shot = OMEGA / "hakim-latest-screen.png"
    shot.write_bytes(data)
    os.chmod(shot, 0o600)
    if len(data) <= 1_500_000:
        return {"ok": True, "mime": "image/png", "png_b64": base64.b64encode(data).decode(), "sha256": hashlib.sha256(data).hexdigest()}
    return {"ok": True, "mime": "image/png", "local_path": str(shot), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "note": "image_retained_locally_payload_too_large"}


def notifications(cfg: dict) -> dict:
    if not adb_ok(cfg):
        return {"ok": False, "error": "adb_offline"}
    rc, out, err = adb(cfg, ["shell", "dumpsys", "notification", "--noredact"], timeout=20)
    if rc != 0:
        return {"ok": False, "error": "notification_dump_failed"}
    # Bound output and avoid exporting the entire system dump by default.
    lines = [ln for ln in out.splitlines() if "pkg=" in ln or "NotificationRecord" in ln or "android.title" in ln or "android.text" in ln]
    return {"ok": True, "text": "\n".join(lines[-400:])[:120000]}


def action(cfg: dict, payload: dict) -> dict:
    if not control_window_open():
        return {"ok": False, "error": "local_control_window_closed"}
    if not adb_ok(cfg):
        return {"ok": False, "error": "adb_offline"}
    kind = str(payload.get("type", ""))
    cmd: list[str]
    if kind == "tap":
        x, y = int(payload["x"]), int(payload["y"])
        if not (0 <= x <= 10000 and 0 <= y <= 10000): raise ValueError("bad_coordinates")
        cmd = ["shell", "input", "tap", str(x), str(y)]
    elif kind == "swipe":
        x1, y1, x2, y2 = (int(payload[k]) for k in ("x1", "y1", "x2", "y2"))
        duration = int(payload.get("duration_ms", 350))
        if not all(0 <= n <= 10000 for n in (x1, y1, x2, y2)) or not 50 <= duration <= 5000: raise ValueError("bad_swipe")
        cmd = ["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)]
    elif kind == "text":
        text = str(payload.get("text", ""))
        if not text or len(text) > 1000: raise ValueError("bad_text")
        # input text uses %s for spaces; reject shell metacharacters because no shell is needed.
        safe = text.replace("%", "%25").replace(" ", "%s")
        cmd = ["shell", "input", "text", safe]
    elif kind == "key":
        key = str(payload.get("key", "")).upper()
        allowed = {"BACK", "HOME", "ENTER", "TAB", "DEL", "ESCAPE", "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT"}
        if key not in allowed: raise ValueError("bad_key")
        cmd = ["shell", "input", "keyevent", f"KEYCODE_{key}"]
    else:
        raise ValueError("unsupported_action")
    rc, out, err = adb(cfg, cmd, timeout=10)
    return {"ok": rc == 0, "error": None if rc == 0 else "adb_action_failed", "detail": err[-500:] if rc else ""}


def launch(cfg: dict, payload: dict) -> dict:
    if not control_window_open():
        return {"ok": False, "error": "local_control_window_closed"}
    if not adb_ok(cfg):
        return {"ok": False, "error": "adb_offline"}
    package = str(payload.get("package", "")).strip()
    url = str(payload.get("url", "")).strip()
    if package:
        if not PKG.fullmatch(package): raise ValueError("bad_package")
        rc, out, err = adb(cfg, ["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"], timeout=15)
    elif url:
        if not (url.startswith("https://") or url.startswith("http://")) or len(url) > 2048: raise ValueError("bad_url")
        rc, out, err = adb(cfg, ["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url], timeout=15)
    else:
        raise ValueError("missing_launch_target")
    return {"ok": rc == 0, "error": None if rc == 0 else "launch_failed", "detail": (out + err)[-1000:]}


def execute(cfg: dict, op: str, payload: dict) -> dict:
    try:
        if op == "status": return status(cfg)
        if op == "ui": return ui(cfg)
        if op == "screenshot": return screenshot(cfg)
        if op == "notifications": return notifications(cfg)
        if op == "action": return action(cfg, payload)
        if op == "launch": return launch(cfg, payload)
        return {"ok": False, "error": "unsupported_operation"}
    except (KeyError, ValueError, TypeError) as e:
        return {"ok": False, "error": str(e)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "adb_timeout"}
    except Exception as e:
        return {"ok": False, "error": type(e).__name__}


def post_result(url: str, request_id: str, status_name: str, result: dict) -> None:
    body = json.dumps({"request_id": request_id, "status": status_name, "received_at_ms": now_ms(), "result": result}, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    with urllib.request.urlopen(req, timeout=25) as r:
        r.read(1024)


def handle_message(cfg: dict, raw_message: str) -> None:
    if not (8 <= len(raw_message) <= MAX_MESSAGE): return
    try:
        pad = "=" * (-len(raw_message) % 4)
        raw = base64.urlsafe_b64decode((raw_message + pad).encode()).decode("utf-8")
        env = json.loads(raw)
        request_id = str(env.get("request_id", ""))
        op = str(env.get("op", ""))
        expires = int(env.get("expires_at_ms", 0))
        if not REQUEST_ID.fullmatch(request_id) or op not in ALLOWED: return
        if not valid_signature(str(cfg["relay_key"]), env): return
        if expires <= now_ms():
            post_result(str(cfg["result_url"]), request_id, "expired", {"ok": False, "error": "request_expired"})
            return
        if not claim(request_id):
            post_result(str(cfg["result_url"]), request_id, "duplicate", {"ok": False, "error": "duplicate_request"})
            return
        payload = decode_payload(env)
        result = execute(cfg, op, payload)
        post_result(str(cfg["result_url"]), request_id, "ok" if result.get("ok") else "error", result)
    except Exception as e:
        log(f"message_error {type(e).__name__}")


def stream(cfg: dict) -> None:
    retry = 2
    url = f"https://ntfy.sh/{cfg['topic']}/json"
    while True:
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/x-ndjson", "User-Agent": "HAKIM-Termux-ADB/1"})
            with urllib.request.urlopen(req, timeout=90) as r:
                retry = 2
                for bline in r:
                    try:
                        event = json.loads(bline.decode("utf-8", "replace"))
                        if event.get("event") == "message":
                            handle_message(cfg, str(event.get("message", "")).strip())
                    except Exception as e:
                        log(f"event_error {type(e).__name__}")
        except KeyboardInterrupt:
            return
        except Exception as e:
            log(f"stream_error {type(e).__name__}; retry={retry}s")
            time.sleep(retry)
            retry = min(retry * 2, 60)


def main() -> int:
    cfg = load_json(CONFIG, None)
    if not isinstance(cfg, dict):
        print("ERROR: missing HAKIM Termux ADB configuration", file=sys.stderr)
        return 2
    for key in ("topic", "result_url", "relay_key", "adb_target"):
        if not cfg.get(key):
            print(f"ERROR: missing config key {key}", file=sys.stderr)
            return 2
    log("bridge_start")
    stream(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
