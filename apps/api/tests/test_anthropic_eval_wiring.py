"""RED (anthropic-haiku Task H, test-author): no OpenAI-compatible client may be built under
`LLM_PROVIDER=anthropic`, and the eval entry points must go through the provider factories.

- `OpenAICompatibleChatLLM` / `OpenAICompatibleAgentLLM` / `OpenAIJudge` `.from_settings` raise
  `ValueError` (mentions "anthropic", never the key) under anthropic, so an Anthropic key can
  never be sent to an OpenAI-compatible base URL. openai/nvidia unchanged; the embedder is exempt.
- `app/eval/groundedness.py` and `app/eval/agent_suite.py` use `build_chat_llm` / `build_agent_llm`.
- Repo scan: only the three factory modules may call the OpenAI-compatible `from_settings`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.agent.anthropic_llm import AnthropicAgentLLM
from app.agent.llm import OpenAICompatibleAgentLLM
from app.agent.llm_factory import build_agent_llm
from app.config import Settings
from app.eval.anthropic_judge import AnthropicJudge
from app.eval.groundedness import OpenAIJudge
from app.eval.judge_factory import build_judge
from app.rag.anthropic_chat import AnthropicChatLLM
from app.rag.chat_provider import build_chat_llm
from app.rag.embeddings import OpenAICompatibleEmbedder
from app.rag.synthesis import OpenAICompatibleChatLLM

_KEY = "sk-ant-wiring-secret-value"
_APP = Path(__file__).resolve().parent.parent / "app"
_BUILDERS = [OpenAICompatibleChatLLM, OpenAICompatibleAgentLLM, OpenAIJudge]


def _anthropic() -> Settings:
    return Settings(llm_provider="anthropic", anthropic_api_key=_KEY, openai_api_key="sk-openai-x")


@pytest.mark.parametrize("cls", _BUILDERS, ids=lambda c: c.__name__)
def test_openai_compatible_from_settings_refuses_anthropic(cls: type) -> None:
    with pytest.raises(ValueError, match="anthropic") as exc:
        cls.from_settings(_anthropic())
    assert _KEY not in str(exc.value)


@pytest.mark.parametrize("cls", _BUILDERS, ids=lambda c: c.__name__)
@pytest.mark.parametrize("provider", ["openai", "nvidia"])
def test_openai_compatible_from_settings_still_works(cls: type, provider: str) -> None:
    settings = Settings(llm_provider=provider, openai_api_key="o", nvidia_api_key="n")  # type: ignore[arg-type]
    assert isinstance(cls.from_settings(settings), cls)


def test_factories_still_return_anthropic_classes() -> None:
    settings = _anthropic()
    assert isinstance(build_chat_llm(settings), AnthropicChatLLM)
    assert isinstance(build_agent_llm(settings), AnthropicAgentLLM)
    assert isinstance(build_judge(settings), AnthropicJudge)


def test_embedder_unaffected_under_anthropic() -> None:
    embedder = OpenAICompatibleEmbedder.from_settings(_anthropic())
    assert isinstance(embedder, OpenAICompatibleEmbedder)


def test_groundedness_cli_uses_chat_factory() -> None:
    src = (_APP / "eval" / "groundedness.py").read_text()
    assert "OpenAICompatibleChatLLM.from_settings(" not in src
    assert "build_chat_llm(" in src


def test_agent_suite_uses_agent_factory() -> None:
    src = (_APP / "eval" / "agent_suite.py").read_text()
    assert "OpenAICompatibleAgentLLM.from_settings(" not in src
    assert "build_agent_llm(" in src


def test_only_factory_modules_call_openai_compatible_from_settings() -> None:
    pattern = re.compile(
        r"\b(OpenAICompatibleChatLLM|OpenAICompatibleAgentLLM|OpenAIJudge)\.from_settings\("
    )
    allowed = {
        Path("rag/chat_provider.py"),
        Path("agent/llm_factory.py"),
        Path("eval/judge_factory.py"),
    }
    offenders: set[Path] = set()
    for path in _APP.rglob("*.py"):
        rel = path.relative_to(_APP)
        for line in path.read_text().splitlines():
            code = line.split("#", 1)[0]
            stripped = code.strip()
            if stripped.startswith(('"', "'", "`")) or "`" in code:
                continue  # docstring / prose mention
            if pattern.search(code):
                offenders.add(rel)
    assert offenders - allowed == set(), sorted(str(p) for p in offenders - allowed)
