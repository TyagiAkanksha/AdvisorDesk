---
id: p9-t03
phase: phase-9-eval-data-loop
depends_on: [p9-t01]
status: todo
spec: docs/plans/phase-9-eval-data-loop/DESIGN.md
review: opus
---

# Task 03 — Eval runs become data: `services/eval_runs.py`, harness CLI, `compare_runs`

## Goal

Every harness run writes rows, and any two runs can be diffed. `app/services/eval_runs.py` gains
`corpus_fingerprint`, `record_run`, `latest_runs` and `compare_runs` — **`compare_runs` is the one
thing DESIGN never cuts**: it is the evidence behind "validated before acceptance".
`app/eval/groundedness.py` keeps `run_eval` pure and grows a real CLI
(`--label/--questions/--no-persist/--compare-to/--runs`) that persists by default and prints a
3-run stability block. The phase-7 stdout (per-question table + `groundedness: …` summary line) is
byte-identical on the default path — the README and task 09 both depend on that line.

## Context (read ONLY these)

- `docs/plans/phase-9-eval-data-loop/DESIGN.md` §B1, §B3, §"Verification".
- `docs/plans/phase-9-eval-data-loop/00-INDEX.md` §"Global Constraints" (import-linter, judge
  determinism, zero-env settings).
- `apps/api/app/eval/groundedness.py` — the whole file (423 lines): `EvalRow` (73-84),
  `EvalReport` (87-94), `_EvalQuestion` (97-103), `_evaluate_question` (241-294), `_build_report`
  (297-315), `run_eval` (318-362), `_print_table` (365-380), `_run_from_cli` (383-418).
- `apps/api/app/models/eval.py` (task 01) — `EvalRun`/`EvalResult` columns.
- `apps/api/app/services/chat.py:30-61` — the structural-`Protocol` seam pattern this task copies
  (read-only `@property` members so a frozen dataclass satisfies it).
- `apps/api/app/services/queries.py` — `active_select` (the define-once soft-delete filter).
- `apps/api/pyproject.toml` `[tool.importlinter]` — "app.services imports only app.models and
  app.config": `app.services.eval_runs` must therefore NOT import `app.eval`.
- `apps/api/tests/test_groundedness.py` — the fake seams (`ScriptedEmbedder`/`ScriptedChatLLM`/
  `ScriptedJudge`, lines 111-174) and `_write_questions_yaml` (220-224); this task must leave
  every test in it green.
- `docs/plans/phase-7-evaluation/verification-record.md` §1 — the exact stdout table this task
  must not disturb.

## Files

**Create**
- `apps/api/app/services/eval_runs.py`
- `apps/api/tests/test_eval_runs_service.py`
- `apps/api/tests/test_groundedness_cli.py`

**Modify**
- `apps/api/app/eval/groundedness.py`

## Interfaces

### `app/services/eval_runs.py` (exact signatures)

```python
class EvalRowLike(Protocol):
    """The subset of `app.eval.groundedness.EvalRow`'s shape this module persists.

    Structural, read-only `@property` members — the same seam pattern
    `app.services.chat.RetrievedChunkLike` uses, and for the same reason: the import-linter
    contract "app.services imports only app.models and app.config" forbids importing
    `app.eval` from here, and `EvalRow` is a frozen dataclass that satisfies this by shape.
    """

    @property
    def question(self) -> str: ...
    @property
    def question_class(self) -> str | None: ...
    @property
    def persona(self) -> str | None: ...
    @property
    def answerable(self) -> bool: ...
    @property
    def expected_slugs(self) -> Sequence[str]: ...
    @property
    def cited_slugs(self) -> Sequence[str]: ...
    @property
    def slugs_hit(self) -> bool: ...
    @property
    def fully_supported(self) -> bool | None: ...
    @property
    def refused(self) -> bool: ...
    @property
    def verdict(self) -> str: ...
    @property
    def top_similarity(self) -> float | None: ...
    @property
    def answer_text(self) -> str: ...
    @property
    def metrics(self) -> dict[str, object] | None: ...


class EvalReportLike(Protocol):
    @property
    def rows(self) -> Sequence[EvalRowLike]: ...
    @property
    def pct_fully_supported(self) -> float: ...
    @property
    def refusal_correct(self) -> int: ...
    @property
    def refusal_total(self) -> int: ...


@dataclass(frozen=True)
class CorpusFingerprint:
    """Identifies the corpus a run measured (DESIGN §B1/§D: `Content.updated_at` is stamped on
    every write, so no corpus-version column is needed)."""

    content_count: int
    chunk_count: int
    max_updated_at: datetime | None
    digest: str


@dataclass(frozen=True)
class RunDiff:
    """`compare_runs`' answer, joined on question text."""

    before_id: uuid.UUID
    after_id: uuid.UUID
    regressions: list[str]    # questions that went PASS -> FAIL
    improvements: list[str]   # FAIL -> PASS
    unchanged: list[str]      # same verdict in both
    added: list[str]          # present only in `after`
    removed: list[str]        # present only in `before`
    pct_delta: float          # after.pct_fully_supported - before.pct_fully_supported


def corpus_fingerprint(session: Session) -> CorpusFingerprint: ...


def record_run(
    session: Session,
    report: EvalReportLike,
    *,
    label: str,
    kind: str = "answer",
    embedding_model: str,
    chat_model: str,
    judge_model: str,
    similarity_threshold: float,
    retrieval_k: int,
    git_sha: str = "",
) -> EvalRun: ...


def latest_runs(
    session: Session, *, kind: str = "answer", label: str | None = None, limit: int = 10
) -> list[EvalRun]: ...


def compare_runs(session: Session, before_id: uuid.UUID, after_id: uuid.UUID) -> RunDiff: ...
```

