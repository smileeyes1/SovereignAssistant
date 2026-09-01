"""Executable production bootstrap for Ω APEX sovereign autonomy."""
from __future__ import annotations

import os
import signal
import threading

from .ci_repair import CISelfRepair
from .coding_provider import CodingProviderPool, OpenAIResponsesCodingProvider
from .development_actions import AutonomousDevelopmentActions
from .production import ProductionConfig, ProductionRuntime, build_production_runtime


def build_runtime_from_env(env: dict[str, str] | None = None, *, github_opener=None, provider_opener=None) -> ProductionRuntime:
    values = os.environ if env is None else env
    config = ProductionConfig.from_env(values)
    runtime = build_production_runtime(config, github_opener=github_opener)
    AutonomousDevelopmentActions(runtime).install()

    provider_key = values.get("OMEGA_OPENAI_API_KEY", "").strip()
    provider_model = values.get("OMEGA_OPENAI_MODEL", "").strip()
    if config.allow_file_write:
        if not provider_key or not provider_model:
            raise ValueError("OMEGA_OPENAI_API_KEY and OMEGA_OPENAI_MODEL are required when autonomous file repair is enabled")
        provider = OpenAIResponsesCodingProvider(
            provider_key,
            provider_model,
            base_url=values.get("OMEGA_OPENAI_BASE_URL", "https://api.openai.com/v1"),
            opener=provider_opener,
        )
        CISelfRepair(runtime, CodingProviderPool([provider])).install()
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
