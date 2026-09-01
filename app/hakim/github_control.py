"""Sovereign GitHub REST adapter for Ω APEX.

The adapter owns transport and write gating so autonomous development does not
depend on a chat connector. Callers still decide *whether* an action is safe
through the RecoveryGovernor/GovernanceKernel.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import io
import json
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
import zipfile


class GitHubControlError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitHubWritePolicy:
    allow_branch_create: bool = True
    allow_merge: bool = False
    allow_comment: bool = True
    allow_file_write: bool = False


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

    def _raw_request(self, method: str, path: str, payload: dict[str, object] | None = None, timeout: int = 20) -> bytes:
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
            return self._opener(req, timeout=timeout).read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise GitHubControlError(f"GitHub {method} {path} failed: HTTP {exc.code}: {detail}") from exc

    def _request(self, method: str, path: str, payload: dict[str, object] | None = None) -> object:
        raw = self._raw_request(method, path, payload)
        return {} if not raw else json.loads(raw.decode("utf-8"))

    @property
    def repo_path(self) -> str:
        return "/repos/" + "/".join(quote(part, safe="") for part in self.repository.split("/", 1))

    def get_pull_request(self, number: int) -> dict[str, object]:
        return dict(self._request("GET", f"{self.repo_path}/pulls/{number}"))

    def pull_requests_for_commit(self, sha: str) -> list[dict[str, object]]:
        result = self._request("GET", f"{self.repo_path}/commits/{quote(sha, safe='')}/pulls")
        return [dict(item) for item in result] if isinstance(result, list) else []

    def pull_request_files(self, number: int) -> list[dict[str, object]]:
        result = self._request("GET", f"{self.repo_path}/pulls/{number}/files?per_page=100")
        return [dict(item) for item in result] if isinstance(result, list) else []

    def workflow_runs_for_commit(self, sha: str) -> list[dict[str, object]]:
        result = self._request("GET", f"{self.repo_path}/actions/runs?head_sha={quote(sha, safe='')}")
        if not isinstance(result, dict):
            return []
        runs = result.get("workflow_runs", [])
        return [dict(item) for item in runs] if isinstance(runs, list) else []

    def workflow_logs(self, run_id: int, max_chars: int = 100_000) -> str:
        raw = self._raw_request("GET", f"{self.repo_path}/actions/runs/{run_id}/logs", timeout=60)
        chunks: list[str] = []
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for name in sorted(archive.namelist()):
                if name.endswith("/"):
                    continue
                text = archive.read(name).decode("utf-8", errors="replace")
                chunks.append(f"\n===== {name} =====\n{text}")
                if sum(len(x) for x in chunks) >= max_chars:
                    break
        return "".join(chunks)[:max_chars]

    def get_file(self, path: str, ref: str) -> tuple[str, str]:
        result = self._request(
            "GET",
            f"{self.repo_path}/contents/{quote(path, safe='/')}?ref={quote(ref, safe='')}",
        )
        if not isinstance(result, dict) or not isinstance(result.get("sha"), str) or not isinstance(result.get("content"), str):
            raise GitHubControlError(f"file response invalid: {path}")
        content = base64.b64decode(result["content"].replace("\n", "")).decode("utf-8")
        return result["sha"], content

    def create_branch(self, branch: str, base_sha: str) -> dict[str, object]:
        if not self.policy.allow_branch_create:
            raise PermissionError("branch creation is disabled by policy")
        return dict(self._request("POST", f"{self.repo_path}/git/refs", {"ref": f"refs/heads/{branch}", "sha": base_sha}))

    def commit_files(self, branch: str, expected_head_sha: str, changes: dict[str, str], message: str) -> str:
        """Atomically replace text files on a branch with optimistic head locking."""
        if not self.policy.allow_file_write:
            raise PermissionError("file writes are disabled by policy")
        if not changes or not message.strip():
            raise ValueError("changes and commit message are required")
        ref_path = f"{self.repo_path}/git/ref/heads/{quote(branch, safe='')}"
        ref = self._request("GET", ref_path)
        current = str(ref.get("object", {}).get("sha", "")) if isinstance(ref, dict) and isinstance(ref.get("object"), dict) else ""
        if current != expected_head_sha:
            raise GitHubControlError("branch head changed; refusing stale repair commit")
        commit = self._request("GET", f"{self.repo_path}/git/commits/{quote(current, safe='')}")
        tree = commit.get("tree", {}) if isinstance(commit, dict) else {}
        base_tree = str(tree.get("sha", "")) if isinstance(tree, dict) else ""
        if not base_tree:
            raise GitHubControlError("base tree missing")

        entries: list[dict[str, object]] = []
        for path, content in sorted(changes.items()):
            blob = self._request("POST", f"{self.repo_path}/git/blobs", {"content": content, "encoding": "utf-8"})
            blob_sha = str(blob.get("sha", "")) if isinstance(blob, dict) else ""
            if not blob_sha:
                raise GitHubControlError(f"blob creation failed: {path}")
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob_sha})
        new_tree = self._request("POST", f"{self.repo_path}/git/trees", {"base_tree": base_tree, "tree": entries})
        tree_sha = str(new_tree.get("sha", "")) if isinstance(new_tree, dict) else ""
        new_commit = self._request("POST", f"{self.repo_path}/git/commits", {"message": message, "tree": tree_sha, "parents": [current]})
        new_sha = str(new_commit.get("sha", "")) if isinstance(new_commit, dict) else ""
        if not tree_sha or not new_sha:
            raise GitHubControlError("repair commit creation failed")
        updated = self._request("PATCH", f"{self.repo_path}/git/refs/heads/{quote(branch, safe='')}", {"sha": new_sha, "force": False})
        updated_sha = str(updated.get("object", {}).get("sha", "")) if isinstance(updated, dict) and isinstance(updated.get("object"), dict) else ""
        if updated_sha != new_sha:
            raise GitHubControlError("branch ref update was not confirmed")
        return new_sha

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
