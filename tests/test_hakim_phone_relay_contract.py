from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_WORKFLOW = ROOT / ".github" / "workflows" / "hakim-phone-relay.yml"
DESIGN = ROOT / "docs" / "HAKIM_LIVE_BRIDGE_DESIGN.md"


def test_public_issue_comment_phone_relay_is_retired():
    assert not PUBLIC_WORKFLOW.exists()


def test_live_bridge_design_is_sovereign_local_and_provider_independent():
    t = DESIGN.read_text(encoding="utf-8")
    assert "التشغيل العادي محلي أولًا" in t
    assert "لا يحتاج التشغيل العادي إلى Make أو TinyFish أو ntfy أو GitHub Relay أو مفتاح API مدفوع" in t
    assert "hakim://task" in t
    assert "HMAC-SHA256" in t
    assert "لا يوجد shell عام" in t
    assert "field_verified=false" in t


def test_no_external_relay_configuration_is_baked_into_live_bridge_design():
    t = DESIGN.read_text(encoding="utf-8")
    assert "ntfy.sh/hakim-" not in t
    assert "HAKIM_RELAY" not in t
    assert "hook.eu1.make.com" not in t
