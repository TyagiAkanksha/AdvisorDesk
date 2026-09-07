"""Failing (RED) tests for the groundedness harness (phase-7 task-02).

Task brief: `.superpowers/sdd/phase-7-evaluation/task-02-brief.md`, Steps 1-4.
Spec: advisordesk-prd.md §8.1 (eval file shape + expected outcomes), §10 Phase 7 (report
contents), §9.1 (the groundedness metric).

`app.eval.groundedness` does not exist yet: every test here is expected to fail at collection
(`ModuleNotFoundError`) until the implementer (a separate agent) creates
`app/eval/__init__.py`/`app/eval/groundedness.py` — that failure IS the RED evidence this file
exists to produce. The tests are written complete (never stubs) so the implementer can make them
pass without rewriting them.

Fakes are defined locally (`ScriptedEmbedder`, `ScriptedChatLLM`, `ScriptedJudge`) per
CONVENTIONS.md §10 / the test-author brief: no cross-test-file imports, never the real OpenAI
API. Content/chunk rows are seeded via direct ORM field setup (`test_retrieval.py`'s style, not
the real publish pipeline) so each chunk's embedding is an exact, known vector.

Vector construction: `_vector_at_cosine` generalizes `test_retrieval.py`'s helper of the same
name with an `axis` offset. `retrieve()` searches the WHOLE `chunks` table with no per-question
partition, and `test_report_arithmetic_matches_rows` below drives four different questions
through one `run_eval(...)` call sharing one seeded corpus — so each question gets its own
2-dimensional axis pair (0/1, 2/3, 4/5, 6/7). A vector built on axis `2*i` has cosine similarity
EXACTLY 0.0 (dot product across disjoint, all-zero coordinate slots) to any query vector built on
a different axis `2*j` — guaranteeing one question's seeded chunk can never leak into another
question's retrieval, regardless of the runtime `similarity_threshold` (`Settings.
similarity_threshold` defaults to 0.5; `cos_theta=0.9`/`0.95` below sit comfortably above it,
`0.0` sits comfortably below it, for any plausible threshold in `(0, 1)`).

Judgment calls (flagged for controller review — no cross-test-file precedent pins these, and the
brief's Interfaces block does not spell them out):

1. `cited_slugs`: assumed to mirror `app.services.chat.record_assistant_message`'s DB citation
   shape — one entry per chunk `retrieve()` actually returned (i.e. every chunk passed to
   `chat_llm.stream_answer`), NOT filtered by which `[n]` brackets the model's answer text
   happens to mention. This is the literal reading of the brief's "Consumes: ... recorded
   chunk-level citations" and of `record_assistant_message`'s own docstring ("this row stores
   chunk-level citations ... because the groundedness harness ... must know exactly which
   chunks supported the answer"). Every test below therefore controls `cited_slugs` purely via
   which chunks `retrieve()` finds (the seeded corpus + `ScriptedEmbedder` vectors), never via
   bracket syntax in the scripted answer text.
2. `refused`: the brief lists it as a THIRD, separately-ANDed condition alongside
   `retrieval_found=False` and "zero citations" in the uncovered verdict rule — implying it is
   not simply `not retrieval_found` restated. It is plausibly derived from retrieval facts
   (defense-in-depth, matching this codebase's general style) OR from the answer's own text
   (catching a model that hallucinates even when given zero sources). `test_uncovered_question_*`
   below construct BOTH signals to agree in every scenario (no chunk found + a refusal-worded
   answer for the "correct" case; a false-positive chunk found + a confident non-refusal answer
   for the "incorrect" case) so the tests pin the observable `refused`/`verdict` outcome without
   betting on which derivation the implementer picks.
3. `pct_fully_supported` is assumed computed over ANSWERABLE rows only (`fully_supported` is
   typed `bool | None`; uncovered rows' is `None`, i.e. not applicable) — matching the PRD §9.1
   goal ("% of answers fully supported by their cited chunks"). `refusal_correct`/`refusal_total`
   are assumed computed over the UNANSWERABLE (uncovered) rows only.
4. `verdict` is assumed to hold the literal strings `"PASS"`/`"FAIL"` (the brief's own casing).

CONVENTIONS.md §10: DB tests run against a throwaway Postgres schema when `TEST_DATABASE_URL` is
set, and are skipped by fixture name otherwise (`tests/conftest.py::pytest_collection_modifyitems`)
— every test here requests `db_session`, so the whole module skips cleanly without a DB.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from app.eval.groundedness import EvalReport, run_eval
from sqlalchemy.orm import Session

from app.models import Content
from app.models.chunks import Chunk
from app.rag.retrieval import RetrievedChunk

# Matches `Chunk.embedding`'s `Vector(1024)` column (`app/models/chunks.py`) and
# `Settings.embedding_dimensions`'s default, same as `test_retrieval.py`/`test_public_chat.py`.
_DIMS = 1024


def _vector_at_cosine(cos_theta: float, *, axis: int = 0, dims: int = _DIMS) -> list[float]:
    """A unit vector at cosine similarity `cos_theta` to axis-`axis`'s basis vector.

    `[0, ..., cos_theta, sin_theta, ..., 0]` (the pair at slots `axis`/`axis + 1`, zero
    everywhere else) has norm 1 for any `cos_theta` in `[-1, 1]`. Its dot product — and
    therefore its cosine similarity, since both vectors are unit-norm — with
    `_query_vector(axis)` (`cos_theta=1.0` on the SAME axis) is exactly `cos_theta`; its dot
    product with any `_query_vector`/chunk vector built on a DIFFERENT axis is exactly `0.0`
    (disjoint, all-zero coordinate slots) — see module docstring.
    """
    sin_theta = math.sqrt(1.0 - cos_theta * cos_theta)
    vector = [0.0] * dims
    vector[axis] = cos_theta
    vector[axis + 1] = sin_theta
    return vector


def _query_vector(axis: int = 0) -> list[float]:
    """The unit query vector for one question's dedicated axis (cosine 1.0 to itself)."""
    return _vector_at_cosine(1.0, axis=axis)


