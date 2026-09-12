#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import stat
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = "smileeyes1/SovereignAssistant"
STATUS_URL = "http://127.0.0.1:47651/v1/status"
DEFAULT_TIMEOUT = 5.0

REQUIRED_RELEASE_ASSETS = {
    "hakim-companion-unsigned.apk",
    "hakim-companion-unsigned.apk.sha256",
    "hakim-companion-build-manifest.json",
}

PHYSICAL_MATRIX = [
    "DEEP_LINK_PAIR_CONFIG",
    "ENCRYPTED_SIGNED_STATUS_ROUND_TRIP",
    "PLAINTEXT_CARRIER_REJECTION",
    "BAD_GCM_TAG_REJECTION",
    "BAD_HMAC_REJECTION",
    "REPLAY_REJECTION",
    "EXPIRY_REJECTION",
    "STATUS_UI_SCREENSHOT_NOTIFICATIONS",
    "FINANCIAL_SAFE_MODE_ONE_TAP_ISOLATION",
    "TARGET_FINANCIAL_APPS_COMPATIBILITY_IN_SAFE_MODE",
    "LOCAL_APPROVAL_FOR_MUTATION",
    "SCREEN_OFF_BACKGROUND",
    "RECONNECT",
    "REBOOT_CONTINUITY",
    "OFFLINE_RECOVERY",
    "IDEMPOTENCY_LKG",
    "BACKUP_RESTORE_CONTAINMENT",
]


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_request(
    url: str,
    *,
    token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[int, dict[str, Any]]:
    headers = {"Accept": "application/vnd.github+json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            return response.status, json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = {"error": f"http_{exc.code}"}
        return exc.code, payload


def text_request(url: str, *, timeout: float = DEFAULT_TIMEOUT) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"Accept": "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def check_token_file(token_file: Path) -> tuple[str | None, list[Check]]:
    checks: list[Check] = []
    if not token_file.is_file():
        return None, [Check("PAIR_TOKEN_PRESENT", "FAIL", "companion.token غير موجود")]
    token = token_file.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        return None, [Check("PAIR_TOKEN_PRESENT", "FAIL", "رمز الاقتران قصير أو فارغ")]

    checks.append(Check("PAIR_TOKEN_PRESENT", "PASS", "رمز الاقتران موجود محليًا ولم يُسجّل في الدليل"))
    mode = stat.S_IMODE(token_file.stat().st_mode)
    if mode & 0o077:
        checks.append(Check("PAIR_TOKEN_PRIVATE_MODE", "FAIL", f"صلاحيات الملف واسعة: {oct(mode)}"))
    else:
        checks.append(Check("PAIR_TOKEN_PRIVATE_MODE", "PASS", f"صلاحيات الملف: {oct(mode)}"))
    return token, checks


def check_local_status(token: str) -> tuple[dict[str, Any] | None, list[Check]]:
    checks: list[Check] = []
    try:
        code, payload = json_request(STATUS_URL, token=token)
    except Exception as exc:
        return None, [Check("LOCAL_STATUS_AUTHENTICATED", "FAIL", exc.__class__.__name__)]

    if code != 200:
        return None, [Check("LOCAL_STATUS_AUTHENTICATED", "FAIL", f"HTTP {code}")]

    checks.append(Check("LOCAL_STATUS_AUTHENTICATED", "PASS", "حلقة التحكم المحلية استجابت بالرمز المحلي"))
    required = {
        "loopback_only": True,
        "control_server_listening": True,
        "persistent_model_allowed": False,
        "evidence_state": "NOT_PROVEN",
    }
    for key, expected in required.items():
        actual = payload.get(key)
        checks.append(
            Check(
                f"STATUS_{key.upper()}",
                "PASS" if actual == expected else "FAIL",
                f"expected={expected!r}; actual={actual!r}",
            )
        )

    try:
        wrong_code, _ = json_request(STATUS_URL, token="x" * 48)
        checks.append(
            Check(
                "WRONG_TOKEN_REJECTED",
                "PASS" if wrong_code == 401 else "FAIL",
                f"HTTP {wrong_code}",
            )
        )
    except Exception as exc:
        checks.append(Check("WRONG_TOKEN_REJECTED", "FAIL", exc.__class__.__name__))

    return payload, checks


def latest_release() -> tuple[dict[str, Any] | None, list[Check]]:
    checks: list[Check] = []
    url = f"https://api.github.com/repos/{REPO}/releases/latest"
    try:
        code, release = json_request(url, timeout=10.0)
    except Exception as exc:
        return None, [Check("LATEST_RELEASE_FETCH", "FAIL", exc.__class__.__name__)]
    if code != 200:
        return None, [Check("LATEST_RELEASE_FETCH", "FAIL", f"HTTP {code}")]
    checks.append(Check("LATEST_RELEASE_FETCH", "PASS", str(release.get("tag_name", ""))))

    assets = {a.get("name"): a for a in release.get("assets", [])}
    missing = sorted(REQUIRED_RELEASE_ASSETS - set(assets))
    if missing:
        checks.append(Check("RELEASE_REQUIRED_ASSETS", "FAIL", "missing=" + ",".join(missing)))
        return release, checks
    checks.append(Check("RELEASE_REQUIRED_ASSETS", "PASS", "apk+sha256+manifest"))

    manifest_asset = assets["hakim-companion-build-manifest.json"]
    manifest_url = manifest_asset.get("browser_download_url")
    if not manifest_url:
        checks.append(Check("RELEASE_MANIFEST_FETCH", "FAIL", "manifest URL missing"))
        return release, checks
    try:
        manifest_code, manifest_text = text_request(manifest_url, timeout=10.0)
        manifest = json.loads(manifest_text) if manifest_code == 200 else {}
    except Exception as exc:
        checks.append(Check("RELEASE_MANIFEST_FETCH", "FAIL", exc.__class__.__name__))
        return release, checks

    if manifest_code != 200:
        checks.append(Check("RELEASE_MANIFEST_FETCH", "FAIL", f"HTTP {manifest_code}"))
        return release, checks
    checks.append(Check("RELEASE_MANIFEST_FETCH", "PASS", "manifest downloaded"))

    target = str(release.get("target_commitish", ""))
    source = str(manifest.get("source_commit_sha", ""))
    checks.append(
        Check(
            "RELEASE_SOURCE_COMMIT_MATCH",
            "PASS" if source == target and len(source) == 40 else "FAIL",
            f"release={target}; manifest={source}",
        )
    )

    apk_asset = assets["hakim-companion-unsigned.apk"]
    api_digest = str(apk_asset.get("digest") or "")
    manifest_digest = str(manifest.get("apk_sha256") or "")
    expected_api_digest = f"sha256:{manifest_digest}" if manifest_digest else ""
    checks.append(
        Check(
            "RELEASE_APK_DIGEST_MATCH",
            "PASS" if api_digest == expected_api_digest and len(manifest_digest) == 64 else "FAIL",
            f"asset={api_digest}; manifest=sha256:{manifest_digest}",
        )
    )

    checks.append(
        Check(
            "RELEASE_FIELD_CLAIM_CLOSED",
            "PASS" if manifest.get("field_verification") == "NOT_PROVEN_BY_BUILD" else "FAIL",
            str(manifest.get("field_verification")),
        )
    )
    return {"release": release, "manifest": manifest}, checks


def local_android_tree(root: Path) -> tuple[str | None, Check]:
    if not (root / ".git").exists():
        return None, Check("LOCAL_ANDROID_TREE_MATCH", "NOT_PROVEN", "لا توجد نسخة Git محلية للمقارنة")
    try:
        value = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD:android/hakim-companion"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
        return value, Check("LOCAL_ANDROID_TREE_READ", "PASS", value)
    except Exception as exc:
        return None, Check("LOCAL_ANDROID_TREE_READ", "NOT_PROVEN", exc.__class__.__name__)


def summarize(checks: list[Check]) -> str:
    if any(c.status == "FAIL" for c in checks):
        return "FAIL"
    return "PRE_FIELD_PASS"


def main() -> int:
    home = Path(os.environ.get("HOME", str(Path.home())))
    root = Path(os.environ.get("OMEGA_ROOT", str(home / "hakim-workspace")))
    out = Path(os.environ.get("HAKIM_FIELD_EVIDENCE", str(home / ".omega" / "physical-field-preflight.json")))
    token_file = Path(os.environ.get("HAKIM_COMPANION_TOKEN_FILE", str(home / ".omega" / "companion.token")))

    checks: list[Check] = []
    token, token_checks = check_token_file(token_file)
    checks.extend(token_checks)

    local_status: dict[str, Any] | None = None
    if token is not None and not any(c.status == "FAIL" for c in token_checks):
        local_status, local_checks = check_local_status(token)
        checks.extend(local_checks)
    else:
        checks.append(Check("LOCAL_STATUS_AUTHENTICATED", "NOT_PROVEN", "الاقتران المحلي غير جاهز"))

    release_data, release_checks = latest_release()
    checks.extend(release_checks)

    tree, tree_check = local_android_tree(root)
    checks.append(tree_check)
    if tree and release_data and isinstance(release_data.get("manifest"), dict):
        expected_tree = str(release_data["manifest"].get("android_tree_sha", ""))
        checks.append(
            Check(
                "LOCAL_ANDROID_TREE_MATCH",
                "PASS" if tree == expected_tree else "NOT_PROVEN",
                f"local={tree}; release={expected_tree}",
            )
        )

    automated_pass = summarize(checks)
    proven_items: list[str] = []
    if local_status is not None and all(
        c.status == "PASS"
        for c in checks
        if c.name in {
            "LOCAL_STATUS_AUTHENTICATED",
            "STATUS_LOOPBACK_ONLY",
            "STATUS_CONTROL_SERVER_LISTENING",
            "WRONG_TOKEN_REJECTED",
        }
    ):
        proven_items.append("DEEP_LINK_PAIR_CONFIG")

    pending = [item for item in PHYSICAL_MATRIX if item not in proven_items]
    payload = {
        "schema_version": "1.0",
        "captured_at": utc_now(),
        "status": automated_pass,
        "field_verified": False,
        "promotion_allowed": False,
        "reason": (
            "الفحص الآلي السابق للميدان لا يساوي تحققًا ميدانيًا كاملًا؛ "
            "لا تُرفع FIELD_VERIFIED حتى تمر مصفوفة الهاتف الفعلية كلها."
        ),
        "checks": [c.as_dict() for c in checks],
        "physical_matrix": {
            "required": PHYSICAL_MATRIX,
            "preflight_proven": proven_items,
            "pending": pending,
        },
        "secrets_recorded": False,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_name("." + out.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, out)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if automated_pass == "PRE_FIELD_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
