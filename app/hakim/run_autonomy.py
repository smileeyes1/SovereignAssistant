"""Executable production bootstrap for Ω APEX sovereign autonomy."""
from __future__ import annotations

import os
import signal
import threading

from .autonomy_roadmap import DEFAULT_AUTONOMY_ROADMAP
from .capability_registry import CapabilityRegistry
from .ci_repair import CISelfRepair
from .coding_provider import CodingProviderPool, OpenAICompatibleChatCodingProvider, OpenAIResponsesCodingProvider
from .continuous_excellence import ContinuousExcellenceController, OperationalSignalCollector
from .cost_policy import CostPolicy, CostTier
from .development_actions import AutonomousDevelopmentActions
from .event_continuation import EventType
from .goal_governor import GoalPortfolio
from .goal_loop import ClosedLoopGoalGovernor
from .production import ProductionConfig, ProductionRuntime, build_production_runtime
from .self_audit import AutonomySelfAuditor


ROADMAP_BOOTSTRAP_EVENT = "omega-roadmap-bootstrap-v1"


def _build_coding_providers(values, *, provider_opener=None, policy: CostPolicy):
    """Build providers from cheapest/most sovereign to paid break-glass.

    Order is local/offline -> explicitly free remote -> paid reference adapter.
    CodingProviderPool independently re-sorts by cost tier, so future callers cannot
    accidentally place a paid provider ahead of a free one.
    """
    providers = []

    local_model = values.get("OMEGA_LOCAL_MODEL", "").strip()
    if local_model:
        providers.append(
            OpenAICompatibleChatCodingProvider(
                local_model,
                base_url=values.get("OMEGA_LOCAL_API_BASE_URL", "http://127.0.0.1:11434/v1"),
                api_key=values.get("OMEGA_LOCAL_API_KEY", ""),
                cost_tier=CostTier.LOCAL,
                max_output_tokens=policy.max_output_tokens,
                opener=provider_opener,
                name="local-openai-compatible",
            )
        )

    free_model = values.get("OMEGA_FREE_MODEL", "").strip()
    free_base_url = values.get("OMEGA_FREE_API_BASE_URL", "").strip()
    if free_model and free_base_url:
        providers.append(
            OpenAICompatibleChatCodingProvider(
                free_model,
                base_url=free_base_url,
                api_key=values.get("OMEGA_FREE_API_KEY", ""),
                cost_tier=CostTier.FREE,
                max_output_tokens=policy.max_output_tokens,
                opener=provider_opener,
                name="free-openai-compatible",
            )
        )

    # Paid provider is a true break-glass route: the policy flag and finite call
    # budget must both admit it. Merely setting a paid API key never enables spend.
    paid_key = values.get("OMEGA_OPENAI_API_KEY", "").strip()
    paid_model = values.get("OMEGA_OPENAI_MODEL", "").strip()
    if policy.allow_paid and policy.max_paid_calls > 0 and paid_key and paid_model:
        providers.append(
            OpenAIResponsesCodingProvider(
                paid_key,
                paid_model,
                base_url=values.get("OMEGA_OPENAI_BASE_URL", "https://api.openai.com/v1"),
                opener=provider_opener,
            )
        )

    return providers


def build_runtime_from_env(env: dict[str, str] | None = None, *, github_opener=None, provider_opener=None) -> ProductionRuntime:
    values = os.environ if env is None else env
    config = ProductionConfig.from_env(values)
    runtime = build_production_runtime(config, github_opener=github_opener)
    AutonomousDevelopmentActions(runtime).install()
    capabilities = CapabilityRegistry(runtime.state)

    # Mission intent/state exists independently of whether a coding provider is
    # currently available. This prevents "no provider" from looking like a
    # completed or empty mission.
    portfolio = GoalPortfolio(runtime)
    portfolio.seed_if_empty(DEFAULT_AUTONOMY_ROADMAP)
    self_auditor = AutonomySelfAuditor(runtime, capabilities)
    excellence = ContinuousExcellenceController(runtime.state, runtime.queue)
    signals = OperationalSignalCollector(runtime.state, runtime.queue)

    def autonomy_heartbeat() -> None:
        report = self_auditor.run_once()
        # Finite roadmap completion becomes the Golden Baseline. Only a healthy,
        # fully completed roadmap may enter continuous-excellence discovery.
        if report.status != "healthy" or portfolio.active() or portfolio.next_ready() is not None:
            return
        excellence.evaluate(signals.collect())

    runtime.service.supervisor.heartbeat = autonomy_heartbeat

    cost_policy = CostPolicy.from_env(values)
    runtime.state.set_state(
        "omega.cost_policy",
        {
            "mode": cost_policy.mode,
            "allow_paid": cost_policy.allow_paid,
            "max_paid_calls": cost_policy.max_paid_calls,
            "max_failure_log_chars": cost_policy.max_failure_log_chars,
            "max_output_tokens": cost_policy.max_output_tokens,
        },
    )

    if config.allow_file_write:
        provider_list = _build_coding_providers(values, provider_opener=provider_opener, policy=cost_policy)
        if not provider_list:
            raise ValueError(
                "autonomous file repair requires a local/free coding provider; "
                "paid providers are disabled by default. Configure OMEGA_LOCAL_MODEL or "
                "OMEGA_FREE_MODEL + OMEGA_FREE_API_BASE_URL. Paid break-glass additionally "
                "requires OMEGA_PAID_PROVIDERS_ALLOWED=true and a finite positive "
                "OMEGA_PAID_PROVIDER_MAX_CALLS."
            )
        providers = CodingProviderPool(provider_list, capabilities, cost_policy=cost_policy)
        runtime.state.set_state("omega.provider_usage", providers.usage_snapshot())
        CISelfRepair(runtime, providers).install()
        ClosedLoopGoalGovernor(runtime, providers, portfolio).install()
        runtime.queue.enqueue(
            ROADMAP_BOOTSTRAP_EVENT,
            EventType.MANUAL_SIGNAL.value,
            "default-autonomy-roadmap",
            {"source": "production-bootstrap", "cost_mode": cost_policy.mode},
            max_attempts=5,
        )
    return runtime


def main() -> None:
    runtime = build_runtime_from_env()
    stopped = threading.Event()

    def stop_handler(signum, frame):
        stopped.set()

    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    address = runtime.start()
    print(f"Ω APEX autonomy service listening on {address[0]}:{address[1]}", flush=True)
    try:
        stopped.wait()
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
