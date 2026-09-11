from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "hakim-phone-relay.yml"


def test_phone_relay_is_owner_only_and_scoped_to_hakim_issue():
    t = WORKFLOW.read_text(encoding="utf-8")
    assert "github.event.issue.number == 42" in t
    assert "github.event.comment.user.login == github.repository_owner" in t
    assert "startsWith(github.event.comment.body, 'HAKIM_RELAY ')" in t


def test_phone_relay_has_no_repository_secret_or_command_execution():
    t = WORKFLOW.read_text(encoding="utf-8")
    assert "HAKIM_RELAY_SENT" in t
    assert "ntfy.sh/hakim-" in t
    assert "secrets." not in t
    assert "eval(" not in t
    assert "bash -c" not in t
    assert "curl |" not in t


def test_phone_relay_forwards_message_as_data_only():
    t = WORKFLOW.read_text(encoding="utf-8")
    assert "COMMENT_BODY" in t
    assert "urllib.request.Request" in t
    assert 'method="POST"' in t
    assert "message.encode" in t
