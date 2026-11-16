"""RED (anthropic-haiku Task D, test-author): `AnthropicJudge` + the `build_judge` seam.

Brief: `.superpowers/sdd/anthropic-haiku/brief.md` (Task D). Required (not yet existing) surfaces:

- `app.eval.anthropic_judge.AnthropicJudge` -- `__init__(*, client, model)` (keyword-only; NO
  temperature parameter), `from_settings(settings)`, and the same public methods as
  `OpenAIJudge` (`is_supported`, `is_answer_relevant`, `is_chunk_relevant`, `is_claim_covered`,
  `is_refusal`, `rank_chunk_relevance`) with identical reply-parsing semantics.
- `app.eval.judge_factory.build_judge(settings)` -- a new module (not groundedness.py, to avoid a
  groundedness <-> anthropic_judge import cycle): `AnthropicJudge.from_settings` when
  `settings.llm_provider == "anthropic"`, else `OpenAIJudge.from_settings`.

Pinned semantics (derived from `OpenAIJudge`, which never catches provider errors and treats an
empty reply as NO / unparsable):
- request kwargs: `model`, `max_tokens` (int > 0), `system` (str), `messages` (one user turn),
  `output_config == {"effort": "low"}`; NEVER `temperature`/`top_p`/`top_k`, never `thinking`.
- `anthropic.APIError` (and subclasses) propagates unchanged out of every method.
- `stop_reason == "refusal"` / no text block => treated as an empty reply (same as an empty
  OpenAI `content`): yes/no methods return False, `rank_chunk_relevance` returns None; no raise.
- The reply text is the concatenation of the text blocks' `.text`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

import anthropic
import httpx
import pytest
from openai import OpenAI

from app.config import Settings
from app.eval.anthropic_judge import AnthropicJudge
from app.eval.groundedness import OpenAIJudge
from app.eval.judge_factory import build_judge


@dataclass
class _Block:
    text: str
    type: str = "text"


@dataclass
class _Message:
    content: list[_Block]
    stop_reason: str = "end_turn"


@dataclass
class _Messages:
    reply: str | None
    stop_reason: str = "end_turn"
    error: Exception | None = None
    calls: list[dict[str, object]] = field(default_factory=list)

    def create(self, **kwargs: object) -> _Message:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        blocks = [] if self.reply is None else [_Block(text=self.reply)]
        return _Message(content=blocks, stop_reason=self.stop_reason)


@dataclass
class _Client:
    messages: _Messages


def _judge(
    reply: str | None, *, stop_reason: str = "end_turn", error: Exception | None = None
) -> tuple[AnthropicJudge, _Messages]:
    messages = _Messages(reply=reply, stop_reason=stop_reason, error=error)
    client = cast(anthropic.Anthropic, _Client(messages=messages))
    return AnthropicJudge(client=client, model="claude-haiku-5-5"), messages


# --- OpenAI-side twin, for "parses identically" comparisons ---------------------------------


@dataclass
class _OAMessage:
    content: str


@dataclass
class _OAChoice:
    message: _OAMessage


@dataclass
class _OACompletion:
    choices: list[_OAChoice]


@dataclass
class _OACompletions:
    reply: str

    def create(self, **kwargs: object) -> _OACompletion:
        return _OACompletion(choices=[_OAChoice(message=_OAMessage(content=self.reply))])


@dataclass
class _OAChat:
    completions: _OACompletions


@dataclass
class _OAClient:
    chat: _OAChat


def _openai_judge(reply: str) -> OpenAIJudge:
    client = _OAClient(chat=_OAChat(completions=_OACompletions(reply=reply)))
    return OpenAIJudge(client=cast(OpenAI, client), model="gpt-5.4")


_YES_NO_REPLIES = [
    "YES\nit is relevant",
    "yes",
    "  Yes \nreason",
    "NO\nnot relevant",
    "no",
    "",
    "Maybe\nunclear",
    "The answer is YES",  # does not START with yes on line 1 -> NO
]


def _call_yes_no(judge: object, method: str) -> bool:
    if method in ("is_supported", "is_claim_covered"):
        return cast(bool, getattr(judge, method)("a claim", ["chunk one", "chunk two"]))
    return cast(bool, getattr(judge, method)("a question?", "some text"))


_YES_NO_METHODS = [
    "is_supported",
    "is_answer_relevant",
    "is_chunk_relevant",
    "is_claim_covered",
    "is_refusal",
]


@pytest.mark.parametrize("method", _YES_NO_METHODS)
@pytest.mark.parametrize("reply", _YES_NO_REPLIES)
def test_yes_no_methods_parse_identically_to_openai_judge(method: str, reply: str) -> None:
    anthropic_judge, _ = _judge(reply)
    assert _call_yes_no(anthropic_judge, method) is _call_yes_no(_openai_judge(reply), method)


def test_yes_no_methods_have_the_expected_truth_values() -> None:
    yes_judge, _ = _judge("YES\nreason")
    no_judge, _ = _judge("NO\nreason")
    for method in _YES_NO_METHODS:
        assert _call_yes_no(yes_judge, method) is True
        assert _call_yes_no(no_judge, method) is False


_RANK_REPLIES = [
    '[{"index": 0, "relevant": true}, {"index": 1, "relevant": false}]',
    '```json\n[{"index": 1, "relevant": false}, {"index": 0, "relevant": true}]\n```',
    '```\n[{"index": 0, "relevant": true}, {"index": 1, "relevant": true}]\n```',
    "not json",
    '[{"index": 0, "relevant": true}]',  # wrong length
    '[{"index": 0, "relevant": true}, {"index": 0, "relevant": false}]',  # duplicate
    '[{"index": 0, "relevant": true}, {"index": 5, "relevant": false}]',  # out of range
    '[{"index": 0, "relevant": "yes"}, {"index": 1, "relevant": false}]',  # non-bool
    '{"index": 0}',  # not a list
    "",
]


@pytest.mark.parametrize("reply", _RANK_REPLIES)
def test_rank_chunk_relevance_parses_identically_to_openai_judge(reply: str) -> None:
    anthropic_judge, _ = _judge(reply)
    chunks = ["first chunk", "second chunk"]
    assert anthropic_judge.rank_chunk_relevance("q?", chunks) == _openai_judge(
        reply
    ).rank_chunk_relevance("q?", chunks)


def test_rank_chunk_relevance_empty_chunks_returns_empty_list_without_a_call() -> None:
    judge, messages = _judge("irrelevant")
    assert judge.rank_chunk_relevance("q?", []) == []
    assert messages.calls == []


def test_rank_chunk_relevance_returns_expected_verdicts() -> None:
    judge, _ = _judge('[{"index": 0, "relevant": true}, {"index": 1, "relevant": false}]')
    assert judge.rank_chunk_relevance("q?", ["a", "b"]) == [True, False]


# --- request shape --------------------------------------------------------------------------


def _all_calls() -> list[dict[str, object]]:
    """One recorded request from every public judge method."""
    out: list[dict[str, object]] = []
    for method in _YES_NO_METHODS:
        judge, messages = _judge("YES\nok")
        _call_yes_no(judge, method)
        out.extend(messages.calls)
    judge, messages = _judge('[{"index": 0, "relevant": true}]')
    judge.rank_chunk_relevance("q?", ["a"])
    out.extend(messages.calls)
    return out


def test_every_request_has_model_max_tokens_system_user_message_and_low_effort() -> None:
    calls = _all_calls()
    assert len(calls) == 6
    for call in calls:
        assert call["model"] == "claude-haiku-5-5"
        max_tokens = call["max_tokens"]
        assert isinstance(max_tokens, int) and not isinstance(max_tokens, bool) and max_tokens > 0
        system = call["system"]
        assert isinstance(system, str) and system.strip()
        messages = call["messages"]
        assert isinstance(messages, list) and len(messages) == 1
        assert messages[0]["role"] == "user"
        assert isinstance(messages[0]["content"], str) and messages[0]["content"].strip()
        assert call["output_config"] == {"effort": "low"}


def test_no_sampling_parameter_or_thinking_key_is_ever_sent() -> None:
    for call in _all_calls():
        for forbidden in ("temperature", "top_p", "top_k", "thinking"):
            assert forbidden not in call


def test_system_prompt_and_user_message_match_the_openai_judge_prompts() -> None:
    """Same rubric text as the OpenAI judge: the claim and sources reach the user turn."""
    judge, messages = _judge("YES")
    judge.is_supported("the CLAIM-TEXT", ["SOURCE-ONE", "SOURCE-TWO"])
    user = messages.calls[0]["messages"][0]["content"]  # type: ignore[index]
    assert "the CLAIM-TEXT" in user and "SOURCE-ONE" in user and "SOURCE-TWO" in user


def test_constructor_takes_no_temperature() -> None:
    with pytest.raises(TypeError):
        AnthropicJudge(
            client=cast(anthropic.Anthropic, _Client(_Messages("x"))), model="m", temperature=0.0
        )  # type: ignore[call-arg]  # noqa: E501


# --- errors / refusals ----------------------------------------------------------------------


def _api_error() -> anthropic.APIError:
    return anthropic.APIConnectionError(request=httpx.Request("POST", "https://x.invalid/v1"))


@pytest.mark.parametrize("method", _YES_NO_METHODS)
def test_api_error_propagates_from_yes_no_methods(method: str) -> None:
    error = _api_error()
    judge, _ = _judge("YES", error=error)
    with pytest.raises(anthropic.APIError) as excinfo:
        _call_yes_no(judge, method)
    assert excinfo.value is error


def test_api_error_propagates_from_rank_chunk_relevance() -> None:
    judge, _ = _judge("[]", error=_api_error())
    with pytest.raises(anthropic.APIError):
        judge.rank_chunk_relevance("q?", ["a"])


@pytest.mark.parametrize("method", _YES_NO_METHODS)
def test_refusal_stop_reason_is_an_empty_reply_so_false(method: str) -> None:
    # Even if a text block were present, a refusal is a failed judgement, never a YES.
    judge, _ = _judge("YES", stop_reason="refusal")
    assert _call_yes_no(judge, method) is False


def test_refusal_stop_reason_makes_rank_chunk_relevance_none() -> None:
    judge, _ = _judge('[{"index": 0, "relevant": true}]', stop_reason="refusal")
    assert judge.rank_chunk_relevance("q?", ["a"]) is None


def test_reply_with_no_text_block_is_treated_as_empty() -> None:
    judge, _ = _judge(None)
    assert judge.is_answer_relevant("q?", "a") is False
    assert judge.rank_chunk_relevance("q?", ["a"]) is None


def test_multiple_text_blocks_are_concatenated() -> None:
    messages = _Messages(reply=None)

    def create(**kwargs: object) -> _Message:
        messages.calls.append(kwargs)
        return _Message(content=[_Block(text="YE"), _Block(text="S\nreason")])

    messages.create = create  # type: ignore[method-assign]
    judge = AnthropicJudge(
        client=cast(anthropic.Anthropic, _Client(messages=messages)), model="claude-haiku-5-5"
    )
    assert judge.is_answer_relevant("q?", "a") is True


# --- from_settings --------------------------------------------------------------------------


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"llm_provider": "anthropic", "judge_model": "claude-haiku-5-5"}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_from_settings_uses_anthropic_key_judge_model_and_retry_budget() -> None:
    settings = _settings(anthropic_api_key="sk-ant-test-key", judge_max_retries=7)
    judge = AnthropicJudge.from_settings(settings)
    assert isinstance(judge, AnthropicJudge)
    assert judge._model == "claude-haiku-5-5"  # noqa: SLF001
    client = judge._client  # noqa: SLF001
    assert isinstance(client, anthropic.Anthropic)
    assert client.api_key == "sk-ant-test-key"
    assert client.max_retries == 7


def test_from_settings_empty_key_falls_back_to_unset_placeholder() -> None:
    judge = AnthropicJudge.from_settings(_settings(anthropic_api_key=""))
    assert judge._client.api_key == "unset"  # noqa: SLF001


def test_from_settings_does_not_use_the_openai_key() -> None:
    judge = AnthropicJudge.from_settings(
        _settings(anthropic_api_key="sk-ant-real", openai_api_key="sk-openai-other")
    )
    assert judge._client.api_key == "sk-ant-real"  # noqa: SLF001


def test_from_settings_uses_settings_judge_model_verbatim() -> None:
    judge = AnthropicJudge.from_settings(_settings(judge_model="claude-some-other"))
    assert judge._model == "claude-some-other"  # noqa: SLF001


# --- build_judge ----------------------------------------------------------------------------


def test_build_judge_returns_anthropic_judge_for_anthropic_provider() -> None:
    judge = build_judge(_settings(anthropic_api_key="sk-ant-x"))
    assert isinstance(judge, AnthropicJudge)


@pytest.mark.parametrize("provider", ["openai", "nvidia"])
def test_build_judge_returns_openai_judge_otherwise(provider: str) -> None:
    judge = build_judge(
        Settings(llm_provider=provider, openai_api_key="sk-o", nvidia_api_key="nv-x")  # type: ignore[arg-type]
    )
    assert isinstance(judge, OpenAIJudge)


def test_build_judge_default_settings_is_openai_judge() -> None:
    assert isinstance(build_judge(Settings()), OpenAIJudge)
