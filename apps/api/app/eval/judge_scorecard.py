"""Judge scorecard: does the groundedness judge deserve to be trusted? (phase-9 task-08).

Spec: `docs/plans/phase-9-eval-data-loop/DESIGN.md` §"Evaluation approach" (Judge row: agreement
with ~40 human labels, target κ >= 0.8, self-consistency x3, position/verbosity spot-check), §B2.
Task brief: `docs/plans/phase-9-eval-data-loop/task-08-judge-scorecard.md`.

`python -m app.eval.judge_scorecard` reports:

- **agreement / Cohen's kappa** against `seed/judge_labels.yaml`'s human-labelled rows — kappa is
  implemented inline below (no sklearn, DESIGN: no new dependency).
- **self-consistency**: how often three independent judgements of the same row agree with each
  other.
- **position/verbosity spot-check**: two bias probes over the first `--sample` rows.

Because the ~40 human labels come from a separate labelling session (owner + Abhishek), this same
module also exports the unlabelled worksheet for them: `--export-pending N` samples N
`(question, answer, chunks)` rows from the latest persisted `kind="answer"` eval run into
`seed/judge_labels.pending.yaml`. Until real labels exist the scorecard reports self-consistency
only (INDEX plan-time ruling) — `agreement`/`kappa` are `None`.

Every judge call goes through the injected `GroundednessJudge` seam (`app.eval.metrics`) — the
real `OpenAIJudge` (`app.eval.groundedness`) is constructed only in `_run_from_cli`, mirroring
that module's own CLI wiring pattern.
"""

from __future__ import annotations

import argparse
import random
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import make_engine, make_session_factory
from app.eval.groundedness import OpenAIJudge
from app.eval.metrics import GroundednessJudge, split_sentences, strip_citation_markers
from app.models import Chunk, EvalResult
from app.seed_paths import seed_data_dir
from app.services.errors import NotFoundError
from app.services.eval_runs import latest_runs

# The only keys `load_judge_labels` recognizes — anything else in a row is an authoring mistake
# (a typo'd field name would otherwise be silently dropped rather than caught).
_ALLOWED_LABEL_KEYS = {"question", "answer", "chunks", "human_verdict", "labeller"}
_VERDICT_STRINGS = {"supported": True, "unsupported": False, None: None}


@dataclass(frozen=True)
class JudgeLabel:
    """One human-labelled (or pending) calibration row (task-08 Interfaces)."""

    question: str
    answer: str
    chunks: list[str]
    human_verdict: bool | None  # True == "supported"
    labeller: str


@dataclass(frozen=True)
class SpotCheck:
    """`position_verbosity_spotcheck`'s result (task-08 Interfaces)."""

    sampled: int
    position_consistency: float | None  # None when no sampled row has >= 2 chunks
    verbosity_consistency: float | None  # None when `sampled == 0`


@dataclass(frozen=True)
class JudgeScorecard:
    """The whole report `score_judge` builds (task-08 Interfaces)."""

    labelled: int
    agreement: float | None  # None when there are no human labels yet
    kappa: float | None
    self_consistency: float | None  # None when there are no rows at all
    repeats: int
    spot_check: SpotCheck


