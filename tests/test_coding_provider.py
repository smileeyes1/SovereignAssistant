import json

import pytest

from app.hakim.coding_provider import (
    CodingProviderPool,
    OpenAICompatibleChatCodingProvider,
    OpenAIResponsesCodingProvider,
    PatchPlan,
    PatchRequest,
    validate_patch,
)
from app.hakim.cost_policy import CostPolicy, CostTier


class BrokenProvider:
    name = "broken"
    def propose_patch(self, request):
        raise RuntimeError("offline")


class GoodProvider:
    name = "good"
    def propose_patch(self, request):
        return PatchPlan(self.name, "fix test", {"app/main.py": "print('fixed')\n"})


class PaidProvider(GoodProvider):
    name = "paid"
    cost_tier = CostTier.PAID


class FreeProvider(GoodProvider):
    name = "free"
    cost_tier = CostTier.FREE


class LocalProvider(GoodProvider):
    name = "local"
    cost_tier = CostTier.LOCAL


class Response:
    def __init__(self, payload):
        self.payload = payload
    def read(self):
        return json.dumps(self.payload).encode()


def test_provider_pool_fails_over_to_next_provider():
    pool = CodingProviderPool([BrokenProvider(), GoodProvider()])
    plan = pool.propose_patch(PatchRequest("fix", "failed", {"app/main.py": "broken"}))
    assert plan.provider == "good"
    assert pool.failures[0][0] == "broken"


def test_pool_orders_local_then_free_then_unknown_then_paid():
    pool = CodingProviderPool(
        [PaidProvider(), GoodProvider(), FreeProvider(), LocalProvider()],
        cost_policy=CostPolicy(allow_paid=True, max_paid_calls=1),
    )
    assert [p.name for p in pool.providers] == ["local", "free", "good", "paid"]


def test_paid_provider_is_blocked_by_default_even_if_configured():
    pool = CodingProviderPool([PaidProvider()])
    with pytest.raises(RuntimeError, match="no admitted healthy"):
        pool.propose_patch(PatchRequest("fix", "failed", {"app/main.py": "broken"}))
    assert pool.paid_calls_used == 0
    assert "paid provider blocked" in pool.failures[0][1]


def test_paid_break_glass_has_finite_attempt_budget():
    class PaidBroken:
        name = "paid-broken"
        cost_tier = CostTier.PAID
        def propose_patch(self, request):
            raise RuntimeError("provider failed")

    pool = CodingProviderPool([PaidBroken()], cost_policy=CostPolicy(allow_paid=True, max_paid_calls=1))
    with pytest.raises(RuntimeError, match="all coding providers failed"):
        pool.propose_patch(PatchRequest("fix", "failed", {"app/main.py": "broken"}))
    assert pool.paid_calls_used == 1
    with pytest.raises(RuntimeError, match="no admitted healthy"):
        pool.propose_patch(PatchRequest("fix", "failed", {"app/main.py": "broken"}))
    assert pool.paid_calls_used == 1


def test_failure_log_is_bounded_before_provider_call():
    seen = {}

    class CaptureProvider(GoodProvider):
        def propose_patch(self, request):
            seen["failure_log"] = request.failure_log
            return super().propose_patch(request)

    pool = CodingProviderPool([CaptureProvider()], cost_policy=CostPolicy(max_failure_log_chars=5))
    pool.propose_patch(PatchRequest("fix", "0123456789", {"app/main.py": "broken"}))
    assert seen["failure_log"] == "56789"


def test_patch_validation_rejects_traversal_and_empty_patch():
    with pytest.raises(ValueError, match="unsafe patch path"):
        validate_patch(PatchPlan("x", "summary", {"../secret": "x"}))
    with pytest.raises(ValueError, match="at least one"):
        validate_patch(PatchPlan("x", "summary", {}))


def test_responses_adapter_requests_structured_patch_and_parses_output():
    captured = {}
    payload = {
        "output": [
            {"type": "message", "content": [
                {"type": "output_text", "text": json.dumps({"summary": "repair", "files": [{"path": "x.py", "content": "x = 1\n"}]})}
            ]}
        ]
    }

    def opener(req, timeout):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode())
        captured["authorization"] = req.headers["Authorization"]
        captured["timeout"] = timeout
        return Response(payload)

    provider = OpenAIResponsesCodingProvider("key", "model-x", opener=opener)
    plan = provider.propose_patch(PatchRequest("repair CI", "trace", {"x.py": "bad"}))
    assert plan.changes == {"x.py": "x = 1\n"}
    assert captured["url"].endswith("/v1/responses")
    assert captured["authorization"] == "Bearer key"
    assert captured["body"]["model"] == "model-x"
    assert captured["body"]["store"] is False
    assert captured["body"]["text"]["format"]["type"] == "json_schema"
    assert provider.cost_tier is CostTier.PAID


def test_responses_adapter_rejects_duplicate_paths():
    payload = {"output": [{"content": [{"type": "output_text", "text": json.dumps({"summary": "x", "files": [{"path": "x.py", "content": "1"}, {"path": "x.py", "content": "2"}]})}]}]}
    provider = OpenAIResponsesCodingProvider("key", "m", opener=lambda req, timeout: Response(payload))
    with pytest.raises(ValueError, match="duplicate file path"):
        provider.propose_patch(PatchRequest("x", "y", {"x.py": "0"}))


def test_openai_compatible_free_adapter_parses_chat_completion_without_api_key():
    captured = {}
    payload = {
        "choices": [
            {"message": {"content": json.dumps({"summary": "repair", "files": [{"path": "x.py", "content": "x = 2\n"}]})}}
        ]
    }

    def opener(req, timeout):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        captured["body"] = json.loads(req.data.decode())
        return Response(payload)

    provider = OpenAICompatibleChatCodingProvider(
        "local-model",
        base_url="http://127.0.0.1:11434/v1",
        cost_tier=CostTier.LOCAL,
        opener=opener,
        name="local",
    )
    plan = provider.propose_patch(PatchRequest("repair", "trace", {"x.py": "bad"}))
    assert plan.changes == {"x.py": "x = 2\n"}
    assert captured["url"].endswith("/v1/chat/completions")
    assert "Authorization" not in captured["headers"]
    assert captured["body"]["model"] == "local-model"
    assert provider.cost_tier is CostTier.LOCAL
