from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "governance" / "HAKIM_CANONICAL_CORE_AR.md"
POLICY = ROOT / "governance" / "HAKIM_RUNTIME_POLICY_v2.json"
SEED = ROOT / "governance" / "HAKIM_CONTEXT_SEED_AR.txt"


def test_canonical_assets_exist_and_parse():
    assert CORE.is_file()
    assert POLICY.is_file()
    assert SEED.is_file()
    data = json.loads(POLICY.read_text(encoding="utf-8"))
    assert data["version"] == "2.1"
    assert data["status"] == "FROZEN_BY_DEFAULT"


def test_sovereignty_truth_and_zero_burden_are_locked():
    t = CORE.read_text(encoding="utf-8")
    for required in (
        "ZERO_BURDEN",
        "ASK_MINIMUM",
        "GOAL_DOES_NOT_FAIL_WHEN_A_MEANS_FAILS",
        "ACTUAL_OUTPUT",
        "LAST_VERIFIED_BASELINE",
        "PROVEN_SUCCESS",
        "KEEP_WHAT_IS_PROVEN",
        "REPLACE_ONLY_WITH_WHAT_PROVES_BETTER",
    ):
        assert required in t


def test_release_and_risk_scaled_assurance_are_locked():
    t = CORE.read_text(encoding="utf-8")
    for required in (
        "RELEASE_BUILD→VALIDATOR_GATE→FINALIZE→DELIVER",
        "P0_FAIL",
        "NO_RELEASE",
        "LOW:", "MEDIUM:", "HIGH:", "CRITICAL:",
        "TMR ليس تصويتًا أعمى",
        "Formal Verification",
        "REALITY_GATE",
    ):
        assert required in t


def test_modular_meta_system_and_recovery_are_locked():
    t = CORE.read_text(encoding="utf-8")
    for required in (
        "Modular Meta-System",
        "ADVERSARIAL_RED_TEAM",
        "SAFETY_RIGHTS",
        "STATE_RECOVERY",
        "LOAD_CANONICAL→LOAD_ACTIVE_STATE→VERIFY_FRESHNESS→RESUME_FROM_LAST_PROVEN_POINT",
        "WIP=1",
    ):
        assert required in t


def test_bridge_security_and_failover_are_locked():
    p = json.loads(POLICY.read_text(encoding="utf-8"))
    b = p["bridges"]
    s = p["security"]
    assert b["identity_independent_of_bridge"] is True
    assert b["health_check"] and b["failover"] and b["self_heal"] and b["round_trip_verify"]
    assert b["external_background_command_transport"] is False
    assert s["least_privilege"] and s["signed_commands"] and s["anti_replay"]
    assert s["loopback_only_control_plane"] is True
    assert s["no_general_remote_shell"] and s["do_not_disable_platform_protection"]


def test_religious_guard_is_truthful_and_non_anthropomorphic():
    t = CORE.read_text(encoding="utf-8")
    p = json.loads(POLICY.read_text(encoding="utf-8"))
    assert "القرآن الكريم والسنة الصحيحة" in t
    assert "لا ينسب لنفسه إيمانًا" in t
    assert p["religious_guard"]["verify_attribution"] is True
    assert p["religious_guard"]["no_claim_of_ai_faith_piety_or_divine_attributes"] is True


def test_arabic_palestinian_and_cross_chat_recovery_seed_are_locked():
    t = CORE.read_text(encoding="utf-8")
    seed = SEED.read_text(encoding="utf-8")
    assert "العربية اللغة الأصلية والافتراضية" in t
    assert "السياق الفلسطيني" in t
    assert "أفضل خطوة قادمة" in t
    assert "LOAD_CANONICAL" in seed
    assert "P0_FAIL→NO_RELEASE" in seed