Behaviour pins:

- `corpus_fingerprint` counts only rows retrieval can see: `active_select(Content).where(
  Content.status == "published")`. `chunk_count` = `Chunk` rows joined to that set.
  `max_updated_at` = the max `updated_at` over that set (`None` for an empty corpus).
  `digest` = `sha256("\n".join(f"{slug}\t{updated_at.isoformat()}" for … ordered by slug))
  .hexdigest()[:16]`.
- `record_run` calls `corpus_fingerprint` itself, writes one `EvalRun` + one `EvalResult` per row
  (`expected_slugs`/`cited_slugs` stored as `list(...)`), `flush()`es, and returns the run. It
  **never commits** (CONVENTIONS.md §3 — the CLI owns the transaction boundary).
- `latest_runs` orders `created_at DESC, id DESC` (`created_at` is Postgres' transaction
  timestamp, so several runs in one transaction tie — the id tiebreaker keeps it deterministic).
- `compare_runs` raises `NotFoundError` if either id has no row. Verdicts come from
  `EvalResult.verdict`; every list is sorted by question text so output is stable.

### `app/eval/groundedness.py` changes

- `EvalRow` gains, in this order after `verdict`: `top_similarity: float | None`,
  `answer_text: str`, then `question_class: str | None = None`, `persona: str | None = None`,
  `metrics: dict[str, object] | None = None`. `_evaluate_question` already holds the first two
  (`retrieval.top_similarity` at line 253-255, `answer_text` at 269-271) — pass them through.
  The three defaulted fields stay `None` here; tasks 04/05/06 fill them.
- New `def _git_sha() -> str` — `subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
  text=True, timeout=5, check=False)`; returns `stdout.strip()` on returncode 0, else `""`
  (never raises; a container/tarball checkout with no `.git` is normal).
- New `def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace` with:
  `--label` (default `"adhoc"`), `--questions` (`Path`, default `_DEFAULT_QUESTIONS_PATH`),
  `--no-persist` (`store_true`), `--compare-to` (`str | None`, a run-id UUID or the literal
  `latest`), `--runs` (`int`, default `1`, `choices=range(1, 11)` is NOT used — validate
  `>= 1` with `type=int` and an explicit `parser.error` when `< 1`).
- New `def _print_report(report: EvalReport) -> None` — `_print_table(report.rows)` then the
  **verbatim** phase-7 summary line
  `f"groundedness: {report.pct_fully_supported:.1f}% fully supported; refusals {report.refusal_correct}/{report.refusal_total} correct"`.
- New `def _print_stability(reports: Sequence[EvalReport], *, label: str) -> None` printing:

```
stability over <n> runs (label=<label>):
  pct_fully_supported  mean 58.8  spread 0.0  [58.8, 58.8, 58.8]
  refusal_correct      mean 4.0  spread 0  [4, 4, 4]
```

  (`mean` = arithmetic mean formatted `.1f`; `spread` = `max - min`, `.1f` for the pct row and
  plain `int` for the count row.)
