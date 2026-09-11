from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_WORKFLOW = ROOT / ".github" / "workflows" / "hakim-phone-relay.yml"
DESIGN = ROOT / "docs" / "HAKIM_LIVE_BRIDGE_DESIGN.md"


def test_public_issue_comment_phone_relay_is_retired():
    """لا يجوز إعادة قناة أوامر الهاتف عبر تعليقات مستودع عام."""
    assert not PUBLIC_WORKFLOW.exists()


def test_live_bridge_design_uses_private_make_relay_and_outbound_phone_transport():
    t = DESIGN.read_text(encoding="utf-8")
    assert "ناقل الأوامر النشط في Make" in t
    assert "HTTPS صادر من الهاتف" in t
    assert "HMAC-SHA256" in t
    assert "لا يُسمح بأمر عام أو shell بعيد" in t


def test_no_public_relay_topic_is_baked_into_live_bridge_design():
    t = DESIGN.read_text(encoding="utf-8")
    assert "ntfy.sh/hakim-" not in t
    assert "HAKIM_RELAY " not in t
