import importlib.util
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "generate-hakim-direct-pairing.py"
MAIN_ACTIVITY = ROOT / "android" / "hakim-companion" / "app" / "src" / "main" / "java" / "org" / "hakim" / "omega" / "companion" / "MainActivity.kt"


def load_generator():
    spec = importlib.util.spec_from_file_location("hakim_pairing_generator", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_generator_matches_android_direct_relay_contract():
    g = load_generator()
    pair, intent = g.pairing_urls(
        token="t" * 48,
        relay_topic="hakim-cmd-" + "a" * 32,
        result_topic="hakim-result-" + "b" * 32,
        relay_key="k" * 48,
    )
    qs = parse_qs(urlparse(pair).query)
    assert set(qs) == {"token", "relay_topic", "result_topic", "relay_key", "relay_base"}
    assert qs["result_topic"] == ["hakim-result-" + "b" * 32]
    assert "result_url" not in pair
    assert "result_url" not in intent
    assert "package=org.hakim.omega.companion" in intent


def test_runtime_and_generator_share_result_topic_name():
    runtime = MAIN_ACTIVITY.read_text(encoding="utf-8")
    generator = GENERATOR.read_text(encoding="utf-8")
    assert 'getQueryParameter("result_topic")' in runtime
    assert '"result_topic": result_topic' in generator
    assert 'getQueryParameter("result_url")' not in runtime


def test_pairing_rejects_ambiguous_or_weak_channel_material():
    g = load_generator()
    try:
        g.pairing_urls(
            token="t" * 48,
            relay_topic="same-topic-abcdefghijklmnop",
            result_topic="same-topic-abcdefghijklmnop",
            relay_key="k" * 48,
        )
    except ValueError as exc:
        assert "distinct" in str(exc)
    else:
        raise AssertionError("same command/result topic must fail closed")

    try:
        g.pairing_urls(
            token="short",
            relay_topic="hakim-cmd-" + "a" * 32,
            result_topic="hakim-result-" + "b" * 32,
            relay_key="short",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("weak pairing material must fail closed")
