"""Sovereign GitHub REST adapter for Ω APEX.

The adapter owns transport and write gating so autonomous development does not
depend on a chat connector.  Callers still decide *whether* an action is safe
through the RecoveryGovernor/GovernanceKernel.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


class GitHubControlError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitHubWritePolicy:
    allow_branch_create: bool = True
    allow_merge: bool = False
    allow_comment: bool = True


class GitHubControl:
    def __init__(
        self,
        token: str,
        repository: str,
        *,
        api_base: str = "https://api.github.com",
        policy: GitHubWritePolicy | None = None,
        opener: Callable[..., object] | None = None,
    ):
        if "/" not in repository:
            raise ValueError("repository must be owner/name")
        self.token = token
        self.repository = repository
        self.api_base = api_base.rstrip("/")
        self.policy = policy or GitHubWritePolicy()
        self._opener = opener or urlopen

    def _request(self, method: str, path: str, payload: dict[str, object] | None = None) -> object:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "omega-apex",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = Request(f"{self.api_base}{path}", data=body, headers=headers, method=method)
        try:
            response = self._opener(req, timeout=20)
            raw = response.read()
            return {} if not raw else json.loads(raw.decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise GitHubControlError(f"GitHub {method} {path} failed: HTTP {exc.code}: {detail}") from exc

    @property
    def repo_path(self) -> str:
        return "/repos/" + "/".join(quote(part, safe="") for part in self.repository.split("/", 1))

    def get_pull_request(self, number: int) -> dict[str, object]:
        return dict(self._request("GET", f"{self.repo_path}/pulls/{number}"))

    def pull_requests_for_commit(self, sha: str) -> list[dict[str, object]]:
        result = self._request("GET", f"{self.repo_path}/commits/{quote(sha, safe='')}/pulls")
        return [dict(item) for item in result] if isinstance(result, list) else []

    def workflow_runs_for_commit(self, sha: str) -> list[dict[str, object]]:
        result = self._request("GET", f"{self.repo_path}/actions/runs?head_sha={quote(sha, safe='')}")
        if not isinstance(result, dict):
            return []
        runs = result.get("workflow_runs", [])
        return [dict(item) for item in runs] if isinstance(runs, list) else []

    def create_branch(self, branch: str, base_sha: str) -> dict[str, object]:
        if not self.policy.allow_branch_create:
            raise PermissionError("branch creation is disabled by policy")
        return dict(self._request("POST", f"{self.repo_path}/git/refs", {"ref": f"refs/heads/{branch}", "sha": base_sha}))

    def merge_pull_request(self, number: int, expected_head_sha: str, method: str = "squash") -> dict[str, object]:
        if not self.policy.allow_merge:
            raise PermissionError("pull request merge is disabled by policy")
        if method not in {"merge", "squash", "rebase"}:
            raise ValueError("unsupported merge method")
        return dict(
            self._request(
                "PUT",
                f"{self.repo_path}/pulls/{number}/merge",
                {"sha": expected_head_sha, "merge_method": method},
            )
        )

    def add_pr_comment(self, number: int, body: str) -> dict[str, object]:
        if not self.policy.allow_comment:
            raise PermissionError("comments are disabled by policy")
        if not body.strip():
            raise ValueError("comment body is required")
        return dict(self._request("POST", f"{self.repo_path}/issues/{number}/comments", {"body": body}))
