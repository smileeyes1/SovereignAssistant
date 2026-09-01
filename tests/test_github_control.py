import base64
import io
import json
import zipfile

import pytest

from app.hakim.github_control import GitHubControl, GitHubControlError, GitHubWritePolicy


class Response:
    def __init__(self, payload=None, raw=None):
        self.payload = payload
        self.raw = raw

    def read(self):
        if self.raw is not None:
            return self.raw
        return json.dumps(self.payload).encode()


def test_get_pull_request_builds_authenticated_request():
    captured = {}

    def opener(req, timeout):
        captured["req"] = req
        captured["timeout"] = timeout
        return Response({"number": 7, "state": "open"})

    control = GitHubControl("token", "owner/repo", opener=opener)
    result = control.get_pull_request(7)
    assert result["number"] == 7
    req = captured["req"]
    assert req.full_url.endswith("/repos/owner/repo/pulls/7")
    assert req.get_method() == "GET"
    assert req.headers["Authorization"] == "Bearer token"


def test_branch_creation_is_allowed_by_default_but_merge_is_not():
    calls = []

    def opener(req, timeout):
        calls.append((req.get_method(), req.full_url, json.loads(req.data.decode()) if req.data else None))
        return Response({"ok": True})

    control = GitHubControl("t", "o/r", opener=opener)
    assert control.create_branch("feature/x", "abc")["ok"]
    with pytest.raises(PermissionError, match="merge is disabled"):
        control.merge_pull_request(3, "abc")
    assert calls[0][0] == "POST"
    assert calls[0][2] == {"ref": "refs/heads/feature/x", "sha": "abc"}


def test_merge_requires_explicit_policy_and_expected_head_sha():
    calls = []

    def opener(req, timeout):
        calls.append(json.loads(req.data.decode()))
        return Response({"merged": True, "sha": "merged-sha"})

    control = GitHubControl("t", "o/r", policy=GitHubWritePolicy(allow_merge=True), opener=opener)
    result = control.merge_pull_request(9, "head-sha", "squash")
    assert result["merged"] is True
    assert calls == [{"sha": "head-sha", "merge_method": "squash"}]


def test_commit_pr_and_workflow_discovery_are_normalized():
    responses = iter([
        Response([{"number": 4}]),
        Response({"workflow_runs": [{"id": 1, "conclusion": "success"}]})
    ])
    control = GitHubControl("", "o/r", opener=lambda req, timeout: next(responses))
    assert control.pull_requests_for_commit("abc") == [{"number": 4}]
    assert control.workflow_runs_for_commit("abc") == [{"id": 1, "conclusion": "success"}]


def test_comment_policy_and_empty_body_guard():
    control = GitHubControl("", "o/r", policy=GitHubWritePolicy(allow_comment=False), opener=lambda req, timeout: Response({}))
    with pytest.raises(PermissionError):
        control.add_pr_comment(1, "x")
    control = GitHubControl("", "o/r", opener=lambda req, timeout: Response({}))
    with pytest.raises(ValueError):
        control.add_pr_comment(1, "   ")


def test_get_file_decodes_repository_content():
    encoded = base64.b64encode(b"print('ok')\n").decode()
    control = GitHubControl("", "o/r", opener=lambda req, timeout: Response({"sha": "blob", "content": encoded}))
    assert control.get_file("app/x.py", "abc") == ("blob", "print('ok')\n")


def test_workflow_logs_extract_zip_text():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("test/1_test.txt", "FAILED assertion")
    control = GitHubControl("", "o/r", opener=lambda req, timeout: Response(raw=buffer.getvalue()))
    logs = control.workflow_logs(99)
    assert "1_test.txt" in logs
    assert "FAILED assertion" in logs


def test_atomic_commit_uses_expected_head_and_updates_ref_once():
    calls = []

    def opener(req, timeout):
        payload = None if req.data is None else json.loads(req.data.decode())
        calls.append((req.get_method(), req.full_url, payload))
        url = req.full_url
        if "/git/ref/heads/" in url:
            return Response({"object": {"sha": "old"}})
        if "/git/commits/old" in url and req.get_method() == "GET":
            return Response({"tree": {"sha": "tree-old"}})
        if "/git/blobs" in url:
            return Response({"sha": "blob-new"})
        if "/git/trees" in url:
            return Response({"sha": "tree-new"})
        if "/git/commits" in url and req.get_method() == "POST":
            return Response({"sha": "commit-new"})
        if "/git/refs/heads/" in url and req.get_method() == "PATCH":
            return Response({"object": {"sha": "commit-new"}})
        raise AssertionError((req.get_method(), url))

    policy = GitHubWritePolicy(allow_file_write=True)
    control = GitHubControl("t", "o/r", policy=policy, opener=opener)
    sha = control.commit_files("feature/fix", "old", {"x.py": "x=2\n"}, "fix")
    assert sha == "commit-new"
    patch_calls = [c for c in calls if c[0] == "PATCH"]
    assert len(patch_calls) == 1
    assert patch_calls[0][2] == {"sha": "commit-new", "force": False}


def test_atomic_commit_refuses_stale_head_and_default_write_policy():
    control = GitHubControl("", "o/r", opener=lambda req, timeout: Response({"object": {"sha": "other"}}))
    with pytest.raises(PermissionError):
        control.commit_files("b", "expected", {"x": "y"}, "fix")
    control = GitHubControl("", "o/r", policy=GitHubWritePolicy(allow_file_write=True), opener=lambda req, timeout: Response({"object": {"sha": "other"}}))
    with pytest.raises(GitHubControlError, match="head changed"):
        control.commit_files("b", "expected", {"x": "y"}, "fix")
