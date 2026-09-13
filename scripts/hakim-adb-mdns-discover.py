#!/data/data/com.termux/files/usr/bin/python
import argparse
import ipaddress
import socket
import struct
import sys
import time

MDNS_ADDR = ("224.0.0.251", 5353)
QTYPE_PTR = 12
QTYPE_A = 1
QTYPE_AAAA = 28
QTYPE_SRV = 33


def enc_name(name: str) -> bytes:
    out = bytearray()
    for label in name.rstrip(".").split("."):
        b = label.encode("utf-8")
        if len(b) > 63:
            raise ValueError("DNS label too long")
        out.append(len(b))
        out.extend(b)
    out.append(0)
    return bytes(out)


def dec_name(data: bytes, off: int, depth: int = 0):
    if depth > 20:
        raise ValueError("compression loop")
    labels = []
    jumped = False
    end = off
    while True:
        if off >= len(data):
            raise ValueError("truncated name")
        n = data[off]
        if n == 0:
            off += 1
            if not jumped:
                end = off
            break
        if n & 0xC0 == 0xC0:
            if off + 1 >= len(data):
                raise ValueError("truncated pointer")
            ptr = ((n & 0x3F) << 8) | data[off + 1]
            sub, _ = dec_name(data, ptr, depth + 1)
            labels.append(sub)
            off += 2
            if not jumped:
                end = off
            jumped = True
            break
        off += 1
        if off + n > len(data):
            raise ValueError("truncated label")
        labels.append(data[off:off+n].decode("utf-8", "replace"))
        off += n
        if not jumped:
            end = off
    return ".".join(x for x in labels if x), end


def parse_packet(data: bytes):
    if len(data) < 12:
        return []
    _id, _flags, qd, an, ns, ar = struct.unpack("!HHHHHH", data[:12])
    off = 12
    for _ in range(qd):
        _, off = dec_name(data, off)
        off += 4
        if off > len(data):
            return []
    recs = []
    for _ in range(an + ns + ar):
        try:
            name, off = dec_name(data, off)
            rtype, rclass, ttl, rdlen = struct.unpack("!HHIH", data[off:off+10])
            off += 10
            rstart = off
            rend = off + rdlen
            if rend > len(data):
                break
            value = None
            if rtype == QTYPE_PTR:
                value, _ = dec_name(data, rstart)
            elif rtype == QTYPE_SRV and rdlen >= 6:
                _pri, _weight, port = struct.unpack("!HHH", data[rstart:rstart+6])
                target, _ = dec_name(data, rstart + 6)
                value = (target, port)
            elif rtype == QTYPE_A and rdlen == 4:
                value = socket.inet_ntop(socket.AF_INET, data[rstart:rend])
            elif rtype == QTYPE_AAAA and rdlen == 16:
                value = socket.inet_ntop(socket.AF_INET6, data[rstart:rend])
            recs.append((name.rstrip("."), rtype, value))
            off = rend
        except Exception:
            break
    return recs


def discover(service: str, timeout: float):
    service_name = f"_adb-tls-{service}._tcp.local"
    packet = struct.pack("!HHHHHH", 0, 0, 1, 0, 0, 0) + enc_name(service_name) + struct.pack("!HH", QTYPE_PTR, 1)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        sock.settimeout(0.35)
        sock.sendto(packet, MDNS_ADDR)
        deadline = time.monotonic() + timeout
        srv = {}
        addrs = {}
        while time.monotonic() < deadline:
            try:
                data, src = sock.recvfrom(65535)
            except socket.timeout:
                continue
            for name, rtype, value in parse_packet(data):
                key = name.lower()
                if rtype == QTYPE_SRV and value:
                    srv[key] = value
                elif rtype in (QTYPE_A, QTYPE_AAAA) and value:
                    addrs.setdefault(key, []).append(value)
            for _instance, (target, port) in list(srv.items()):
                candidates = addrs.get(target.lower(), [])
                if not candidates and src and src[0]:
                    candidates = [src[0]]
                for addr in candidates:
                    try:
                        ip = ipaddress.ip_address(addr.split("%", 1)[0])
                    except ValueError:
                        continue
                    if ip.is_loopback or ip.is_unspecified or ip.is_multicast:
                        continue
                    if ip.version == 6:
                        print(f"[{addr}]:{port}")
                    else:
                        print(f"{addr}:{port}")
                    return 0
        return 1
    finally:
        sock.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--service", choices=("connect", "pairing"), default="connect")
    ap.add_argument("--timeout", type=float, default=2.5)
    args = ap.parse_args()
    sys.exit(discover(args.service, max(0.5, args.timeout)))


if __name__ == "__main__":
    main()
