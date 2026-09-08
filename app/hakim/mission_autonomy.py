"""ΩL7 bounded mission autonomy controls.

These primitives are deterministic and conservative. Every executable mission
step is evaluated by GovernanceKernel and then MissionKernel before its callback
may run. Outcome audit, champion/challenger admission, canary rollback and
bounded multi-environment progression remain inside the declared envelope.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Callable, Iterable

from .core import Action, ActionRisk, Claim, Decision, Evidence, GovernanceKernel
from .durable_state import DurableStateStore
from .mission_kernel import AuthorityLevel, MissionAction, MissionKernel, OperationalEnvelope


@dataclass(frozen=True)
class OutcomeRecord:
    mission_id: str
    goal_id: str
    environment: str
    status: str
    evidence: tuple[str, ...]
    rollback: bool = False


class OutcomeAudit:
    PREFIX = "omega.outcomes"
    RESERVATION_PREFIX = "omega.mission_execution_reservations"
    APPROVAL_PREFIX = "omega.human_approval_consumption"

    def __init__(self, state: DurableStateStore):
        self.state = state

    def record(self, item: OutcomeRecord) -> None:
        if not item.mission_id.strip() or not item.goal_id.strip() or not item.environment.strip():
            raise ValueError("mission_id, goal_id and environment are required")
        if item.status not in {"completed", "failed", "rolled_back", "blocked"}:
            raise ValueError("invalid outcome status")
        if item.status == "completed" and not item.evidence:
            raise ValueError("completed outcomes require evidence")
        self.state.set_state(
            f"{self.PREFIX}.{item.mission_id}.{item.goal_id}.{item.environment}",
            {
                "mission_id": item.mission_id,
                "goal_id": item.goal_id,
                "environment": item.environment,
                "status": item.status,
                "evidence": list(item.evidence),
                "rollback": item.rollback,
            },
        )

    def get(self, mission_id: str, goal_id: str, environment: str) -> dict[str, object]:
        value = self.state.get_state(f"{self.PREFIX}.{mission_id}.{goal_id}.{environment}", {})
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _reservation_value(mission_id: str, goal_id: str, environment: str, state: str) -> dict[str, str]:
        return {"mission_id": mission_id, "goal_id": goal_id, "environment": environment, "state": state}

    def _reservation_key(self, mission_id: str, goal_id: str, environment: str) -> str:
        return f"{self.RESERVATION_PREFIX}.{mission_id}.{goal_id}.{environment}"

    def reserve_execution(self, mission_id: str, goal_id: str, environment: str) -> bool:
        """Reserve one execution slot, or reuse only a durably compensated slot."""
        key = self._reservation_key(mission_id, goal_id, environment)
        reserved = self._reservation_value(mission_id, goal_id, environment, "reserved")
        if self.state.set_state_if_absent(key, reserved):
            return True
        compensated = self._reservation_value(mission_id, goal_id, environment, "compensated")
        return self.state.compare_and_set_state(key, compensated, reserved)

    def mark_execution_compensated(self, mission_id: str, goal_id: str, environment: str) -> bool:
        """Durably prove a reservation is reusable only after a proven rollback."""
        key = self._reservation_key(mission_id, goal_id, environment)
        reserved = self._reservation_value(mission_id, goal_id, environment, "reserved")
        compensated = self._reservation_value(mission_id, goal_id, environment, "compensated")
        current = self.state.get_state(key, None)
        if current == compensated:
            return True
        return self.state.compare_and_set_state(key, reserved, compensated)

    @staticmethod
    def _approval_digest(approval_evidence: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
        normalized = tuple(str(item).strip() for item in approval_evidence if str(item).strip())
        if not normalized:
            return "", ()
        canonical = json.dumps(list(normalized), ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), normalized

    def consume_approval(
        self,
        mission_id: str,
        goal_id: str,
        environment: str,
        approval_evidence: tuple[str, ...],
    ) -> bool:
        """Atomically consume one human-approval proof before consequential execution.

        The proof itself is never persisted in this ledger. Its canonical digest is
        globally single-use, so the same approval cannot authorize another
        consequential side effect after restart, rollback, or across mission steps.
        """
        if not mission_id.strip() or not goal_id.strip() or not environment.strip():
            raise ValueError("mission_id, goal_id and environment are required")
        digest, _ = self._approval_digest(approval_evidence)
        if not digest:
            return False
        return self.state.set_state_if_absent(
            f"{self.APPROVAL_PREFIX}.{digest}",
            {
                "proof_sha256": digest,
                "mission_id": mission_id,
                "goal_id": goal_id,
                "environment": environment,
                "state": "consumed",
            },
        )

    def claim_approved_execution(
        self,
        mission_id: str,
        goal_id: str,
        environment: str,
        approval_evidence: tuple[str, ...],
    ) -> str:
        """Atomically consume approval authority and acquire its execution slot."""
        if not mission_id.strip() or not goal_id.strip() or not environment.strip():
            raise ValueError("mission_id, goal_id and environment are required")
        digest, _ = self._approval_digest(approval_evidence)
        if not digest:
            return "claim_exists"
        reservation_key = self._reservation_key(mission_id, goal_id, environment)
        reserved = self._reservation_value(mission_id, goal_id, environment, "reserved")
        compensated = self._reservation_value(mission_id, goal_id, environment, "compensated")
        return self.state.claim_once_and_reserve(
            f"{self.APPROVAL_PREFIX}.{digest}",
            {
                "proof_sha256": digest,
                "mission_id": mission_id,
                "goal_id": goal_id,
                "environment": environment,
                "state": "consumed",
            },
            reservation_key,
            reserved,
            compensated,
        )


@dataclass(frozen=True)
class CandidateScore:
    name: str
    quality: float
    safety: float
    regression_passed: bool


@dataclass(frozen=True)
class PromotionDecision:
    promote: bool
    selected: str
    reason: str


class ImprovementSandbox:
    """Champion/challenger admission with fail-closed canary rollback semantics."""

    def choose(self, champion: CandidateScore, challenger: CandidateScore) -> PromotionDecision:
        if not challenger.regression_passed:
            return PromotionDecision(False, champion.name, "challenger regression failed")
        if challenger.safety < champion.safety:
            return PromotionDecision(False, champion.name, "challenger safety regressed")
        if challenger.quality <= champion.quality:
            return PromotionDecision(False, champion.name, "challenger has no quality gain")
        return PromotionDecision(True, challenger.name, "challenger dominated champion")

    def canary(self, decision: PromotionDecision, probe: Callable[[], bool]) -> PromotionDecision:
        if not decision.promote:
            return decision
        try:
            passed = bool(probe())
        except Exception:
            passed = False
        if not passed:
            return PromotionDecision(False, "champion", "canary failed; rollback required")
        return decision


_RISK_SCORE = {
    ActionRisk.LOW: 0,
    ActionRisk.MODERATE: 1,
    ActionRisk.HIGH: 2,
    ActionRisk.CRITICAL: 3,
}


@dataclass(frozen=True)
class MissionStep:
    goal_id: str
    environment: str
    capability: str
    risk: ActionRisk
    reversible: bool
    evidence: tuple[str, ...]
    execute: Callable[[], tuple[bool, tuple[str, ...]]]
    rollback: Callable[[], bool]
    requires_human_approval: bool = False


@dataclass(frozen=True)
class MissionRun:
    completed: bool
    attempted: int
    recovered: int
    outcomes: tuple[OutcomeRecord, ...]


class BoundedMissionRunner:
    """Runs bounded multi-environment work only after both Golden Baseline gates."""

    def __init__(
        self,
        audit: OutcomeAudit,
        *,
        governance: GovernanceKernel | None = None,
        mission_kernel: MissionKernel | None = None,
        approval_verifier: Callable[[str, MissionStep], tuple[bool, tuple[str, ...]]] | None = None,
    ):
        self.audit = audit
        self.governance = governance or GovernanceKernel()
        self.mission_kernel = mission_kernel or MissionKernel(
            OperationalEnvelope(frozenset({"mission-step"}), max_risk=2, require_reversible_above=1, min_evidence=1)
        )
        self.approval_verifier = approval_verifier

    def _authorized(self, mission_id: str, step: MissionStep) -> tuple[bool, tuple[str, ...]]:
        claim = Claim(
            f"mission step {step.goal_id} in {step.environment} is ready",
            tuple(Evidence("mission-plan", item, 1.0) for item in step.evidence if item.strip()),
            confidence=1.0 if step.evidence else 0.0,
        )
        action = Action(
            step.goal_id,
            step.risk,
            reversible=step.reversible,
            requires_human_approval=step.requires_human_approval,
        )
        governance_decision = self.governance.evaluate(claim, action)
        human_approved = False
        approval_evidence: tuple[str, ...] = ()
        if governance_decision == Decision.APPROVAL_REQUIRED:
            if self.approval_verifier is None:
                return False, ()
            try:
                approved, proof = self.approval_verifier(mission_id, step)
            except Exception:
                return False, ()
            approval_evidence = tuple(str(item) for item in proof if str(item).strip())
            if not approved or not approval_evidence:
                return False, ()
            human_approved = True
        elif governance_decision != Decision.PROCEED:
            return False, ()
        mission = MissionAction(
            name=step.goal_id,
            capability=step.capability,
            risk=_RISK_SCORE[step.risk],
            reversible=step.reversible,
            authority=AuthorityLevel.CONSEQUENTIAL if step.requires_human_approval else AuthorityLevel.MODERATE,
            evidence=step.evidence,
        )
        allowed = self.mission_kernel.evaluate(mission, human_approved=human_approved).allowed
        return allowed, approval_evidence if allowed else ()

    @staticmethod
    def _record_from_state(value: dict[str, object]) -> OutcomeRecord:
        return OutcomeRecord(
            str(value.get("mission_id", "")),
            str(value.get("goal_id", "")),
            str(value.get("environment", "")),
            str(value.get("status", "")),
            tuple(str(item) for item in value.get("evidence", []) if str(item)),
            bool(value.get("rollback", False)),
        )

    def _blocked_without_side_effect(
        self,
        mission_id: str,
        step: MissionStep,
        attempted: int,
        recovered: int,
        outcomes: list[OutcomeRecord],
        reason: str,
    ) -> MissionRun:
        """Contain pre-execution persistence faults as a fail-closed in-memory outcome.

        Recording the blocked outcome is best-effort because the same persistence
        layer may be unavailable. The authoritative safety property is that the
        step callback is never invoked when reservation/authority persistence is
        not proven.
        """
        record = OutcomeRecord(mission_id, step.goal_id, step.environment, "blocked", (reason,), False)
        try:
            self.audit.record(record)
        except Exception:
            pass
        outcomes.append(record)
        return MissionRun(False, attempted, recovered, tuple(outcomes))

    def _blocked_after_side_effect(
        self,
        mission_id: str,
        step: MissionStep,
        attempted: int,
        recovered: int,
        outcomes: list[OutcomeRecord],
        evidence: tuple[str, ...],
        reason: str,
    ) -> MissionRun:
        """Contain post-execution audit faults without risking duplicate execution.

        The existing reservation is deliberately retained unless a rollback was
        durably compensated. This converts ambiguous persistence into an explicit
        fail-closed outcome instead of allowing an exception to escape or a retry
        to repeat a consequential side effect.
        """
        record = OutcomeRecord(
            mission_id,
            step.goal_id,
            step.environment,
            "blocked",
            tuple(evidence) + (reason,),
            False,
        )
        try:
            self.audit.record(record)
        except Exception:
            pass
        outcomes.append(record)
        return MissionRun(False, attempted, recovered, tuple(outcomes))

    def run(self, mission_id: str, steps: Iterable[MissionStep]) -> MissionRun:
        outcomes: list[OutcomeRecord] = []
        recovered = 0
        attempted = 0
        for step in steps:
            attempted += 1
            try:
                prior = self.audit.get(mission_id, step.goal_id, step.environment)
            except Exception:
                return self._blocked_without_side_effect(
                    mission_id,
                    step,
                    attempted,
                    recovered,
                    outcomes,
                    "outcome audit persistence unavailable before execution; no side effect executed",
                )
            if prior.get("status") == "completed":
                outcomes.append(self._record_from_state(prior))
                continue
            if prior.get("status") == "rolled_back" and prior.get("rollback") is True:
                try:
                    reconciled = self.audit.mark_execution_compensated(mission_id, step.goal_id, step.environment)
                except Exception:
                    return self._blocked_without_side_effect(
                        mission_id,
                        step,
                        attempted,
                        recovered,
                        outcomes,
                        "rollback reservation reconciliation persistence unavailable; no new side effect executed",
                    )
                if not reconciled:
                    record = OutcomeRecord(
                        mission_id,
                        step.goal_id,
                        step.environment,
                        "blocked",
                        ("proven rollback could not reconcile execution reservation",),
                        False,
                    )
                    try:
                        self.audit.record(record)
                    except Exception:
                        pass
                    outcomes.append(record)
                    return MissionRun(False, attempted, recovered, tuple(outcomes))
            authorized, approval_evidence = self._authorized(mission_id, step)
            if not authorized:
                record = OutcomeRecord(mission_id, step.goal_id, step.environment, "blocked", step.evidence, False)
                try:
                    self.audit.record(record)
                except Exception:
                    pass
                outcomes.append(record)
                return MissionRun(False, attempted, recovered, tuple(outcomes))
            try:
                if approval_evidence:
                    claim_status = self.audit.claim_approved_execution(
                        mission_id, step.goal_id, step.environment, approval_evidence
                    )
                    if claim_status != "claimed":
                        evidence = (
                            ("human approval proof already consumed",)
                            if claim_status == "claim_exists"
                            else ("execution reservation already exists without a completed or compensated outcome",)
                        )
                        record = OutcomeRecord(
                            mission_id,
                            step.goal_id,
                            step.environment,
                            "blocked",
                            evidence,
                            False,
                        )
                        try:
                            self.audit.record(record)
                        except Exception:
                            pass
                        outcomes.append(record)
                        return MissionRun(False, attempted, recovered, tuple(outcomes))
                elif not self.audit.reserve_execution(mission_id, step.goal_id, step.environment):
                    record = OutcomeRecord(
                        mission_id,
                        step.goal_id,
                        step.environment,
                        "blocked",
                        ("execution reservation already exists without a completed or compensated outcome",),
                        False,
                    )
                    try:
                        self.audit.record(record)
                    except Exception:
                        pass
                    outcomes.append(record)
                    return MissionRun(False, attempted, recovered, tuple(outcomes))
            except Exception:
                return self._blocked_without_side_effect(
                    mission_id,
                    step,
                    attempted,
                    recovered,
                    outcomes,
                    "execution authority/reservation persistence unavailable; no side effect executed",
                )
            try:
                ok, result_evidence = step.execute()
            except Exception:
                ok, result_evidence = False, ()
            durable_evidence = tuple(result_evidence) + approval_evidence
            if ok and result_evidence:
                record = OutcomeRecord(mission_id, step.goal_id, step.environment, "completed", durable_evidence, False)
                try:
                    self.audit.record(record)
                except Exception:
                    return self._blocked_after_side_effect(
                        mission_id,
                        step,
                        attempted,
                        recovered,
                        outcomes,
                        durable_evidence,
                        "side effect succeeded but completed outcome persistence is unavailable; reservation retained",
                    )
                outcomes.append(record)
                continue
            rollback_ok = False
            try:
                rollback_ok = bool(step.rollback())
            except Exception:
                rollback_ok = False
            if rollback_ok:
                try:
                    compensated = self.audit.mark_execution_compensated(mission_id, step.goal_id, step.environment)
                except Exception:
                    return self._blocked_after_side_effect(
                        mission_id,
                        step,
                        attempted,
                        recovered,
                        outcomes,
                        durable_evidence,
                        "rollback succeeded but reservation compensation persistence is unavailable",
                    )
                if compensated:
                    recovered += 1
                    record = OutcomeRecord(
                        mission_id, step.goal_id, step.environment, "rolled_back", durable_evidence, True
                    )
                else:
                    record = OutcomeRecord(
                        mission_id,
                        step.goal_id,
                        step.environment,
                        "blocked",
                        durable_evidence + ("rollback succeeded but execution reservation compensation was not persisted",),
                        False,
                    )
                try:
                    self.audit.record(record)
                except Exception:
                    return self._blocked_after_side_effect(
                        mission_id,
                        step,
                        attempted,
                        recovered,
                        outcomes,
                        durable_evidence,
                        "rollback outcome audit persistence unavailable after side effect handling",
                    )
            else:
                record = OutcomeRecord(mission_id, step.goal_id, step.environment, "failed", durable_evidence, False)
                try:
                    self.audit.record(record)
                except Exception:
                    return self._blocked_after_side_effect(
                        mission_id,
                        step,
                        attempted,
                        recovered,
                        outcomes,
                        durable_evidence,
                        "failed execution outcome persistence unavailable; reservation retained",
                    )
            outcomes.append(record)
            return MissionRun(False, attempted, recovered, tuple(outcomes))
        return MissionRun(bool(outcomes), attempted, recovered, tuple(outcomes))
