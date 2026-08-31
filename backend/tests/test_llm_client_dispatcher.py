"""DispatcherLLMClient — routes every call to mock or real based on the
*live* runtime_settings flag (checked at call time, not baked in at
construction) so the UI's mock/real toggle actually takes effect without
restarting the backend. See app/routes/mock_mode.py for the guardrail that
keeps it from being switched to real with no provider configured."""

from app.matching.llm_client import (
    DispatcherLLMClient,
    LLMClient,
    MockLLMClient,
    build_llm_client,
)
from app.runtime_settings import set_use_mock_llm


class _FakeRealClient(LLMClient):
    async def complete(self, model: str, prompt: str, system: str = "") -> str:
        return "real response"

    async def embed(self, model: str, text: str) -> list[float]:
        return [1.0]


async def test_dispatcher_uses_mock_by_default():
    set_use_mock_llm(True)
    dispatcher = DispatcherLLMClient(mock_client=MockLLMClient(), real_client=_FakeRealClient())
    result = await dispatcher.complete("model", "prompt")
    assert result != "real response"


async def test_dispatcher_switches_to_real_when_flag_flips():
    dispatcher = DispatcherLLMClient(mock_client=MockLLMClient(), real_client=_FakeRealClient())
    set_use_mock_llm(False)
    try:
        assert await dispatcher.complete("model", "prompt") == "real response"
    finally:
        set_use_mock_llm(True)


async def test_dispatcher_falls_back_to_mock_if_no_real_client_even_when_flag_is_off():
    dispatcher = DispatcherLLMClient(mock_client=MockLLMClient(), real_client=None)
    set_use_mock_llm(False)
    try:
        result = await dispatcher.complete("model", "prompt")
        assert result != "real response"  # silently mock, not a crash
    finally:
        set_use_mock_llm(True)


def test_build_llm_client_always_returns_a_dispatcher_even_with_no_keys():
    client = build_llm_client(openrouter_key="", openai_key="")
    assert isinstance(client, DispatcherLLMClient)
    assert client.real_client is None


def test_build_llm_client_wires_a_real_client_when_a_key_is_present():
    client = build_llm_client(openrouter_key="sk-fake", openai_key="")
    assert isinstance(client, DispatcherLLMClient)
    assert client.real_client is not None