- `_run_from_cli()` rewritten: parse args → build the real seams → open ONE session → run
  `run_eval` `args.runs` times **sequentially**, printing `_print_report` after each → unless
  `--no-persist`, `record_run(...)` each report with the SAME `label` (so the N runs form one
  labelled family) and `session.commit()` → if `args.runs > 1`, `_print_stability(...)` → if
  `--compare-to` is set, resolve `before_id` (`latest` = the most recent `kind="answer"` run
  **excluding** the ones just written; otherwise `uuid.UUID(args.compare_to)`), call
  `compare_runs` against the LAST persisted run, and print:

```
compare <before_id> -> <after_id>: pct <b> -> <a> (<+/-d>); regressions <n>; improvements <n>; added <n>; removed <n>
  regression: <question>
```

  `record_run` is called with `embedding_model=settings.embedding_model`,
  `chat_model=settings.chat_model`, `judge_model=settings.chat_model` (task 05 switches this to
  `settings.judge_model`), `similarity_threshold=settings.similarity_threshold`,
  `retrieval_k=6` (the `retrieve()` default the harness uses today), `git_sha=_git_sha()`.

> **Conflict to flag:** the INDEX says the contracts already forbid `app.services -> app.eval`,
> but `pyproject.toml`'s "app.services imports only app.models and app.config" contract does not
> list `app.eval` in `forbidden_modules`. The Protocol seam above satisfies the intent either way;
> **do not** edit the contract in this task — record it for the controller (see Report).

## Steps (TDD)

- [ ] **RED — test-author, 1/2.** Create `apps/api/tests/test_eval_runs_service.py`:

