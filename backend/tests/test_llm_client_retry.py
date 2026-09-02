"""LLM client retry-with-backoff (speed-plan report lever #4a) —
_post_with_retry retries transient 429/5xx responses instead of failing (or,
for OpenRouterClient, immediately falling through to the fallback provider)
on the first blip. asyncio.sleep is monkeypatched to a no-op throughout so
these tests run instantly despite exercising real backoff attempts."""

import pytest

from app.matching import llm_client as llm_client_module
from app.matching.llm_client import OpenAIClient, OpenRouterClient, _post_with_retry


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")

    def json(self):
        return self._json


class _ScriptedClient:
    """Returns responses from `script` in order, one per call to post()."""

    def __init__(self, script: list[_FakeResponse]):
        self.script = list(script)
        self.calls = 0

    async def post(self, path, json=None):
        self.calls += 1
        return self.script.pop(0)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def _instant_sleep(_seconds):
        return None

    monkeypatch.setattr(llm_client_module.asyncio, "sleep", _instant_sleep)


@pytest.mark.asyncio
async def test_retries_429_then_succeeds():
    client = _ScriptedClient(
        [_FakeResponse({}, 429), _FakeResponse({}, 429), _FakeResponse({"ok": True}, 200)]
    )
    resp = await _post_with_retry(client, "/chat/completions", {"model": "x"})
    assert resp.json() == {"ok": True}
    assert client.calls == 3


@pytest.mark.asyncio
async def test_retries_5xx_then_succeeds():
    client = _ScriptedClient([_FakeResponse({}, 503), _FakeResponse({"ok": True}, 200)])
    resp = await _post_with_retry(client, "/embeddings", {"model": "x", "input": "y"})
    assert resp.json() == {"ok": True}
    assert client.calls == 2


@pytest.mark.asyncio
async def test_non_retryable_4xx_raises_immediately_without_retrying():
    client = _ScriptedClient([_FakeResponse({}, 401)])
    with pytest.raises(RuntimeError, match="status 401"):
        await _post_with_retry(client, "/chat/completions", {"model": "x"})
    assert client.calls == 1


@pytest.mark.asyncio
async def test_exhausting_all_attempts_on_persistent_429_raises():
    client = _ScriptedClient([_FakeResponse({}, 429) for _ in range(6)])
    with pytest.raises(RuntimeError, match="status 429"):
        await _post_with_retry(client, "/chat/completions", {"model": "x"}, max_attempts=6)
    assert client.calls == 6


@pytest.mark.asyncio
async def test_openrouter_retries_a_transient_429_before_falling_back(monkeypatch):
    """A transient blip must be absorbed by retrying the primary provider —
    not treated as an immediate excuse to fall through to OpenAI."""

    class _NeverCalledFallback:
        async def complete(self, model, prompt, system=""):
            raise AssertionError("fallback should not have been used — the primary provider recovered on retry")

    router = OpenRouterClient(api_key="key", fallback=_NeverCalledFallback())
    router._client = _ScriptedClient(
        [_FakeResponse({}, 429), _FakeResponse({"choices": [{"message": {"content": "hi"}}]}, 200)]
    )

    result = await router.complete("some-model", "prompt")
    assert result == "hi"


@pytest.mark.asyncio
async def test_openrouter_still_falls_back_once_retries_are_truly_exhausted(monkeypatch):
    class _RecordingFallback:
        def __init__(self):
            self.called = False

        async def complete(self, model, prompt, system=""):
            self.called = True
            return "fallback response"

    fallback = _RecordingFallback()
    router = OpenRouterClient(api_key="key", fallback=fallback)
    router._client = _ScriptedClient([_FakeResponse({}, 500) for _ in range(6)])

    result = await router.complete("some-model", "prompt")
    assert result == "fallback response"
    assert fallback.called is True


@pytest.mark.asyncio
async def test_openai_client_retries_transient_errors_too():
    client = OpenAIClient(api_key="key")
    client._client = _ScriptedClient(
        [_FakeResponse({}, 429), _FakeResponse({"choices": [{"message": {"content": "hi"}}]}, 200)]
    )
    result = await client.complete("gpt-4.1-mini", "prompt")
    assert result == "hi"
