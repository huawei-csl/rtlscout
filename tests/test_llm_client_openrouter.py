"""OpenRouter client: provider pin and completion cap from the environment; provider and finish reason reported."""
from types import SimpleNamespace

from rtlscout.llm_client import OpenRouterClient


def _fake_response(provider="Z.AI", finish_reason="tool_calls"):
    msg = SimpleNamespace(content="hi", tool_calls=None)
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason=finish_reason)], usage=usage,
                           provider=provider)


def _client(monkeypatch, response):
    client = OpenRouterClient(model="z-ai/glm-5.3-flash", api_key="x")
    seen = {}

    def create(**kwargs):
        seen.update(kwargs)
        return response
    monkeypatch.setattr(client._client.chat.completions, "create", create)
    return client, seen


def test_default_request_has_no_provider_pin_and_no_cap(monkeypatch):
    monkeypatch.delenv("RTLSCOUT_OPENROUTER_PROVIDERS", raising=False)
    monkeypatch.delenv("RTLSCOUT_OPENROUTER_MAX_TOKENS", raising=False)
    monkeypatch.delenv("RTLSCOUT_REASONING_EFFORT", raising=False)
    client, seen = _client(monkeypatch, _fake_response())
    out = client.chat_completion([{"role": "user", "content": "x"}], tools=[])
    assert "extra_body" not in seen and "max_tokens" not in seen
    assert out.provider == "Z.AI" and out.finish_reason == "tool_calls"
    assert out.usage.input_tokens == 10 and out.usage.output_tokens == 5


def test_env_pins_providers_and_caps_tokens(monkeypatch):
    monkeypatch.setenv("RTLSCOUT_OPENROUTER_PROVIDERS", "z-ai, deepinfra")
    monkeypatch.setenv("RTLSCOUT_OPENROUTER_MAX_TOKENS", "65536")
    monkeypatch.setenv("RTLSCOUT_REASONING_EFFORT", "high")
    client, seen = _client(monkeypatch, _fake_response(finish_reason="length"))
    out = client.chat_completion([{"role": "user", "content": "x"}], tools=[])
    assert seen["extra_body"] == {"reasoning": {"effort": "high"},
                                  "provider": {"order": ["z-ai", "deepinfra"], "allow_fallbacks": False}}
    assert seen["max_tokens"] == 65536
    assert out.finish_reason == "length"


def test_response_without_provider_field(monkeypatch):
    monkeypatch.delenv("RTLSCOUT_OPENROUTER_PROVIDERS", raising=False)
    resp = _fake_response(); del resp.provider          # a plain OpenAI-compatible server
    client, seen = _client(monkeypatch, resp)
    assert client.chat_completion([{"role": "user", "content": "x"}], tools=[]).provider is None
