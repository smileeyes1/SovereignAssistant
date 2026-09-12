import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOV = ROOT / "governance"


def _json(name):
    return json.loads((GOV / name).read_text(encoding="utf-8"))


def test_nstar_is_active_and_machine_encoded():
    active = _json("HAKIM_ACTIVE.json")
    policy = _json("HAKIM_RUNTIME_POLICY_v2.json")
    assert active["version"] == "2.1"
    assert active["adaptive_intelligence_spec"] == "governance/HAKIM_NSTAR_SPEC_AR.md"
    assert active["meta_method_spec"] == "governance/HAKIM_META_METHOD_AR.md"
    assert active["phone_sovereign_constraints"] == "governance/HAKIM_PHONE_SOVEREIGN_CONSTRAINTS.json"
    assert active["active_state"] == "governance/HAKIM_ACTIVE_STATE.json"
    nstar = policy["adaptive_intelligence"]
    assert nstar["name"] == "NSTAR"
    assert nstar["enabled"] is True
    assert nstar["dynamic_depth"] is True
    assert "HOW_ITSELF" in nstar["apply_to"]
    assert "MATERIAL_NET_GAIN" in nstar["increase_depth_while"]


def test_restore_chain_is_complete_and_files_exist():
    active = _json("HAKIM_ACTIVE.json")
    expected = [
        "LOAD_ACTIVE_POINTER", "LOAD_CANONICAL", "LOAD_NSTAR_SPEC",
        "LOAD_META_METHOD_SPEC", "LOAD_PHONE_SOVEREIGN_CONSTRAINTS",
        "LOAD_RUNTIME_POLICY", "LOAD_BRIDGE_POLICY", "LOAD_ACTIVE_STATE",
        "LOAD_BRIDGE_HEALTH", "VERIFY_FRESHNESS", "RESUME_FROM_LAST_PROVEN_POINT",
    ]
    assert active["restore_sequence"] == expected
    assert expected.index("LOAD_NSTAR_SPEC") < expected.index("LOAD_META_METHOD_SPEC")
    assert expected.index("LOAD_META_METHOD_SPEC") < expected.index("LOAD_PHONE_SOVEREIGN_CONSTRAINTS")
    assert expected.index("LOAD_PHONE_SOVEREIGN_CONSTRAINTS") < expected.index("LOAD_RUNTIME_POLICY")
    assert expected.index("LOAD_PHONE_SOVEREIGN_CONSTRAINTS") < expected.index("LOAD_BRIDGE_POLICY")
    for key in (
        "core", "adaptive_intelligence_spec", "meta_method_spec",
        "phone_sovereign_constraints", "runtime_policy", "bridge_policy",
        "active_state", "context_seed",
    ):
        assert (ROOT / active[key]).is_file(), key


def test_seed_and_spec_preserve_nstar_and_safe_autonomy():
    seed = (GOV / "HAKIM_CONTEXT_SEED_AR.txt").read_text(encoding="utf-8")
    spec = (GOV / "HAKIM_NSTAR_SPEC_AR.md").read_text(encoding="utf-8")
    assert "ن★" in seed and "ن★" in spec
    assert "AUTONOMY_DEFAULT=ON" in seed
    assert "ACTUAL_OUTPUT" in seed
    assert "التفويض العام لا يلغي" in seed
    assert "لا يُعلن COMPLETE" in spec


def test_phone_sovereign_constraints_are_p0_and_stronger_than_generic_autonomy():
    c = _json("HAKIM_PHONE_SOVEREIGN_CONSTRAINTS.json")
    assert c["priority"] == "P0"
    assert c["constraints"]["developer_options_normal_operation"] == "MUST_REMAIN_OFF"
    assert c["constraints"]["wireless_debugging_normal_operation"] == "MUST_REMAIN_OFF"
    assert c["precedence"]["generic_autonomy_cannot_override"] is True
    assert c["precedence"]["only_later_explicit_user_instruction_may_change"] is True


def test_governance_files_do_not_contain_operational_secrets():
    forbidden = (
        "relay_hmac_key",
        "result_webhook",
        "hook.eu1.make.com/",
        "BEGIN PRIVATE KEY",
        "auth_token",
    )
    for path in GOV.iterdir():
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in forbidden:
            assert token not in text, f"{token} leaked in {path.name}"
