"""P7 remediation (fresh-review R3-2/I-2) — the OpenAI-provider credential path for
`app.agent.llm.OpenAICompatibleAgentLLM` (the admin agent panel's `/agent/chat` live provider-key
path), previously untested.

`tests/test_openai_chat_llm_client.py` covers the SYNTHESIS chat client's (`app.rag.synthesis.
OpenAICompatibleChatLLM`) `from_settings` key-resolution under `llm_provider="openai"` — but
`OpenAICompatibleAgentLLM.from_settings` is a SEPARATE implementation (same shape, different
method body, different class): every existing test that exercises it
(`tests/test_agent_llm_client.py`) pins `llm_provider="nvidia"` explicitly, so nothing proved the
admin agent panel actually authenticates with the OpenAI key under the new default provider. If
`OpenAICompatibleAgentLLM.from_settings` were ever edited to always read `nvidia_api_key`
regardless of `llm_provider` (a bad merge, a copy-paste from an nvidia-only helper), `/agent/chat`
would silently try to authenticate to `https://api.openai.com/v1` with an `"unset"` placeholder
key and fail every request in production — exactly the class of outage task 6R-14 was itself a
response to — and nothing in the suite would have caught it.

Near-verbatim port of `tests/test_openai_chat_llm_client.py`'s own
`test_from_settings_uses_the_openai_key_when_provider_is_openai` onto the agent client, for
symmetry with that file's existing naming convention. Deliberately DB-less, no network
(CONVENTIONS.md §10) — `from_settings` only inspects `Settings`/constructs an `openai.OpenAI`
client, it never makes a request.
"""

from __future__ import annotations

from app.agent.llm import OpenAICompatibleAgentLLM
from app.config import Settings


def test_from_settings_uses_the_openai_key_when_provider_is_openai() -> None:
    """The core R3-2 pin: under the default `llm_provider="openai"`, `from_settings` must build
    the client with `settings.openai_api_key` — NOT `settings.nvidia_api_key` — mirroring
    `test_openai_chat_llm_client.py::test_from_settings_uses_the_openai_key_when_provider_is_openai`
    exactly, for the sibling agent-chat client."""
    settings = Settings(
        llm_provider="openai",
        openai_api_key="sk-test-openai-key",
        nvidia_api_key="nvapi-should-not-be-used",
        chat_model="gpt-4o-mini",
    )

    agent_llm = OpenAICompatibleAgentLLM.from_settings(settings)

    assert agent_llm._client.api_key == "sk-test-openai-key"
    assert agent_llm._model == "gpt-4o-mini"


def test_from_settings_falls_back_to_unset_api_key_when_openai_api_key_is_empty() -> None:
    """Boot-safety symmetry (mirrors `test_openai_chat_llm_client.py`'s identically-named test):
    an empty `openai_api_key` under the default `llm_provider="openai"` must not crash
    `from_settings` — the `openai` SDK raises at *construction* time for a falsy `api_key` with
    no `OPENAI_API_KEY` env var either, which would crash `app.main`'s module-level wiring on
    every offline dev boot."""
    settings = Settings(llm_provider="openai", openai_api_key="")

    agent_llm = OpenAICompatibleAgentLLM.from_settings(settings)

    assert agent_llm._client.api_key == "unset"
