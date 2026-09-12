import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOV = ROOT / "governance"


def _json(name):
    return json.loads((GOV / name).read_text(encoding="utf-8"))


def test_nstar_is_active_and_machine_encoded():
    active = _json("HAKIM_ACTIVE.json")
    policy = _json("HAKIM_RUNTIME_POLICY_v2.json")
    assert active["version"] == "2.2"
    assert active["adaptive_intelligence_spec"] == "governance/HAKIM_NSTAR_SPEC_AR.md"
    assert active["nstar_governing_constitution"] == "governance/HAKIM_NSTAR_GOVERNING_CONSTITUTION_AR.md"
    assert active["intelligence_fabric_spec"] == "governance/HAKIM_INTELLIGENCE_FABRIC_AR.md"
    assert active["intelligence_matrix"] == "governance/HAKIM_INTELLIGENCE_MATRIX.json"
    assert active["meta_method_spec"] == "governance/HAKIM_META_METHOD_AR.md"
    assert active["value_gates_spec"] == "governance/HAKIM_VALUE_GATES_AR.md"
    assert active["continuity_shield_spec"] == "governance/HAKIM_CONTINUITY_SHIELD_AR.md"
    assert active["continuity_shield_policy"] == "governance/HAKIM_CONTINUITY_SHIELD.json"
    assert active["capability_transitions"] == "governance/HAKIM_CAPABILITY_TRANSITIONS.json"
    assert active["phone_sovereign_constraints"] == "governance/HAKIM_PHONE_SOVEREIGN_CONSTRAINTS.json"
    assert active["active_state"] == "governance/HAKIM_ACTIVE_STATE.json"
    assert "CONTINUITY_SHIELD_PASS" in active["promotion_gate"]
    nstar = policy["adaptive_intelligence"]
    assert nstar["name"] == "NSTAR"
    assert nstar["enabled"] is True
    assert nstar["dynamic_depth"] is True
    assert "HOW_ITSELF" in nstar["apply_to"]
    assert "MATERIAL_NET_GAIN" in nstar["increase_depth_while"]
    fabric = policy["intelligence_fabric"]
    assert fabric["enabled"] is True
    assert fabric["nstar_controls_depth"] is True
    assert fabric["method_claim_requires_execution_evidence"] is True


def test_restore_chain_is_complete_and_files_exist():
    active = _json("HAKIM_ACTIVE.json")
    expected = [
        "LOAD_ACTIVE_POINTER", "LOAD_CANONICAL", "LOAD_NSTAR_SPEC",
        "LOAD_NSTAR_GOVERNING_CONSTITUTION", "LOAD_INTELLIGENCE_FABRIC_SPEC",
        "LOAD_INTELLIGENCE_MATRIX", "LOAD_META_METHOD_SPEC", "LOAD_VALUE_GATES_SPEC",
        "LOAD_CONTINUITY_SHIELD_SPEC", "LOAD_CONTINUITY_SHIELD_POLICY",
        "LOAD_CAPABILITY_TRANSITIONS", "LOAD_PHONE_SOVEREIGN_CONSTRAINTS",
        "LOAD_RUNTIME_POLICY", "LOAD_BRIDGE_POLICY", "LOAD_ACTIVE_STATE",
        "LOAD_BRIDGE_HEALTH", "VERIFY_FRESHNESS", "RESUME_FROM_LAST_PROVEN_POINT",
    ]
    assert active["restore_sequence"] == expected
    assert expected.index("LOAD_NSTAR_SPEC") < expected.index("LOAD_NSTAR_GOVERNING_CONSTITUTION")
    assert expected.index("LOAD_NSTAR_GOVERNING_CONSTITUTION") < expected.index("LOAD_INTELLIGENCE_FABRIC_SPEC")
    assert expected.index("LOAD_INTELLIGENCE_FABRIC_SPEC") < expected.index("LOAD_INTELLIGENCE_MATRIX")
    assert expected.index("LOAD_INTELLIGENCE_MATRIX") < expected.index("LOAD_META_METHOD_SPEC")
    assert expected.index("LOAD_META_METHOD_SPEC") < expected.index("LOAD_VALUE_GATES_SPEC")
    assert expected.index("LOAD_VALUE_GATES_SPEC") < expected.index("LOAD_CONTINUITY_SHIELD_SPEC")
    assert expected.index("LOAD_CONTINUITY_SHIELD_SPEC") < expected.index("LOAD_CONTINUITY_SHIELD_POLICY")
    assert expected.index("LOAD_CONTINUITY_SHIELD_POLICY") < expected.index("LOAD_CAPABILITY_TRANSITIONS")
    assert expected.index("LOAD_CAPABILITY_TRANSITIONS") < expected.index("LOAD_PHONE_SOVEREIGN_CONSTRAINTS")
    for key in (
        "core", "adaptive_intelligence_spec", "nstar_governing_constitution",
        "intelligence_fabric_spec", "intelligence_matrix", "meta_method_spec",
        "value_gates_spec", "continuity_shield_spec", "continuity_shield_policy",
        "capability_transitions", "phone_sovereign_constraints", "runtime_policy", "bridge_policy",
        "active_state", "context_seed",
    ):
        assert (ROOT / active[key]).is_file(), key


def test_seed_and_spec_preserve_nstar_and_safe_autonomy():
    seed = (GOV / "HAKIM_CONTEXT_SEED_AR.txt").read_text(encoding="utf-8")
    spec = (GOV / "HAKIM_NSTAR_SPEC_AR.md").read_text(encoding="utf-8")
    assert "ن★" in seed and "ن★" in spec
    assert "نسيج الذكاء الشامل" in seed
    assert "AUTONOMY_DEFAULT=ON" in seed
    assert "ACTUAL_OUTPUT" in seed
    assert "التفويض العام لا يلغي" in seed
    assert "لا يُعلن COMPLETE" in spec


def test_phone_sovereign_constraints_are_p0_and_stronger_than_generic_autonomy():
    c = _json("HAKIM_PHONE_SOVEREIGN_CONSTRAINTS.json")
    assert c["priority"] == "P0"
    constraints = c["constraints"]
    assert constraints["developer_options_normal_operation"] == "MUST_REMAIN_OFF"
    assert constraints["wireless_debugging_normal_operation"] == "MUST_REMAIN_OFF"
    assert constraints["normal_phone_path"] == "ANDROID_COMPANION_SOVEREIGN_LOCAL_OWNED_BROWSER"
    assert constraints["external_background_command_transport"] == "FORBIDDEN_IN_NORMAL_OPERATION"
    assert constraints["accessibility_service_required"] is False
    assert constraints["notification_listener_required"] is False
    assert constraints["platform_protection_bypass"] is False
    assert c["precedence"]["generic_autonomy_cannot_override"] is True
    assert c["precedence"]["optimization_cannot_override"] is True
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
