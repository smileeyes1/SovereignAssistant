"""Deterministic CI recovery that does not require a coding model.

Only directly evidenced infrastructure/transient failures are eligible. Code/test
failures remain fail-closed for the coding-provider repair path. Every real
rerun is still executed through RecoveryGovernor, therefore GovernanceKernel
and MissionKernel authorize again at the execution boundary.
"""
from __future__ import annotations

from dataclasses import dataclass

from .core import ActionRisk
from .event_continuation import ContinuationEvent, EventType
from .production import ProductionRuntime
from .recovery_governor import RegisteredAction, strong_claim


_TRANSIENT_MARKERS = (
    "the runner has received a shutdown signal",
    "lost communication with the server",
    "lost communication with runner",
    "temporary failure in name resolution",
    "connection reset by peer",
    "connection timed out while connecting",
    "http 502 bad gateway",
    "http 503 service unavailable",
    "http 504 gateway timeout",
    "github services are currently unavailable",
)


@dataclass
class ProviderlessCIRecovery:
    runtime: ProductionRuntime
    max_reruns_per_run: int = 1

    def install(self) -> None:
        self.runtime.registry.register(
            RegisteredAction(
                name="rerun-transient-ci-failure",
                event_types=(EventType.CI_FAILED,),
                value=110,
                risk=ActionRisk.LOW,
                reversible=True,
                requires_human_approval=False,
                claim_factory=lambda event: strong_claim(
                    "GitHub reported a completed CI failure with directly inspectable workflow evidence",
                    "github-workflow-run",
                ),
                executor=self.rerun,
                ready=self.ready,
            )
        )

    @staticmethod
    def _workflow_run(event: ContinuationEvent) -> dict[str, object]:
        value = event.payload.get("workflow_run", {})
        if not isinstance(value, dict):
            raise RuntimeError("workflow_run payload missing")
        return value

    def _run_id(self, event: ContinuationEvent) -> int:
        value = self._workflow_run(event).get("id")
        if value is None:
            raise RuntimeError("workflow run id missing")
        return int(value)

    def _attempt_key(self, run_id: int) -> str:
        return f"omega.providerless_ci_recovery.run.{run_id}.attempts"

    def attempt_count(self, run_id: int) -> int:
        return int(self.runtime.state.get_state(self._attempt_key(run_id), 0))

    def _transient_evidence(self, event: ContinuationEvent) -> tuple[bool, str]:
        run = self._workflow_run(event)
        conclusion = str(run.get("conclusion", "")).lower()
        if conclusion == "startup_failure":
            return True, "workflow startup_failure"
        if conclusion not in {"failure", "timed_out"}:
            return False, f"unsupported conclusion: {conclusion or 'missing'}"
        logs = self.runtime.github.workflow_logs(self._run_id(event), max_chars=80_000).lower()
        for marker in _TRANSIENT_MARKERS:
            if marker in logs:
                return True, marker
        return False, "no deterministic transient marker"

    def ready(self, event: ContinuationEvent) -> bool:
        if not self.runtime.state.get_state("omega.providerless_ci_recovery.enabled", False):
            return False
        try:
            run_id = self._run_id(event)
            if self.attempt_count(run_id) >= self.max_reruns_per_run:
                return False
            transient, _ = self._transient_evidence(event)
            return transient
        except Exception:
            return False

    def rerun(self, event: ContinuationEvent) -> None:
        if not self.runtime.state.get_state("omega.providerless_ci_recovery.enabled", False):
            raise PermissionError("providerless CI rerun is disabled")
        run_id = self._run_id(event)
        if self.attempt_count(run_id) >= self.max_reruns_per_run:
            raise RuntimeError("providerless CI rerun budget exhausted")
        transient, evidence = self._transient_evidence(event)
        if not transient:
            raise RuntimeError("CI failure is not deterministically classified as transient")

        # GitHub's rerun-failed-jobs endpoint is a bounded, reversible control
        # action: it does not change repository contents or bypass release gates.
        self.runtime.github._request("POST", f"{self.runtime.github.repo_path}/actions/runs/{run_id}/rerun-failed-jobs")
        attempts = self.attempt_count(run_id) + 1
        self.runtime.state.set_state(self._attempt_key(run_id), attempts)
        self.runtime.state.set_state(
            "omega.providerless_ci_recovery.last",
            {
                "run_id": run_id,
                "attempt": attempts,
                "evidence": evidence,
                "event_id": event.event_id,
            },
        )