# ---------------------------------------------------------------------------
# Fakes: `Embedder`, `ChatLLM`, and `GroundednessJudge` seams (defined locally, per the brief).
# ---------------------------------------------------------------------------


@dataclass
class ScriptedEmbedder:
    """`Embedder`-shaped fake mapping exact question text to a pre-chosen vector.

    Unlike `test_retrieval.py`'s single-fixed-vector fake (fine there because only one query is
    ever embedded per test), `run_eval` embeds a DIFFERENT question per `retrieve()` call, and
    `test_report_arithmetic_matches_rows` below drives several questions through one shared
    corpus in a single `run_eval(...)` call — each needs its own vector. A question not in
    `vectors` raises `KeyError` (the plain dict lookup) rather than silently returning some
    default/zero vector that could mask a mismatched-question bug in a test.
    """

    vectors: dict[str, list[float]]
    calls: list[tuple[tuple[str, ...], str]] = field(default_factory=list)

    def embed_texts(
        self, texts: Sequence[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        self.calls.append((tuple(texts), input_type))
        return [self.vectors[text] for text in texts]


@dataclass
class ScriptedChatLLM:
    """`ChatLLM`-shaped fake yielding one pre-scripted answer string per exact question text.

    Yields the whole answer as a single fragment — valid per `ChatLLM.stream_answer`'s own
    contract ("concatenating every yielded fragment reconstructs the full answer text"; a
    single fragment trivially satisfies that) and irrelevant to what these tests check, which is
    the harness's handling of the FINAL accumulated answer text and the `sources` it was given,
    not token-by-token streaming mechanics (already covered by `test_public_chat.py`). Records
    every call's `(question, sources)` pair.
    """

    answers: dict[str, str]
    calls: list[tuple[str, tuple[RetrievedChunk, ...]]] = field(default_factory=list)

    def stream_answer(
        self, system: str, question: str, sources: Sequence[RetrievedChunk]
    ) -> Iterator[str]:
        self.calls.append((question, tuple(sources)))
        yield self.answers[question]


@dataclass
class ScriptedJudge:
    """`GroundednessJudge`-shaped fake: a claim is unsupported iff it contains one of
    `unsupported_markers`.

    Content-based (not call-order-based) scripting deliberately decouples these tests from
    `run_eval`'s exact sentence-splitting algorithm (unspecified by the brief): whatever
    sentences an answer gets sliced into, any sentence containing a marker substring is judged
    unsupported and every other sentence is judged supported — so the *outcome*
    (`fully_supported` True/False) is pinned without pinning the tokenizer itself. The default
    (`unsupported_markers=()`) is the brief's "all-true judge". Records every
    `(claim_text, chunk_texts)` call.
    """

    unsupported_markers: tuple[str, ...] = ()
    calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    def is_supported(self, claim_text: str, chunk_texts: Sequence[str]) -> bool:
        self.calls.append((claim_text, tuple(chunk_texts)))
        return not any(marker in claim_text for marker in self.unsupported_markers)


# ---------------------------------------------------------------------------
# DB seeding + YAML-fixture helpers.
# ---------------------------------------------------------------------------


def _add_content(session: Session, *, slug: str) -> Content:
    """Insert and flush a published, non-deleted `Content` row via direct field setup."""
    content = Content(
        title=f"Title for {slug}",
        slug=slug,
        body_md="body text, irrelevant to retrieval — chunks carry the retrievable text",
        status="published",
        is_deleted=False,
        published_at=datetime.now(UTC),
    )
    session.add(content)
    session.flush()
    return content


def _add_chunk(
    session: Session,
    content_id: uuid.UUID,
    *,
    text: str,
    cos_theta: float,
    axis: int = 0,
    chunk_index: int = 0,
) -> Chunk:
    """Insert and flush a `Chunk` row whose embedding has cosine similarity `cos_theta` to
    `_query_vector(axis)`.
    """
    chunk = Chunk(
        content_id=content_id,
        chunk_index=chunk_index,
        text=text,
        embedding=_vector_at_cosine(cos_theta, axis=axis),
    )
    session.add(chunk)
    session.flush()
    return chunk


def _write_questions_yaml(tmp_path: Path, questions: list[dict[str, object]]) -> Path:
    """Write `questions` (§8.1 shape) to a YAML file under `tmp_path`; return its path."""
    path = tmp_path / "eval_questions.yaml"
    path.write_text(yaml.safe_dump(questions, sort_keys=False))
    return path


# ---------------------------------------------------------------------------
# Step 1 tests.
# ---------------------------------------------------------------------------


def test_loads_eval_questions_yaml_matching_the_seed_shape(
    db_session: Session, tmp_path: Path
) -> None:
    """§8.1 shape: a YAML list of `{question, expected_slugs, answerable}` records — the exact
    shape `seed/eval_questions.yaml` (repo root) uses. One answerable record with a non-empty
    `expected_slugs`, one unanswerable record with `expected_slugs: []`; `run_eval` must load
    every record into one `EvalRow` apiece, carrying `question`/`answerable`/`expected_slugs`
    through unchanged, in file order.
    """
    q_answerable = "What is a Roth IRA conversion and how is it taxed?"
    q_unanswerable = "Can you help me set up an offshore trust in the Cayman Islands?"
    content = _add_content(db_session, slug="roth-ira-conversion-basics")
    _add_chunk(
        db_session,
        content.id,
        text="A Roth IRA conversion moves funds from a traditional IRA and is a taxable event.",
        cos_theta=0.95,
        axis=0,
    )
    questions_path = _write_questions_yaml(
        tmp_path,
        [
            {
                "question": q_answerable,
                "expected_slugs": ["roth-ira-conversion-basics"],
                "answerable": True,
            },
            {"question": q_unanswerable, "expected_slugs": [], "answerable": False},
        ],
    )
    embedder = ScriptedEmbedder(
        vectors={q_answerable: _query_vector(axis=0), q_unanswerable: _query_vector(axis=2)}
    )
    chat_llm = ScriptedChatLLM(
        answers={
            q_answerable: "A Roth IRA conversion is a taxable event.",
            q_unanswerable: "No published guidance covers this. Please ask the advisory team.",
        }
    )
    judge = ScriptedJudge()

    report = run_eval(
        db_session,
        embedder=embedder,
        chat_llm=chat_llm,
        judge=judge,
        questions_path=questions_path,
    )

    assert isinstance(report, EvalReport)
    assert len(report.rows) == 2
    assert [row.question for row in report.rows] == [q_answerable, q_unanswerable]
    assert [row.answerable for row in report.rows] == [True, False]
    assert list(report.rows[0].expected_slugs) == ["roth-ira-conversion-basics"]
    assert list(report.rows[1].expected_slugs) == []


def test_answerable_question_with_full_slug_coverage_and_supported_answer_passes(
    db_session: Session, tmp_path: Path
) -> None:
    """Brief Step 1, case 1: an answerable question whose retrieved/cited chunk covers the
    expected slug, judged fully supported by an all-true judge -> a PASS row, counted in
    `pct_fully_supported`.
    """
    question = "What is a Roth IRA conversion and how is it taxed?"
    content = _add_content(db_session, slug="roth-ira-conversion-basics")
    _add_chunk(
        db_session,
        content.id,
        text="Converting funds from a traditional IRA to a Roth IRA is a taxable event.",
        cos_theta=0.95,
    )
    questions_path = _write_questions_yaml(
        tmp_path,
        [
            {
                "question": question,
                "expected_slugs": ["roth-ira-conversion-basics"],
                "answerable": True,
            }
        ],
    )
    embedder = ScriptedEmbedder(vectors={question: _query_vector()})
    chat_llm = ScriptedChatLLM(
        answers={
            question: (
                "A Roth IRA conversion is a taxable event. "
                "The converted amount is added to your income for that year."
            )
        }
    )
    judge = ScriptedJudge()  # all-true

    report = run_eval(
        db_session,
        embedder=embedder,
        chat_llm=chat_llm,
        judge=judge,
        questions_path=questions_path,
    )

    assert len(report.rows) == 1
    row = report.rows[0]
    assert set(row.cited_slugs) == {"roth-ira-conversion-basics"}
    assert row.slugs_hit is True
    assert row.fully_supported is True
    assert row.verdict == "PASS"
    assert report.pct_fully_supported == 100.0


def test_answerable_question_missing_expected_slug_fails_despite_full_support(
    db_session: Session, tmp_path: Path
) -> None:
    """Brief Step 1, case 2: the slug check is independent of the support check. Retrieval
    finds ONLY a chunk belonging to a different, real published slug than the one
    `expected_slugs` names, so `cited_slugs` never contains the expected slug — even though an
    all-true judge marks the (wrong-article) answer fully supported, the row still FAILS.
    `pct_fully_supported` still counts the row as fully supported (`fully_supported` and
    `slugs_hit` are independent signals; only `verdict` combines them).
    """
    question = "What is a Roth IRA conversion and how is it taxed?"
    wrong_content = _add_content(db_session, slug="traditional-vs-roth-ira-basics")
    _add_chunk(
        db_session,
        wrong_content.id,
        text="Traditional and Roth IRAs differ mainly in when you pay income tax.",
        cos_theta=0.95,
    )
    questions_path = _write_questions_yaml(
        tmp_path,
        [
            {
                "question": question,
                "expected_slugs": ["roth-ira-conversion-basics"],
                "answerable": True,
            }
        ],
    )
    embedder = ScriptedEmbedder(vectors={question: _query_vector()})
    chat_llm = ScriptedChatLLM(
        answers={question: "Traditional and Roth IRAs differ mainly in when you pay income tax."}
    )
    judge = ScriptedJudge()  # all-true

    report = run_eval(
        db_session,
        embedder=embedder,
        chat_llm=chat_llm,
        judge=judge,
        questions_path=questions_path,
    )

    row = report.rows[0]
    assert "roth-ira-conversion-basics" not in set(row.cited_slugs)
    assert row.slugs_hit is False
    assert row.fully_supported is True
    assert row.verdict == "FAIL"
    assert report.pct_fully_supported == 100.0


def test_one_unsupported_sentence_marks_fully_supported_false(
    db_session: Session, tmp_path: Path
) -> None:
    """Brief Step 1, case 3: the judge is called per sentence against the union of the row's
    cited chunk texts; one sentence judged unsupported (the judge returns False exactly once)
    is enough to make the whole answer `fully_supported=False` -- and therefore FAIL the
    verdict, even though the expected slug WAS hit.
    """
    question = "What is a Roth IRA conversion and how is it taxed?"
    content = _add_content(db_session, slug="roth-ira-conversion-basics")
    chunk_text = "Converting funds from a traditional IRA to a Roth IRA is a taxable event."
    _add_chunk(db_session, content.id, text=chunk_text, cos_theta=0.95)
    questions_path = _write_questions_yaml(
        tmp_path,
        [
            {
                "question": question,
                "expected_slugs": ["roth-ira-conversion-basics"],
                "answerable": True,
            }
        ],
    )
    embedder = ScriptedEmbedder(vectors={question: _query_vector()})
    answer = (
        "Converting funds to a Roth IRA is a taxable event. "
        "UNSUPPORTED_CLAIM_MARKER the conversion also guarantees higher retirement income."
    )
    chat_llm = ScriptedChatLLM(answers={question: answer})
    judge = ScriptedJudge(unsupported_markers=("UNSUPPORTED_CLAIM_MARKER",))

    report = run_eval(
        db_session,
        embedder=embedder,
        chat_llm=chat_llm,
        judge=judge,
        questions_path=questions_path,
    )

    row = report.rows[0]
    assert row.slugs_hit is True
    assert row.fully_supported is False
    assert row.verdict == "FAIL"
    # The judge was called per sentence (at least the two this answer unambiguously contains,
    # split on ". "), and exactly one of those calls carried the unsupported marker.
    assert len(judge.calls) >= 2
    marker_calls = [claim for claim, _chunks in judge.calls if "UNSUPPORTED_CLAIM_MARKER" in claim]
    assert len(marker_calls) == 1
    # Every call is judged against the union of the row's cited chunk texts (this row has only
    # one cited chunk, but the union must still include it).
    for _claim, chunk_texts in judge.calls:
        assert chunk_text in chunk_texts


def test_uncovered_question_with_correct_refusal_counts_as_refusal_correct(
    db_session: Session, tmp_path: Path
) -> None:
    """Brief Step 1, case 4a: an uncovered question with no chunk anywhere near its query
    vector -- retrieval finds nothing, the model (correctly) refuses -- is `refusal_correct`
    and PASSes (PRD §8.1: `retrieval_found=false`, a refusal, no citations).
    """
    question = "What does the firm recommend about cryptocurrency staking rewards?"
    # Deliberately no chunk seeded anywhere: an empty `chunks` table clears no threshold for
    # ANY query, so retrieval finding nothing here does not depend on axis isolation at all.
    questions_path = _write_questions_yaml(
        tmp_path, [{"question": question, "expected_slugs": [], "answerable": False}]
    )
    embedder = ScriptedEmbedder(vectors={question: _query_vector()})
    chat_llm = ScriptedChatLLM(
        answers={question: "No published guidance covers this. Please ask the advisory team."}
    )
    judge = ScriptedJudge()

    report = run_eval(
        db_session,
        embedder=embedder,
        chat_llm=chat_llm,
        judge=judge,
        questions_path=questions_path,
    )

    row = report.rows[0]
    assert row.refused is True
    assert len(row.cited_slugs) == 0
    assert row.fully_supported is None
    assert row.verdict == "PASS"
    assert report.refusal_correct == 1
    assert report.refusal_total == 1


def test_uncovered_question_with_hallucinated_answer_counts_as_refusal_incorrect(
    db_session: Session, tmp_path: Path
) -> None:
    """Brief Step 1, case 4b: the eval file marks this question `answerable: false`, but a
    distractor chunk happens to clear the similarity threshold anyway (a retrieval false
    positive -- the real-world failure mode this check exists to catch), and the model answers
    from it confidently instead of refusing. Both the retrieval-found signal (a chunk WAS cited)
    and the answer's own non-refusal wording point the same way, so this counts as
    `refusal_correct`'s complement regardless of which signal `run_eval` bases `refused` on.
    """
    question = "Should I use a covered call options strategy to generate income on my portfolio?"
    distractor = _add_content(db_session, slug="dollar-cost-averaging-basics")
    _add_chunk(
        db_session,
        distractor.id,
        text="Dollar-cost averaging invests a fixed amount on a fixed schedule.",
        cos_theta=0.9,
    )
    questions_path = _write_questions_yaml(
        tmp_path, [{"question": question, "expected_slugs": [], "answerable": False}]
    )
    embedder = ScriptedEmbedder(vectors={question: _query_vector()})
    chat_llm = ScriptedChatLLM(
        answers={
            question: "Covered calls generate steady premium income with no meaningful downside."
        }
    )
    judge = ScriptedJudge()

    report = run_eval(
        db_session,
        embedder=embedder,
        chat_llm=chat_llm,
        judge=judge,
        questions_path=questions_path,
    )

    row = report.rows[0]
    assert row.refused is False
    assert len(row.cited_slugs) > 0
    assert row.verdict == "FAIL"
    assert report.refusal_correct == 0
    assert report.refusal_total == 1


def test_report_arithmetic_matches_rows(db_session: Session, tmp_path: Path) -> None:
    """Brief Step 1, case 5: `EvalReport`'s summary numbers must exactly match what a plain
    count over `report.rows` gives -- run four questions (two answerable, two uncovered) with
    known, mixed outcomes through ONE `run_eval(...)` call sharing one seeded corpus, each on
    its own isolated axis pair (module docstring), and check both the literal expected numbers
    AND a fresh recomputation from `rows` agree.
    """
    q_pass = "What is a Roth IRA conversion and how is it taxed?"
    q_fail_unsupported = "What's the difference between a traditional IRA and a Roth IRA?"
    q_refusal_correct = "What does the firm recommend about cryptocurrency staking rewards?"
    q_refusal_incorrect = "Should I use a covered call options strategy to generate income?"

    pass_content = _add_content(db_session, slug="roth-ira-conversion-basics")
    _add_chunk(
        db_session,
        pass_content.id,
        text="Converting funds from a traditional IRA to a Roth IRA is a taxable event.",
        cos_theta=0.95,
        axis=0,
    )
    fail_content = _add_content(db_session, slug="traditional-vs-roth-ira-basics")
    fail_chunk_text = "Traditional and Roth IRAs differ mainly in when you pay income tax."
    _add_chunk(db_session, fail_content.id, text=fail_chunk_text, cos_theta=0.95, axis=2)
    # axis=4 (q_refusal_correct): no chunk seeded near it at all.
    distractor_content = _add_content(db_session, slug="dollar-cost-averaging-basics")
    _add_chunk(
        db_session,
        distractor_content.id,
        text="Dollar-cost averaging invests a fixed amount on a fixed schedule.",
        cos_theta=0.9,
        axis=6,
    )

    questions_path = _write_questions_yaml(
        tmp_path,
        [
            {
                "question": q_pass,
                "expected_slugs": ["roth-ira-conversion-basics"],
                "answerable": True,
            },
            {
                "question": q_fail_unsupported,
                "expected_slugs": ["traditional-vs-roth-ira-basics"],
                "answerable": True,
            },
            {"question": q_refusal_correct, "expected_slugs": [], "answerable": False},
            {"question": q_refusal_incorrect, "expected_slugs": [], "answerable": False},
        ],
    )
    embedder = ScriptedEmbedder(
        vectors={
            q_pass: _query_vector(axis=0),
            q_fail_unsupported: _query_vector(axis=2),
            q_refusal_correct: _query_vector(axis=4),
            q_refusal_incorrect: _query_vector(axis=6),
        }
    )
    chat_llm = ScriptedChatLLM(
        answers={
            q_pass: "A Roth IRA conversion is a taxable event.",
            q_fail_unsupported: (
                "Traditional and Roth IRAs differ mainly in when you pay income tax. "
                "UNSUPPORTED_CLAIM_MARKER a Roth IRA also doubles your annual contribution limit."
            ),
            q_refusal_correct: "No published guidance covers this. Please ask the advisory team.",
            q_refusal_incorrect: (
                "Covered calls generate steady premium income with no meaningful downside."
            ),
        }
    )
    judge = ScriptedJudge(unsupported_markers=("UNSUPPORTED_CLAIM_MARKER",))

    report = run_eval(
        db_session,
        embedder=embedder,
        chat_llm=chat_llm,
        judge=judge,
        questions_path=questions_path,
    )

    assert len(report.rows) == 4
    by_question = {row.question: row for row in report.rows}
    assert by_question[q_pass].verdict == "PASS"
    assert by_question[q_fail_unsupported].verdict == "FAIL"
    assert by_question[q_fail_unsupported].slugs_hit is True
    assert by_question[q_fail_unsupported].fully_supported is False
    assert by_question[q_refusal_correct].verdict == "PASS"
    assert by_question[q_refusal_incorrect].verdict == "FAIL"

    answerable_rows = [row for row in report.rows if row.answerable]
    uncovered_rows = [row for row in report.rows if not row.answerable]
    assert len(answerable_rows) == 2
    assert len(uncovered_rows) == 2

    expected_pct = (
        100.0 * sum(1 for row in answerable_rows if row.fully_supported) / len(answerable_rows)
    )
    expected_refusal_correct = sum(1 for row in uncovered_rows if row.verdict == "PASS")

    assert report.pct_fully_supported == expected_pct == 50.0
    assert report.refusal_total == len(uncovered_rows) == 2
    assert report.refusal_correct == expected_refusal_correct == 1
