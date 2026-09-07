from pathlib import Path
import re


def test_hakim_state_capsule_does_not_embed_repository_commit_sha():
    text = Path("docs/HAKIM_STATE_CAPSULE.md").read_text(encoding="utf-8")
    assert not re.search(r"\b[0-9a-f]{40}\b", text, flags=re.IGNORECASE)
    assert "resolve live `main` at recovery time" in text
    assert "Never update this file merely to chase a new repository SHA" in text


def test_hakim_state_capsule_preserves_field_evidence_boundary():
    text = Path("docs/HAKIM_STATE_CAPSULE.md").read_text(encoding="utf-8")
    assert "repository/CI/runtime only" in text
    assert "never implies Android Companion field qualification" in text
    assert "no resident local model" in text
    assert "Remote Desktop Commander remains optional maintenance only" in text