```python
"""`app.services.eval_runs` pins (phase-9 task-03, DESIGN §B1)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chunk, Content, EvalResult
from app.services.errors import NotFoundError
from app.services.eval_runs import compare_runs, corpus_fingerprint, latest_runs, record_run


@dataclass(frozen=True)
class FakeRow:
    question: str
    answerable: bool = True
    expected_slugs: list[str] = field(default_factory=list)
    cited_slugs: list[str] = field(default_factory=list)
    slugs_hit: bool = True
    fully_supported: bool | None = True
    refused: bool = False
    verdict: str = "PASS"
    top_similarity: float | None = 0.8
    answer_text: str = "an answer"
    question_class: str | None = None
    persona: str | None = None
    metrics: dict[str, object] | None = None


@dataclass(frozen=True)
class FakeReport:
    rows: list[FakeRow]
    pct_fully_supported: float = 100.0
    refusal_correct: int = 0
    refusal_total: int = 0


def _record(session: Session, report: FakeReport, *, label: str = "t", kind: str = "answer"):
    return record_run(
        session,
        report,
        label=label,
        kind=kind,
        embedding_model="text-embedding-3-small",
        chat_model="gpt-4o-mini",
        judge_model="gpt-4o",
        similarity_threshold=0.5,
        retrieval_k=6,
        git_sha="deadbeef",
    )


def _publish(session: Session, slug: str, *, chunks: int = 1) -> Content:
    content = Content(
        title=f"Title {slug}",
        slug=slug,
        body_md="body",
        status="published",
        published_at=datetime.now(UTC),
    )
    session.add(content)
    session.flush()
    for index in range(chunks):
        session.add(Chunk(content_id=content.id, chunk_index=index, text=f"chunk {index}"))
    session.flush()
    return content


def test_corpus_fingerprint_counts_published_chunks_and_changes_when_content_is_updated(
    db_session: Session,
) -> None:
    _publish(db_session, "alpha", chunks=2)
    _publish(db_session, "beta", chunks=1)
    before = corpus_fingerprint(db_session)

    assert before.content_count == 2
    assert before.chunk_count == 3
    assert len(before.digest) == 16

    target = db_session.scalars(select(Content).where(Content.slug == "beta")).one()
    target.updated_at = datetime.now(UTC) + timedelta(seconds=5)
    db_session.flush()
    after = corpus_fingerprint(db_session)

    assert after.digest != before.digest
    assert after.max_updated_at is not None and before.max_updated_at is not None
    assert after.max_updated_at > before.max_updated_at


def test_draft_and_deleted_content_are_outside_the_fingerprint(db_session: Session) -> None:
    _publish(db_session, "published-one")
    db_session.add(Content(title="Draft", slug="draft-one", status="draft"))
    deleted = _publish(db_session, "deleted-one")
    deleted.is_deleted = True
    db_session.flush()

    assert corpus_fingerprint(db_session).content_count == 1


def test_record_run_persists_the_run_and_one_result_per_row(db_session: Session) -> None:
    report = FakeReport(
        rows=[
            FakeRow(question="q1", expected_slugs=["a"], cited_slugs=["a"]),
            FakeRow(
                question="q2",
                answerable=False,
                fully_supported=None,
                refused=True,
                verdict="PASS",
                top_similarity=None,
                metrics={"failure_cause": None},
            ),
        ],
        pct_fully_supported=100.0,
        refusal_correct=1,
        refusal_total=1,
    )

    run = _record(db_session, report, label="baseline-2026-09")

    assert run.label == "baseline-2026-09"
    assert run.kind == "answer"
    assert run.git_sha == "deadbeef"
    assert run.total_questions == 2
    assert run.judge_model == "gpt-4o"
    results = db_session.scalars(
        select(EvalResult).where(EvalResult.run_id == run.id).order_by(EvalResult.question)
    ).all()
    assert [r.question for r in results] == ["q1", "q2"]
    assert results[0].cited_slugs == ["a"]
    assert results[1].top_similarity is None
    assert results[1].metrics == {"failure_cause": None}


def test_latest_runs_is_newest_first_and_filters_by_kind_and_label(db_session: Session) -> None:
    first = _record(db_session, FakeReport(rows=[FakeRow(question="q")]), label="a")
    second = _record(db_session, FakeReport(rows=[FakeRow(question="q")]), label="b")
    agent = _record(db_session, FakeReport(rows=[FakeRow(question="q")]), label="b", kind="agent")

    ids = [run.id for run in latest_runs(db_session)]
    assert ids[0] == second.id
    assert first.id in ids
    assert agent.id not in ids
    assert [run.id for run in latest_runs(db_session, kind="agent")] == [agent.id]
    assert [run.id for run in latest_runs(db_session, label="a")] == [first.id]


def test_compare_runs_classifies_regressions_improvements_added_and_removed(
    db_session: Session,
) -> None:
    before = _record(
        db_session,
        FakeReport(
            rows=[
                FakeRow(question="stays-pass", verdict="PASS"),
                FakeRow(question="regresses", verdict="PASS"),
                FakeRow(question="improves", verdict="FAIL", fully_supported=False),
                FakeRow(question="removed", verdict="PASS"),
            ],
            pct_fully_supported=75.0,
        ),
        label="before",
    )
    after = _record(
        db_session,
        FakeReport(
            rows=[
                FakeRow(question="stays-pass", verdict="PASS"),
                FakeRow(question="regresses", verdict="FAIL", fully_supported=False),
                FakeRow(question="improves", verdict="PASS"),
                FakeRow(question="added", verdict="PASS"),
            ],
            pct_fully_supported=80.0,
        ),
        label="after",
    )

    diff = compare_runs(db_session, before.id, after.id)

    assert diff.regressions == ["regresses"]
    assert diff.improvements == ["improves"]
    assert diff.unchanged == ["stays-pass"]
    assert diff.added == ["added"]
    assert diff.removed == ["removed"]
    assert diff.pct_delta == pytest.approx(5.0)


def test_compare_runs_raises_not_found_for_an_unknown_run_id(db_session: Session) -> None:
    run = _record(db_session, FakeReport(rows=[FakeRow(question="q")]))
    with pytest.raises(NotFoundError):
        compare_runs(db_session, run.id, uuid.uuid4())
```

  (add `from datetime import timedelta` to the imports.)

- [ ] **RED — test-author, 2/2.** Create `apps/api/tests/test_groundedness_cli.py` — no DB, no
  network; it imports the CLI helpers directly (private names, deliberately: they are this task's
  pinned seams):

