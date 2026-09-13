#!/data/data/com.termux/files/usr/bin/python
import concurrent.futures
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

OMEGA = Path.home() / ".omega"
CFG = OMEGA / "hakim-termux-adb.json"
SUP = OMEGA / "bin" / "hakim-multibridge-supervisor"


def run(args, timeout=8):
    try:
        return subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    except Exception:
        return None


def adb_online(target):
    if not target:
        return False
    p = run(["adb", "-s", target, "get-state"], timeout=4)
    return bool(p and p.stdout.strip() == "device")


def connect(target):
    if not target:
        return False
    run(["adb", "connect", target], timeout=5)
    return adb_online(target)


def load_cfg():
    try:
        return json.loads(CFG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_target(target):
    OMEGA.mkdir(parents=True, exist_ok=True)
    d = load_cfg()
    d["adb_target"] = target
    d["transport"] = "termux-wireless-adb"
    d["apk_required"] = False
    d["public_command_transport"] = False
    fd, tmp = tempfile.mkstemp(prefix=".hakim-cfg-", dir=str(OMEGA))
    os.close(fd)
    Path(tmp).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, CFG)


def current_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return ""
    finally:
        s.close()


def mdns_targets():
    p = run(["adb", "mdns", "services"], timeout=5)
    if not p:
        return []
    out = []
    for line in p.stdout.splitlines():
        if "_adb-tls-connect._tcp" not in line:
            continue
        m = re.search(r"([0-9a-fA-F:.]+:\d{2,5})\s*$", line)
        if m:
            out.append(m.group(1))
    return list(dict.fromkeys(out))


def listening_ports():
    p = run(["ss", "-ltnH"], timeout=5)
    if not p:
        return []
    ports = []
    for line in p.stdout.splitlines():
        for m in re.finditer(r":(\d{2,5})(?:\s|$)", line):
            v = int(m.group(1))
            if 1024 < v < 65536:
                ports.append(v)
    return list(dict.fromkeys(ports))


def port_open(ip, port):
    s = socket.socket()
    s.settimeout(0.035)
    try:
        return port if s.connect_ex((ip, port)) == 0 else None
    except Exception:
        return None
    finally:
        s.close()


def scan_ports(ip):
    # Wireless ADB commonly chooses a high ephemeral port. This scan runs only
    # after saved-target, mDNS, and local-listener discovery have all failed.
    with concurrent.futures.ThreadPoolExecutor(max_workers=320) as ex:
        return [p for p in ex.map(lambda x: port_open(ip, x), range(20000, 60001)) if p]


def restart_supervisor():
    if not SUP.exists():
        return
    run(["tmux", "kill-session", "-t", "hakim-multibridge-supervisor"], timeout=3)
    run(["tmux", "new-session", "-d", "-s", "hakim-multibridge-supervisor", str(SUP)], timeout=4)


run(["adb", "start-server"], timeout=5)

cfg = load_cfg()
saved = str(cfg.get("adb_target", "")).strip()
if adb_online(saved) or connect(saved):
    save_target(saved)
    restart_supervisor()
    print("HAKIM_LOCAL_ADB_RECOVER=PASS")
    print("TARGET=" + saved)
    raise SystemExit(0)

for target in mdns_targets():
    if connect(target):
        save_target(target)
        restart_supervisor()
        print("HAKIM_LOCAL_ADB_RECOVER=PASS")
        print("TARGET=" + target)
        raise SystemExit(0)

ip = current_ip()
if not ip:
    print("HAKIM_LOCAL_ADB_RECOVER=NO_IP")
    raise SystemExit(2)

tried = set()
for port in listening_ports():
    target = f"{ip}:{port}"
    tried.add(port)
    if connect(target):
        save_target(target)
        restart_supervisor()
        print("HAKIM_LOCAL_ADB_RECOVER=PASS")
        print("TARGET=" + target)
        raise SystemExit(0)

for port in scan_ports(ip):
    if port in tried:
        continue
    target = f"{ip}:{port}"
    if connect(target):
        save_target(target)
        restart_supervisor()
        print("HAKIM_LOCAL_ADB_RECOVER=PASS")
        print("TARGET=" + target)
        raise SystemExit(0)

print("HAKIM_LOCAL_ADB_RECOVER=PAIRING_MAY_BE_REQUIRED")
raise SystemExit(8)
