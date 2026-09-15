#!/usr/bin/env python3
"""Generate a private HAKIM direct-relay pairing page.

The Android direct relay contract is topic-to-topic.  It intentionally does not
accept a legacy result_url webhook.  Keeping the generator beside the runtime
prevents a pairing artifact from silently drifting away from MainActivity.
"""
from __future__ import annotations

import argparse
import html
import re
from pathlib import Path
from urllib.parse import urlencode

TOPIC_RE = re.compile(r"^[A-Za-z0-9_-]{20,120}$")
RELAY_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{40,100}$")
PACKAGE_ID = "org.hakim.omega.companion"
DEFAULT_RELAY_BASE = "https://ntfy.sh"


def validate(*, token: str, relay_topic: str, result_topic: str, relay_key: str) -> None:
    if not 32 <= len(token) <= 256:
        raise ValueError("token length must be 32..256")
    if not TOPIC_RE.fullmatch(relay_topic):
        raise ValueError("invalid relay_topic")
    if not TOPIC_RE.fullmatch(result_topic):
        raise ValueError("invalid result_topic")
    if relay_topic == result_topic:
        raise ValueError("command and result topics must be distinct")
    if not RELAY_KEY_RE.fullmatch(relay_key):
        raise ValueError("invalid relay_key")


def pairing_urls(*, token: str, relay_topic: str, result_topic: str, relay_key: str,
                 relay_base: str = DEFAULT_RELAY_BASE) -> tuple[str, str]:
    validate(token=token, relay_topic=relay_topic, result_topic=result_topic, relay_key=relay_key)
    if not relay_base.startswith("https://"):
        raise ValueError("relay_base must use https")
    query = urlencode({
        "token": token,
        "relay_topic": relay_topic,
        "result_topic": result_topic,
        "relay_key": relay_key,
        "relay_base": relay_base.rstrip("/"),
    })
    pair = f"hakim://pair?{query}"
    intent = f"intent://pair?{query}#Intent;scheme=hakim;package={PACKAGE_ID};end"
    return pair, intent


def render_page(*, token: str, relay_topic: str, result_topic: str, relay_key: str,
                relay_base: str = DEFAULT_RELAY_BASE) -> str:
    pair, intent = pairing_urls(
        token=token,
        relay_topic=relay_topic,
        result_topic=result_topic,
        relay_key=relay_key,
        relay_base=relay_base,
    )
    return f'''<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow,noarchive">
<title>ربط حكيم المباشر</title></head><body>
<h1>ربط حكيم المباشر</h1>
<p>هذا الملف خاص بجهازك. لا تشاركه لأنه يحتوي إعداد قناة التحكم المشفّرة.</p>
<a id="go" href="{html.escape(intent, quote=True)}">تهيئة حكيم الآن</a>
<script>
const pair={pair!r};
document.getElementById('go').addEventListener('click',()=>{{setTimeout(()=>{{window.location.href=pair;}},900);}});
</script>
</body></html>'''


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--token", required=True)
    p.add_argument("--relay-topic", required=True)
    p.add_argument("--result-topic", required=True)
    p.add_argument("--relay-key", required=True)
    p.add_argument("--relay-base", default=DEFAULT_RELAY_BASE)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    page = render_page(
        token=args.token,
        relay_topic=args.relay_topic,
        result_topic=args.result_topic,
        relay_key=args.relay_key,
        relay_base=args.relay_base,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(page, encoding="utf-8")
    args.output.chmod(0o600)
    print(f"PAIRING_FILE_WRITTEN={args.output}")
    print("PAIRING_CONTRACT=HC1_DIRECT_RESULT_TOPIC")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
