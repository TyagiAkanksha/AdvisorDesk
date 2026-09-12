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
