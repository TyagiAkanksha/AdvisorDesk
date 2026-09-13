"""RED (phase-9 task-05d, test-author): ruling 4 -- the judge's temperature becomes optional and
overridable.

Task brief: `.superpowers/sdd/phase-9-eval-data-loop/task-05d-brief.md`, Ruling 4. `Settings`
does not have a `judge_temperature` field yet; `OpenAIJudge.__init__` does not accept a
`temperature` keyword yet; `app.eval.judge_scorecard`'s CLI does not have `--judge-model`/
`--judge-temperature` flags yet -- every test below that touches one of those three surfaces is
genuinely RED (raises `AttributeError`/`TypeError`/`SystemExit` rather than failing a plain
assertion).

Interface assumptions this file pins (the brief leaves the exact shape to the implementer, so
these are the test-author's documented, minimal choices -- mirroring existing naming exactly):

- `OpenAIJudge.__init__` gains a `temperature: float | None = 0.0` keyword-only parameter
  alongside the existing `client`/`model` ones, defaulting to the SAME value
  `Settings.judge_temperature`'s own default will be (ruling 4 item 1) -- stored as `self.
  _temperature`, mirroring the existing `self._model` private-attribute convention (pinned
  today by `tests/test_eval_metrics_fix_round1.py`'s own
  `test_run_from_cli_builds_the_judge_from_judge_model_and_forwards_it_as_metrics_judge`, which
  already reads `getattr(captured["judge"], "_model", None)`).
- The fake-OpenAI-client pattern (`_FakeMessage`/`_FakeChoice`/`_FakeCompletion`/
  `_FakeCompletions`/`_FakeChat`/`_FakeOpenAIClient`) is copied from
  `tests/test_eval_metrics_fix_round1.py`/`tests/test_eval_refusal_semantics.py`, widened (like
  the latter) to RECORD every call's kwargs rather than discard them, since these tests must
  assert whether `temperature` was sent at all.
- The CLI-wiring test (case c) does not assume whether `judge_scorecard._run_from_cli` builds its
  judge via `OpenAIJudge.from_settings(...)` or a direct `OpenAIJudge(...)` call once
  `--judge-model`/`--judge-temperature` are wired in -- it only assumes the constructed judge is
  the exact object passed as `score_judge`'s first argument (true today, per `_run_from_cli`'s
  existing body), and inspects that object's own `_model`/`_temperature` state afterward. This
  keeps the test honest about the CONTRACT ("the flags reach the constructed judge") without
  locking in one particular wiring shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from openai import OpenAI

from app.config import Settings
from app.eval.groundedness import OpenAIJudge
from app.eval.judge_scorecard import JudgeScorecard, SpotCheck, _run_from_cli

# --- the fake-OpenAI-client pattern, copied from tests/test_eval_metrics_fix_round1.py /
# tests/test_eval_refusal_semantics.py (widened to record kwargs, per that second file) ---------


@dataclass
class _FakeMessage:
    content: str


@dataclass
class _FakeChoice:
    message: _FakeMessage


@dataclass
class _FakeCompletion:
    choices: list[_FakeChoice]


@dataclass
class _FakeCompletions:
    reply: str
    calls: list[dict[str, object]] = field(default_factory=list)

    def create(self, **kwargs: object) -> _FakeCompletion:
        self.calls.append(kwargs)
        return _FakeCompletion(choices=[_FakeChoice(message=_FakeMessage(content=self.reply))])


@dataclass
class _FakeChat:
    completions: _FakeCompletions


@dataclass
class _FakeOpenAIClient:
    """Structurally satisfies the one `client.chat.completions.create(...)` call `OpenAIJudge`
    makes -- never a real `OpenAI` instance, `cast` at each call site tells mypy this is
    deliberate (mirrors `tests/test_eval_metrics_fix_round1.py`'s own `_FakeOpenAIClient`).
    """

    chat: _FakeChat


def _fake_client(reply: str) -> tuple[_FakeOpenAIClient, _FakeCompletions]:
    completions = _FakeCompletions(reply=reply)
    return _FakeOpenAIClient(chat=_FakeChat(completions=completions)), completions


# --- (a) temperature 0 is sent by default, on both a standalone call site (is_supported) and
# the shared _ask call site five other judge methods reuse (rank_chunk_relevance) -------------


def test_default_judge_temperature_zero_is_sent_on_every_judge_call() -> None:
    """Ruling 4 item 1's default (`judge_temperature: float | None = 0.0`) must still send
    `temperature=0` when the caller does not override it -- pinned for `is_supported` (its own
    standalone `chat.completions.create` call) and `rank_chunk_relevance` (routed through the
    shared `_ask` helper five other judge methods also use), the two distinct call shapes in
    `OpenAIJudge`. NOT genuinely RED: both call sites already hard-code `temperature=0` today, so
    this passes now and must keep passing once that literal becomes `self._temperature`.
    """
    client, completions = _fake_client("YES\nfully supported")
    judge = OpenAIJudge(client=cast(OpenAI, client), model="gpt-5.4")  # temperature omitted
    judge.is_supported("claim", ["chunk"])
    assert completions.calls[-1]["temperature"] == 0

    client2, completions2 = _fake_client('[{"index": 0, "relevant": true}]')
    judge2 = OpenAIJudge(client=cast(OpenAI, client2), model="gpt-5.4")  # temperature omitted
    judge2.rank_chunk_relevance("question?", ["chunk"])
    assert completions2.calls[-1]["temperature"] == 0


# --- (b) no `temperature` key at all when judge_temperature=None -----------------------------


def test_none_judge_temperature_omits_the_temperature_key_on_every_judge_call() -> None:
    """Ruling 4 item 2: a model that rejects `temperature` (the brief's `gpt-5.6-terra`/`-luna`/
    `-sol`, `gpt-5`, `gpt-5.5` account probe) must be usable by omitting the parameter entirely,
    not by sending some sentinel value -- pinned for the same two call sites as the default-value
    test above. Genuinely RED now: `OpenAIJudge.__init__` does not accept a `temperature` keyword
    at all yet, so this raises `TypeError` at construction.
    """
    client, completions = _fake_client("YES\nfully supported")
    judge = OpenAIJudge(client=cast(OpenAI, client), model="gpt-5.4", temperature=None)
    judge.is_supported("claim", ["chunk"])
    assert "temperature" not in completions.calls[-1]

    client2, completions2 = _fake_client('[{"index": 0, "relevant": true}]')
    judge2 = OpenAIJudge(client=cast(OpenAI, client2), model="gpt-5.4", temperature=None)
    judge2.rank_chunk_relevance("question?", ["chunk"])
    assert "temperature" not in completions2.calls[-1]


# --- (c) the CLI's --judge-model/--judge-temperature flags reach the constructed judge --------


def test_cli_judge_model_and_temperature_flags_reach_the_constructed_judge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ruling 4 item 3: `judge_scorecard`'s CLI gains `--judge-model MODEL` and
    `--judge-temperature VALUE` (the literal `none` parsing to Python `None`), and whatever judge
    `_run_from_cli` builds from them must actually carry those values through to the object
    `score_judge` scores with -- `score_judge` itself is monkeypatched to a recording stub (never
    called for real, so no OpenAI network access happens) purely to capture that object; `--labels`
    points at an empty worksheet so no DB/network is needed either. Genuinely RED now: `--judge-
    model`/`--judge-temperature` are not recognised flags yet, so `argparse` raises `SystemExit`
    before any of this logic runs.
    """
    captured: dict[str, object] = {}

    def recording_score_judge(judge: object, labels: object, **kwargs: object) -> JudgeScorecard:
        captured["judge"] = judge
        return JudgeScorecard(
            labelled=0,
            agreement=None,
            kappa=None,
            self_consistency=None,
            repeats=3,
            spot_check=SpotCheck(sampled=0, position_consistency=None, verbosity_consistency=None),
        )

    monkeypatch.setattr("app.eval.judge_scorecard.score_judge", recording_score_judge)

    labels_path = tmp_path / "judge_labels.yaml"
    labels_path.write_text("[]\n", encoding="utf-8")

    _run_from_cli(
        [
            "--labels",
            str(labels_path),
            "--judge-model",
            "gpt-5.6-terra",
            "--judge-temperature",
            "none",
        ]
    )

    judge = captured.get("judge")
    assert judge is not None, "score_judge was never called -- no judge was constructed/scored"
    assert getattr(judge, "_model", None) == "gpt-5.6-terra"
    assert getattr(judge, "_temperature", None) is None


# --- (d) Settings() still constructs with no env (the zero-env rule) --------------------------


def test_settings_constructs_with_zero_env_including_judge_temperature_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ruling 4 item 1's zero-env rule: `Settings()` must still construct with no relevant env
    vars set, and the new `judge_temperature` field defaults to `0.0` -- mirrors the pre-existing
    zero-env pins in `tests/test_config.py`/`tests/test_llm_provider_config.py` for the other
    settings fields. Genuinely RED now: `Settings` has no `judge_temperature` attribute yet, so
    this raises `AttributeError`.
    """
    for name in ("JUDGE_TEMPERATURE", "JUDGE_MODEL", "CHAT_MODEL"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings()

    assert settings.judge_temperature == 0.0


# --- fix wave D1: judge_max_retries is the judge client's OWN retry budget ---------------------


def test_judge_max_retries_defaults_to_twelve_and_is_used_not_embedding_max_retries() -> None:
    """Fix wave D1 (t03 review, the 30k-TPM incident's proper fix): `judge_max_retries` gives the
    judge client its own, correctly-named retry budget instead of reusing `embedding_max_retries`
    (task 09's incident needed `EMBEDDING_MAX_RETRIES=12` as an env override to survive the org's
    judge rate limit -- discoverable only by reading `OpenAIJudge.from_settings`'s source). The
    zero-env default is `12`, the incident's own established headroom; giving the two settings
    DIFFERENT values and reading `OpenAIJudge`'s constructed client back proves `from_settings`
    wires `judge_max_retries`, not `embedding_max_retries`.
    """
    settings = Settings()
    assert settings.judge_max_retries == 12

    settings = Settings(judge_max_retries=7, embedding_max_retries=3)
    judge = OpenAIJudge.from_settings(settings)

    assert judge._client.max_retries == 7