def load_judge_labels(path: Path) -> list[JudgeLabel]:
    """Load and validate a judge-labels YAML file (`seed/judge_labels.yaml`'s schema).

    Raises:
        ValueError: the file's top level isn't a list, a row isn't a mapping, a row is missing a
            required key or has one of the wrong type, a row has an unknown key, or a row's
            `human_verdict` is outside {"supported", "unsupported", null}.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(
            f"{path}: expected a top-level list of judge-label rows, got {type(raw).__name__}"
        )

    labels: list[JudgeLabel] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"{path}: row {index} is not a mapping (got {type(item).__name__})")

        unknown_keys = set(item) - _ALLOWED_LABEL_KEYS
        if unknown_keys:
            raise ValueError(f"{path}: row {index} has unknown key(s): {sorted(unknown_keys)}")

        for key in ("question", "answer", "labeller"):
            if not isinstance(item.get(key), str):
                raise ValueError(f"{path}: row {index} is missing a string '{key}'")

        chunks = item.get("chunks")
        if not isinstance(chunks, list) or not all(isinstance(chunk, str) for chunk in chunks):
            raise ValueError(f"{path}: row {index} 'chunks' must be a list of strings")

        if "human_verdict" not in item:
            raise ValueError(f"{path}: row {index} is missing 'human_verdict'")
        verdict_raw = item["human_verdict"]
        if verdict_raw not in _VERDICT_STRINGS:
            raise ValueError(
                f"{path}: row {index} 'human_verdict' must be 'supported', 'unsupported', or null"
                f" (got {verdict_raw!r})"
            )

        labels.append(
            JudgeLabel(
                question=item["question"],
                answer=item["answer"],
                chunks=list(chunks),
                human_verdict=_VERDICT_STRINGS[verdict_raw],
                labeller=item["labeller"],
            )
        )

    return labels


def judge_answer(judge: GroundednessJudge, answer: str, chunks: Sequence[str]) -> bool:
    """The harness's own "fully supported" definition (`app.eval.groundedness._evaluate_question`),
    reused verbatim: every sentence of `answer` (via `app.eval.metrics.split_sentences`, after
    `app.eval.metrics.strip_citation_markers`) must be supported by the union of `chunks`. An empty
    answer is `True` (nothing unsupported was said) — the one edge the harness itself never hits.

    Task-05b (task-10 re-review §3): same input hygiene as `_evaluate_question` — `[n]` citation
    markers are stripped (the answerer's and judge's bracket-numbering spaces disagree) and the
    ordinal-list-marker fragments `split_sentences` now drops are never judged as claims — so this
    function and the harness share one definition of "fully supported".
    """
    sentences = split_sentences(strip_citation_markers(answer))
    if not sentences:
        return True
    return all(judge.is_supported(sentence, chunks) for sentence in sentences)


def cohen_kappa(judge_calls: Sequence[bool], human_calls: Sequence[bool]) -> float:
    """Cohen's kappa for two binary raters, implemented inline (no sklearn — DESIGN: no new
    dependency).

        po = fraction of rows the two raters agree on
        pe = p_j*p_h + (1 - p_j)*(1 - p_h)      (p_x = that rater's "supported" rate)
        kappa = (po - pe) / (1 - pe), and 1.0 when pe == 1.0 (both raters constant and agreeing)

    Raises:
        ValueError: the sequences are empty or differ in length.
    """
    if not judge_calls or not human_calls or len(judge_calls) != len(human_calls):
        raise ValueError("cohen_kappa requires two non-empty, equal-length sequences.")

    n = len(judge_calls)
    agree = sum(
        1
        for judge_call, human_call in zip(judge_calls, human_calls, strict=True)
        if judge_call == human_call
    )
    po = agree / n
    p_judge = sum(judge_calls) / n
    p_human = sum(human_calls) / n
    pe = p_judge * p_human + (1 - p_judge) * (1 - p_human)
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def self_consistency(
    judge: GroundednessJudge, labels: Sequence[JudgeLabel], *, repeats: int = 3
) -> float | None:
    """Fraction of rows whose `repeats` independent judgements are all identical.

    Iteration order is pinned: row-by-row, repeats as the inner loop (`for label: for _ in
    range(repeats)`), not repeats-outer — a stateful judge (e.g. one that changes behavior after N
    calls) makes this order observable, and one test depends on it. `None` when `labels` is empty.
    """
    if not labels:
        return None

    consistent = 0
    for label in labels:
        verdicts = {judge_answer(judge, label.answer, label.chunks) for _ in range(repeats)}
        if len(verdicts) == 1:
            consistent += 1
    return consistent / len(labels)


def position_verbosity_spotcheck(
    judge: GroundednessJudge, labels: Sequence[JudgeLabel], *, sample: int = 10
) -> SpotCheck:
    """Two bias probes over the first `sample` rows (file order — deterministic, no RNG):

    - **position**: judge the answer against `chunks`, then against `list(reversed(chunks))`;
      `position_consistency` = fraction where the verdict did not move. A row with fewer than two
      chunks is skipped for this probe (reversal is a no-op) and does not count toward its
      denominator; `None` when no sampled row has >= 2 chunks.
    - **verbosity**: judge the answer, then judge `answer + " " + split_sentences(answer)[0]` —
      the answer with its own first sentence restated, so nothing new is claimed and a calibrated
      judge's verdict must not move. `verbosity_consistency` = fraction where it did not, over
      every sampled row; `None` when `sampled == 0`.
    """
    sampled_labels = list(labels)[:sample]
    sampled = len(sampled_labels)
    if sampled == 0:
        return SpotCheck(sampled=0, position_consistency=None, verbosity_consistency=None)

    position_eligible = 0
    position_stable = 0
    verbosity_stable = 0

    for label in sampled_labels:
        base_verdict = judge_answer(judge, label.answer, label.chunks)

        if len(label.chunks) >= 2:
            position_eligible += 1
            reversed_verdict = judge_answer(judge, label.answer, list(reversed(label.chunks)))
            if base_verdict == reversed_verdict:
                position_stable += 1

        sentences = split_sentences(label.answer)
        padded_answer = f"{label.answer} {sentences[0]}" if sentences else label.answer
        padded_verdict = judge_answer(judge, padded_answer, label.chunks)
        if base_verdict == padded_verdict:
            verbosity_stable += 1

    position_consistency = position_stable / position_eligible if position_eligible > 0 else None
    verbosity_consistency = verbosity_stable / sampled

    return SpotCheck(
        sampled=sampled,
        position_consistency=position_consistency,
        verbosity_consistency=verbosity_consistency,
    )


def score_judge(
    judge: GroundednessJudge,
    labels: Sequence[JudgeLabel],
    *,
    repeats: int = 3,
    sample: int = 10,
) -> JudgeScorecard:
    """Build the whole scorecard: agreement/kappa over labelled rows only, self-consistency and
    the position/verbosity spot-check over every row (task-08 Interfaces)."""
    labelled_rows = [label for label in labels if label.human_verdict is not None]
    human_calls: list[bool] = [
        label.human_verdict for label in labels if label.human_verdict is not None
    ]

    agreement: float | None = None
    kappa: float | None = None
    if labelled_rows:
        judge_calls = [judge_answer(judge, label.answer, label.chunks) for label in labelled_rows]
        matches = sum(
            1
            for judge_call, human_call in zip(judge_calls, human_calls, strict=True)
            if judge_call == human_call
        )
        agreement = matches / len(labelled_rows)
        kappa = cohen_kappa(judge_calls, human_calls)

    return JudgeScorecard(
        labelled=len(labelled_rows),
        agreement=agreement,
        kappa=kappa,
        self_consistency=self_consistency(judge, labels, repeats=repeats),
        repeats=repeats,
        spot_check=position_verbosity_spotcheck(judge, labels, sample=sample),
    )


def _resolve_chunk_texts(session: Session, chunk_ids: Sequence[object]) -> list[str]:
    """Resolve `chunk_ids` (raw `EvalResult.metrics["retrieved_chunk_ids"]` strings) against the
    live `chunks` table, dropping any id that no longer resolves (the corpus was re-chunked since
    the run was recorded) — never raising, per `export_pending`'s own docstring.
    """
    texts: list[str] = []
    for raw_id in chunk_ids:
        try:
            chunk_id = uuid.UUID(str(raw_id))
        except ValueError:
            continue
        chunk = session.get(Chunk, chunk_id)
        if chunk is not None:
            texts.append(chunk.text)
    return texts


def export_pending(session: Session, *, count: int, out_path: Path, seed: int = 0) -> Path:
    """Write `count` unlabelled rows from the latest `kind="answer"` run to `out_path`.

    Rows are sampled with `random.Random(seed).sample(...)` over that run's `eval_results` ordered
    by `question` (deterministic given a run), skipping rows with an empty `answer_text`. Chunk
    texts come from `metrics["retrieved_chunk_ids"]` resolved against `chunks.id`; ids that no
    longer resolve are dropped, and a row whose ids all fail is exported with `chunks: []` — an
    honest "the judge saw nothing" row a labeller can still label. Emits `human_verdict: null` and
    `labeller: ""` for every row.

    Raises:
        NotFoundError: there is no persisted `kind="answer"` run to sample from.
    """
    runs = latest_runs(session, kind="answer", limit=1)
    if not runs:
        raise NotFoundError("No persisted 'answer' eval run to sample judge rows from.")
    run = runs[0]

    results = list(
        session.scalars(
            select(EvalResult)
            .where(EvalResult.run_id == run.id)
            .where(EvalResult.answer_text != "")
            .order_by(EvalResult.question)
        ).all()
    )

    sample_size = min(count, len(results))
    sampled_results = random.Random(seed).sample(results, sample_size)

    rows: list[dict[str, object]] = []
    for result in sampled_results:
        retrieved_chunk_ids: Sequence[object] = []
        if result.metrics is not None:
            raw_ids = result.metrics.get("retrieved_chunk_ids")
            if isinstance(raw_ids, list):
                retrieved_chunk_ids = raw_ids
        rows.append(
            {
                "question": result.question,
                "answer": result.answer_text,
                "chunks": _resolve_chunk_texts(session, retrieved_chunk_ids),
                "human_verdict": None,
                "labeller": "",
            }
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.safe_dump(rows, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return out_path


def _fmt_ratio(value: float | None, *, none_label: str) -> str:
    """Render a 0-1 fraction as a percentage, or `none_label` when `value is None`."""
    return none_label if value is None else f"{value * 100:.1f}%"


def _fmt_spot(value: float | None, *, sampled: int) -> str:
    """Render one spot-check ratio, annotated with the sample size the CLI print format shows
    (task-08 Interfaces: `position consistency   100.0% (n=3)`)."""
    if value is None:
        return "n/a (no eligible rows)" if sampled > 0 else "n/a (no rows)"
    return f"{value * 100:.1f}% (n={sampled})"


def _print_scorecard(card: JudgeScorecard, *, model: str, total: int) -> None:
    """Print the scorecard in the task-08 CLI format."""
    print(f"judge scorecard (model={model}, labels={card.labelled} labelled / {total} total)")

    agreement_str = _fmt_ratio(card.agreement, none_label="n/a (no human labels yet)")
    print(f"  {'agreement':<23}{agreement_str}")

    kappa_str = (
        "n/a (no human labels yet)"
        if card.kappa is None
        else f"{card.kappa:.2f}   (target >= 0.80)"
    )
    kappa_label = "cohen's kappa"
    print(f"  {kappa_label:<23}{kappa_str}")

    self_consistency_label = f"self-consistency x{card.repeats}"
    self_consistency_str = _fmt_ratio(card.self_consistency, none_label="n/a (no rows)")
    print(f"  {self_consistency_label:<23}{self_consistency_str}")

    sampled = card.spot_check.sampled
    position_str = _fmt_spot(card.spot_check.position_consistency, sampled=sampled)
    print(f"  {'position consistency':<23}{position_str}")

    verbosity_str = _fmt_spot(card.spot_check.verbosity_consistency, sampled=sampled)
    print(f"  {'verbosity consistency':<23}{verbosity_str}")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the CLI's flags (task-08: `[--labels PATH] [--repeats 3] [--sample 10]
    [--export-pending N] [--out PATH]`)."""
    parser = argparse.ArgumentParser(
        description="Score the groundedness judge against seed/judge_labels.yaml, or export "
        "unlabelled rows from the latest answer run for a labelling session."
    )
    parser.add_argument(
        "--labels", type=Path, default=None, help="Path to a judge-labels YAML file."
    )
    parser.add_argument(
        "--repeats", type=int, default=3, help="Self-consistency repeats (default: 3)."
    )
    parser.add_argument(
        "--sample", type=int, default=10, help="Position/verbosity spot-check sample size."
    )
    parser.add_argument(
        "--export-pending",
        type=int,
        default=None,
        metavar="N",
        help="Export N unlabelled rows from the latest answer run instead of scoring.",
    )
    parser.add_argument("--out", type=Path, default=None, help="Output path for --export-pending.")
    return parser.parse_args(argv)


def _run_from_cli(argv: list[str] | None = None) -> None:
    """`python -m app.eval.judge_scorecard`: either export a pending-labels worksheet from the
    latest persisted answer run (`--export-pending N`, a DB job — never calls the judge), or score
    the real `OpenAIJudge` against `seed/judge_labels.yaml` and print the scorecard.
    """
    args = _parse_args(argv)
    settings = Settings()

    if args.export_pending is not None:
        out_path = (
            args.out if args.out is not None else seed_data_dir() / "judge_labels.pending.yaml"
        )
        engine = make_engine(settings.database_url.get_secret_value())
        session_factory = make_session_factory(engine)
        session = session_factory()
        try:
            written = export_pending(session, count=args.export_pending, out_path=out_path)
        finally:
            session.close()
        engine.dispose()
        rows = yaml.safe_load(written.read_text(encoding="utf-8")) or []
        print(f"wrote {len(rows)} pending row(s) to {written}")
        return

    labels_path = args.labels if args.labels is not None else seed_data_dir() / "judge_labels.yaml"
    labels = load_judge_labels(labels_path)
    judge = OpenAIJudge.from_settings(settings)
    card = score_judge(judge, labels, repeats=args.repeats, sample=args.sample)
    _print_scorecard(card, model=settings.judge_model, total=len(labels))


if __name__ == "__main__":
    _run_from_cli()