```python
"""Harness CLI pins: argparse surface, unchanged phase-7 stdout, stability block."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.eval.groundedness import (
    EvalReport,
    EvalRow,
    _parse_args,
    _print_report,
    _print_stability,
)


def _row(question: str, *, verdict: str = "PASS") -> EvalRow:
    return EvalRow(
        question=question,
        answerable=True,
        expected_slugs=["a"],
        cited_slugs=["a"],
        slugs_hit=True,
        fully_supported=verdict == "PASS",
        refused=False,
        verdict=verdict,
        top_similarity=0.8,
        answer_text="an answer",
    )


def test_parse_args_defaults_persist_one_run_and_no_comparison() -> None:
    args = _parse_args([])

    assert args.label == "adhoc"
    assert args.no_persist is False
    assert args.compare_to is None
    assert args.runs == 1
    assert isinstance(args.questions, Path)


def test_parse_args_accepts_every_flag() -> None:
    args = _parse_args(
        ["--label", "baseline-2026-09", "--questions", "/tmp/q.yaml", "--no-persist",
         "--compare-to", "latest", "--runs", "3"]
    )

    assert args.label == "baseline-2026-09"
    assert args.questions == Path("/tmp/q.yaml")
    assert args.no_persist is True
    assert args.compare_to == "latest"
    assert args.runs == 3


def test_parse_args_rejects_zero_runs() -> None:
    with pytest.raises(SystemExit):
        _parse_args(["--runs", "0"])


def test_print_report_emits_the_unchanged_phase7_table_and_summary_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = EvalReport(
        rows=[_row("What is a Roth IRA conversion and how is it taxed?")],
        pct_fully_supported=58.8,
        refusal_correct=4,
        refusal_total=4,
    )

    _print_report(report)

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "answerable  slugs_hit  supported  refused  verdict question"
    assert lines[1] == "-" * len(lines[0])
    assert lines[2] == (
        "True        True       True       False    PASS    "
        "What is a Roth IRA conversion and how is it taxed?"
    )
    assert lines[3] == "groundedness: 58.8% fully supported; refusals 4/4 correct"


def test_print_stability_reports_mean_and_spread_per_metric(
    capsys: pytest.CaptureFixture[str],
) -> None:
    reports = [
        EvalReport(rows=[_row("q")], pct_fully_supported=60.0, refusal_correct=4, refusal_total=4),
        EvalReport(rows=[_row("q")], pct_fully_supported=58.0, refusal_correct=3, refusal_total=4),
        EvalReport(rows=[_row("q")], pct_fully_supported=59.0, refusal_correct=4, refusal_total=4),
    ]

    _print_stability(reports, label="baseline-2026-09")

    out = capsys.readouterr().out
    assert "stability over 3 runs (label=baseline-2026-09):" in out
    assert "pct_fully_supported" in out
    assert "mean 59.0" in out
    assert "spread 2.0" in out
    assert "[60.0, 58.0, 59.0]" in out
    assert "refusal_correct" in out
```

- [ ] **Run RED:** `cd apps/api && TEST_DATABASE_URL=… uv run pytest tests/test_eval_runs_service.py
  tests/test_groundedness_cli.py -q` → every test FAILS (`ModuleNotFoundError:
  app.services.eval_runs`, `ImportError: cannot import name '_parse_args'`, `TypeError` on
  `EvalRow`'s new fields). Paste the evidence.

- [ ] **GREEN — implementer.** Write `app/services/eval_runs.py` per Interfaces (module docstring
  stating WHY the Protocols exist: the import-linter layering). Then edit
  `app/eval/groundedness.py`: extend `EvalRow`, pass the two new values through
  `_evaluate_question`, add `_git_sha`/`_parse_args`/`_print_report`/`_print_stability`, and
  rewrite `_run_from_cli`. Keep `run_eval` pure (no persistence inside it — DESIGN §B1).

- [ ] **Run GREEN:** the two new files, then `uv run pytest -q` (whole suite —
  `tests/test_groundedness.py`'s seven tests must still pass untouched).

- [ ] **Gates:** `pnpm gates:api`, especially **`uv run lint-imports`** (this task is the one that
  could break the services layering).

- [ ] **Commit:**
  `git commit -m "feat(api): persist eval runs + compare_runs + harness CLI (p9 t03)"`

## Verify

```bash
cd apps/api
TEST_DATABASE_URL=… uv run pytest tests/test_eval_runs_service.py tests/test_groundedness_cli.py \
  tests/test_groundedness.py -q
uv run lint-imports
pnpm gates:api
```

## Acceptance

- `record_run` + `compare_runs` behave exactly as the six service tests pin, on real rows.
- `corpus_fingerprint` ignores drafts and soft-deleted rows, and its digest moves when a published
  row's `updated_at` moves.
- `app/services/eval_runs.py` imports nothing from `app.eval` / `app.rag`; `lint-imports` green.
- `python -m app.eval.groundedness` with no flags still prints exactly the phase-7 table + summary
  line, and additionally persists one run (`--no-persist` opts out).
- `--runs 3` produces three runs sharing one `label` and one stability block with mean ± spread.
- `--compare-to latest` resolves the previous run of the same kind and prints the diff line.

## Report

- Test-author: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-03-test-author.md`
- Implementer: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-03-implementer.md` — must
  include the import-linter note above (the `app.services` contract does not currently name
  `app.eval`) as an explicit controller question.
