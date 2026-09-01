import io
import json

import pytest

from app.hakim.github_control import GitHubControl, GitHubWritePolicy


class Response:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
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
