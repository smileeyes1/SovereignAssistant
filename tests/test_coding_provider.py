import json

import pytest

from app.hakim.coding_provider import CodingProviderPool, OpenAIResponsesCodingProvider, PatchPlan, PatchRequest, validate_patch


class BrokenProvider:
    name = "broken"
    def propose_patch(self, request):
        raise RuntimeError("offline")


class GoodProvider:
    name = "good"
    def propose_patch(self, request):
        return PatchPlan(self.name, "fix test", {"app/main.py": "print('fixed')\n"})


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


def test_responses_adapter_rejects_duplicate_paths():
    payload = {"output": [{"content": [{"type": "output_text", "text": json.dumps({"summary": "x", "files": [{"path": "x.py", "content": "1"}, {"path": "x.py", "content": "2"}]})}]}]}
    provider = OpenAIResponsesCodingProvider("key", "m", opener=lambda req, timeout: Response(payload))
    with pytest.raises(ValueError, match="duplicate file path"):
        provider.propose_patch(PatchRequest("x", "y", {"x.py": "0"}))
