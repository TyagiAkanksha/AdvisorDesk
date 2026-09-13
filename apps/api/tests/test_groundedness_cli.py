"""Harness CLI pins: argparse surface, unchanged phase-7 stdout, stability block."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.eval.groundedness import (
    ClassRollup,
    EvalReport,
    EvalRow,
    _parse_args,
    _print_report,
    _print_stability,
    _run_from_cli,
)
from app.services.eval_runs import latest_runs, record_run


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
        [
            "--label",
            "baseline-2026-09",
            "--questions",
            "/tmp/q.yaml",
            "--no-persist",
            "--compare-to",
            "latest",
            "--runs",
            "3",
        ]
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


# --- implementer addition: task-06 failure-taxonomy printing pins ----------


def test_print_report_prints_failure_causes_after_the_rollup_blocks(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Task-06: the `failure causes:` block prints AFTER the per-class rollup blocks, only when
    at least one cause was assigned, in `FAILURE_CAUSES` order, each line formatted
    `f"  {cause:<24} {count:>3}"` (task file Interfaces).
    """
    rollup = ClassRollup(
        question_class="answerable",
        count=1,
        n_scored=0,
        passed=1,
        pct_fully_supported=100.0,
        doc_hit_rate=1.0,
        mean_recall_at_k=None,
        mean_mrr=None,
        mean_precision_at_k=None,
        mean_answer_relevance_rubric=None,
        mean_context_precision=None,
        mean_context_recall=None,
    )
    report = EvalReport(
        rows=[_row("q")],
        pct_fully_supported=50.0,
        refusal_correct=0,
        refusal_total=0,
        by_class={"answerable": rollup},
        failure_causes={"corpus_gap": 6, "generation_unfaithful": 4, "threshold_refusal": 1},
    )

    _print_report(report)

    lines = capsys.readouterr().out.splitlines()
    assert "failure causes:" in lines
    causes_index = lines.index("failure causes:")
    judge_metrics_index = lines.index("judge metrics by class:")
    assert causes_index > judge_metrics_index
    assert lines[causes_index + 1] == f"  {'corpus_gap':<24} {6:>3}"
    assert lines[causes_index + 2] == f"  {'generation_unfaithful':<24} {4:>3}"
    assert lines[causes_index + 3] == f"  {'threshold_refusal':<24} {1:>3}"


def test_print_report_omits_the_failure_causes_block_on_a_clean_run(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = EvalReport(
        rows=[_row("q")], pct_fully_supported=100.0, refusal_correct=0, refusal_total=0
    )

    _print_report(report)

    assert "failure causes:" not in capsys.readouterr().out


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


# ---------------------------------------------------------------------------
# Fix round 1, I3: `_run_from_cli` orchestration — previously untested because it built its own
# real embedder/chat/judge/session internally. `run_eval_fn`/`session_factory` are the injectable
# seams that make it testable: `run_eval_fn` replaces `run_eval` outright (so no real
# embedder/chat/judge call ever happens, even though `_run_from_cli` still constructs those real
# — but here inert — objects from zero-env `Settings()` defaults), and `session_factory` hands
# back the `db_session` fixture so these tests run against a real throwaway-schema Postgres, not a
# mock.
# ---------------------------------------------------------------------------


def _report(pct: float = 100.0) -> EvalReport:
    return EvalReport(rows=[_row("q")], pct_fully_supported=pct, refusal_correct=0, refusal_total=0)


def test_run_from_cli_persists_a_run_by_default(db_session: Session) -> None:
    _run_from_cli(
        ["--label", "persist-default"],
        run_eval_fn=lambda *_args, **_kwargs: _report(),
        session_factory=lambda: db_session,
    )

    runs = latest_runs(db_session, label="persist-default")
    assert len(runs) == 1
    assert runs[0].total_questions == 1


def test_run_from_cli_prints_the_recorded_run_id_for_every_persisted_run(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fix-wave B4 (final-review I4): `_run_from_cli` prints `recorded eval_runs id=<id>` for
    every persisted run, exactly as `app.eval.agent_suite`'s own CLI already does
    (`agent_suite.py:796`) — needed live to feed `accept_proposal(eval_run_after_id=...)` without
    a `psql` round-trip. One line per run in a `--runs N > 1` family, each naming that run's own id.
    """
    _run_from_cli(
        ["--label", "prints-ids", "--runs", "2"],
        run_eval_fn=lambda *_args, **_kwargs: _report(),
        session_factory=lambda: db_session,
    )

    runs = latest_runs(db_session, label="prints-ids", limit=2)
    assert len(runs) == 2
    out = capsys.readouterr().out
    for run in runs:
        assert f"recorded eval_runs id={run.id}" in out


def test_run_from_cli_no_persist_writes_nothing(db_session: Session) -> None:
    _run_from_cli(
        ["--label", "no-persist-check", "--no-persist"],
        run_eval_fn=lambda *_args, **_kwargs: _report(),
        session_factory=lambda: db_session,
    )

    assert latest_runs(db_session, label="no-persist-check") == []


def test_run_from_cli_compare_to_latest_diffs_against_the_previous_run(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline_run = record_run(
        db_session,
        EvalReport(
            rows=[_row("q", verdict="PASS")],
            pct_fully_supported=100.0,
            refusal_correct=0,
            refusal_total=0,
        ),
        label="baseline",
        embedding_model="m",
        chat_model="m",
        judge_model="m",
        similarity_threshold=0.5,
        retrieval_k=6,
    )
    db_session.commit()

    _run_from_cli(
        ["--label", "second", "--compare-to", "latest"],
        run_eval_fn=lambda *_args, **_kwargs: EvalReport(
            rows=[_row("q", verdict="FAIL")],
            pct_fully_supported=0.0,
            refusal_correct=0,
            refusal_total=0,
        ),
        session_factory=lambda: db_session,
    )

    [second_run] = latest_runs(db_session, label="second")
    out = capsys.readouterr().out
    # The "before" run in the printed diff is the pre-existing baseline, never the run this same
    # invocation just wrote — "most recent OTHER run", not "most recent run".
    assert f"compare {baseline_run.id} -> {second_run.id}:" in out
    assert "regression: q" in out


def test_run_from_cli_a_run_that_raises_midway_persists_nothing(db_session: Session) -> None:
    calls = {"n": 0}

    def flaky_run_eval(*_args: object, **_kwargs: object) -> EvalReport:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")
        return _report()

    with pytest.raises(RuntimeError, match="boom"):
        _run_from_cli(
            ["--label", "flaky", "--runs", "2"],
            run_eval_fn=flaky_run_eval,
            session_factory=lambda: db_session,
        )

    # The single `session.commit()` sits after the whole `--runs` loop, so an exception on run 2
    # of 2 must leave run 1's already-flushed-but-uncommitted row rolled back too — no partial
    # family persists.
    db_session.rollback()
    assert latest_runs(db_session, label="flaky") == []
