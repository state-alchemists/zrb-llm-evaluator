# GENERATED FROM SPEC: specs/experiment-runner/requirements.md,
#                      specs/report-aggregate/requirements.md
# IMPLEMENTS: REQ-003, REQ-017, REQ-025, REQ-026, REQ-027, REQ-028, REQ-029,
#             REQ-030, REQ-031, REQ-032, REQ-033, REQ-034, REQ-035, REQ-036,
#             REQ-037, REQ-038, REQ-039, REQ-040, REQ-041, REQ-042,
#             NFR-002, NFR-003, NFR-004

"""Report generation — Markdown and JSON output."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from zrb_llm_evaluator.models import Experiment, Report, TrialResult

# Status icon mapping (REQ-029).
_STATUS_ICONS: Final[dict[str, str]] = {
    "EXCELLENT": "👍",
    "PASS": "✅",
    "FAIL": "❌",
    "TIMEOUT": "⏱️",
    "ERROR": "⚠️",
}

# Statuses eligible for the best-metric bolding scope (REQ-026).
_BOLD_ELIGIBLE_STATUSES: Final[frozenset[str]] = frozenset({"EXCELLENT", "PASS"})


@dataclass(frozen=True)
class _BestMetrics:
    """Per-test-case extrema across PASS/EXCELLENT trials.

    Any field may be ``None`` if no eligible trial contributed a value
    (e.g. no trial had a ``verification_result`` for ``best_score``).
    """

    best_duration: float | None
    best_score: float | None
    best_total_tokens: int | None
    best_tool_call_count: int | None


def _trial_sort_key(t: TrialResult) -> tuple[str, str, int]:
    """Sort key for trials — model, test_case, trial_index (all ASC)."""
    return (t.model, t.test_case, t.trial_index)


def _compute_best_metrics_by_case(
    results: list[TrialResult],
) -> dict[str, _BestMetrics]:
    """Compute per-test-case extrema across PASS/EXCELLENT trials only."""
    by_case: dict[str, list[TrialResult]] = {}
    for r in results:
        if r.status in _BOLD_ELIGIBLE_STATUSES:
            by_case.setdefault(r.test_case, []).append(r)

    out: dict[str, _BestMetrics] = {}
    for case, trials in by_case.items():
        durations = [t.duration for t in trials]
        totals = [t.total_tokens for t in trials]
        tool_counts = [t.tool_call_count for t in trials]
        scores = [
            t.verification_result.score
            for t in trials
            if t.verification_result is not None
        ]
        out[case] = _BestMetrics(
            best_duration=min(durations) if durations else None,
            best_score=max(scores) if scores else None,
            best_total_tokens=min(totals) if totals else None,
            best_tool_call_count=min(tool_counts) if tool_counts else None,
        )
    return out


def _bold(text: str) -> str:
    """Wrap ``text`` in Markdown bold."""
    return f"**{text}**"


def _status_cell(status: str) -> str:
    """Render a status cell with the icon prefix (REQ-029)."""
    icon = _STATUS_ICONS.get(status, "")
    return f"{icon} {status}" if icon else status


def _render_summary_row(r: TrialResult, best: _BestMetrics | None) -> str:
    """Render one row of the summary table, applying bold to best metric cells."""
    score_text = ""
    if r.verification_result is not None:
        score_text = f"{r.verification_result.score:.2f}"
    duration_text = f"{r.duration:.2f}"
    total_text = str(r.total_tokens)
    tool_count_text = str(r.tool_call_count)

    eligible = r.status in _BOLD_ELIGIBLE_STATUSES and best is not None
    if eligible and best is not None:
        if best.best_duration is not None and r.duration == best.best_duration:
            duration_text = _bold(duration_text)
        if (
            r.verification_result is not None
            and best.best_score is not None
            and r.verification_result.score == best.best_score
        ):
            score_text = _bold(score_text)
        if (
            best.best_total_tokens is not None
            and r.total_tokens == best.best_total_tokens
        ):
            total_text = _bold(total_text)
        if (
            best.best_tool_call_count is not None
            and r.tool_call_count == best.best_tool_call_count
        ):
            tool_count_text = _bold(tool_count_text)

    return (
        f"| {r.model} | {r.test_case} | {r.trial_index} | "
        f"{_status_cell(r.status)} | {duration_text} | {score_text} | "
        f"{total_text} | {r.input_tokens} | "
        f"{r.output_tokens} | {r.cache_read_tokens} | "
        f"{tool_count_text} |\n"
    )


# Canonical status order for the Overall Status table (REQ-035).
_CANONICAL_STATUS_ORDER: Final[tuple[str, ...]] = (
    "EXCELLENT",
    "PASS",
    "FAIL",
    "TIMEOUT",
    "ERROR",
)

# Statuses whose trials populate the Failing / Timeout table (REQ-040).
_FAILING_STATUSES: Final[frozenset[str]] = frozenset({"FAIL", "TIMEOUT", "ERROR"})

# Em dash literal used for empty Grid cells (REQ-039).
_EM_DASH: Final[str] = "—"


@dataclass
class _StatusCounts:
    """Per-status counters for a single bucket (model or test case)."""

    excellent: int = 0
    passed: int = 0
    failed: int = 0
    timeout: int = 0
    error: int = 0
    trials: int = 0

    def add(self, status: str) -> None:
        """Increment the counter for ``status`` and the total trials."""
        self.trials += 1
        if status == "EXCELLENT":
            self.excellent += 1
        elif status == "PASS":
            self.passed += 1
        elif status == "FAIL":
            self.failed += 1
        elif status == "TIMEOUT":
            self.timeout += 1
        elif status == "ERROR":
            self.error += 1


@dataclass
class _AggregateBuckets:
    """Accumulated aggregate buckets used to render the aggregate sections."""

    overall: dict[str, int] = field(default_factory=dict)
    by_model: dict[str, _StatusCounts] = field(default_factory=dict)
    by_case: dict[str, _StatusCounts] = field(default_factory=dict)
    by_cell: dict[tuple[str, str], list[TrialResult]] = field(default_factory=dict)
    failing: list[TrialResult] = field(default_factory=list)
    model_duration_sum: dict[str, float] = field(default_factory=dict)
    total: int = 0


# @sdlc NFR-002
def _collect_aggregates(results: list[TrialResult]) -> _AggregateBuckets:
    """Build all aggregate buckets in a single O(T) pass over ``results``."""
    b = _AggregateBuckets()
    for r in results:
        b.total += 1
        b.overall[r.status] = b.overall.get(r.status, 0) + 1

        model_bucket = b.by_model.get(r.model)
        if model_bucket is None:
            model_bucket = _StatusCounts()
            b.by_model[r.model] = model_bucket
        model_bucket.add(r.status)
        b.model_duration_sum[r.model] = (
            b.model_duration_sum.get(r.model, 0.0) + r.duration
        )

        case_bucket = b.by_case.get(r.test_case)
        if case_bucket is None:
            case_bucket = _StatusCounts()
            b.by_case[r.test_case] = case_bucket
        case_bucket.add(r.status)

        b.by_cell.setdefault((r.model, r.test_case), []).append(r)

        if r.status in _FAILING_STATUSES:
            b.failing.append(r)
    return b


# @sdlc REQ-035
def _render_overall_status(b: _AggregateBuckets) -> list[str]:
    """Render the Overall Status section."""
    lines: list[str] = [
        f"**Total trials**: {b.total}\n",
        "\n## Overall Status\n\n",
        "| Status | Count | % |\n",
        "|--------|-------|---|\n",
    ]
    for status in _CANONICAL_STATUS_ORDER:
        count = b.overall.get(status, 0)
        if count == 0:
            continue
        pct = (count / b.total * 100.0) if b.total > 0 else 0.0
        lines.append(f"| {_status_cell(status)} | {count} | {pct:.1f} |\n")
    return lines


# @sdlc REQ-036
def _render_by_model(b: _AggregateBuckets) -> list[str]:
    """Render the By Model section."""
    lines: list[str] = [
        "\n## By Model\n\n",
        "| Model | Trials | 👍 | ✅ | ❌ | ⏱️ | ⚠️ | Avg dur (s) |\n",
        "|-------|--------|----|----|----|----|----|-------------|\n",
    ]
    for model in sorted(b.by_model):
        c = b.by_model[model]
        avg = (b.model_duration_sum[model] / c.trials) if c.trials > 0 else 0.0
        lines.append(
            f"| {model} | {c.trials} | {c.excellent} | {c.passed} | "
            f"{c.failed} | {c.timeout} | {c.error} | {avg:.1f} |\n"
        )
    return lines


# @sdlc REQ-037
def _render_by_test_case(b: _AggregateBuckets) -> list[str]:
    """Render the By Test Case section."""
    lines: list[str] = [
        "\n## By Test Case\n\n",
        "| Test Case | Trials | 👍 | ✅ | ❌ | ⏱️ | ⚠️ |\n",
        "|-----------|--------|----|----|----|----|----|\n",
    ]
    for case in sorted(b.by_case):
        c = b.by_case[case]
        lines.append(
            f"| {case} | {c.trials} | {c.excellent} | {c.passed} | "
            f"{c.failed} | {c.timeout} | {c.error} |\n"
        )
    return lines


# @sdlc REQ-038, REQ-039
def _render_grid(b: _AggregateBuckets) -> list[str]:
    """Render the Grid section: models as rows, test cases as columns."""
    models = sorted(b.by_model)
    cases = sorted(b.by_case)

    lines: list[str] = ["\n## Grid\n\n"]
    header_cols = ["Model", *cases]
    lines.append("| " + " | ".join(header_cols) + " |\n")
    sep_cols = ["-" * max(3, len(col)) for col in header_cols]
    lines.append("|" + "|".join(sep_cols) + "|\n")

    for model in models:
        row_cells: list[str] = [model]
        for case in cases:
            trials = b.by_cell.get((model, case))
            if not trials:
                row_cells.append(_EM_DASH)
                continue
            icons = [
                _STATUS_ICONS.get(t.status, "")
                for t in sorted(trials, key=lambda x: x.trial_index)
            ]
            row_cells.append(" ".join(icons))
        lines.append("| " + " | ".join(row_cells) + " |\n")
    return lines


def _render_stability(b: _AggregateBuckets) -> list[str]:
    """Render the Stability section: per-(model, test_case) pass-rate gate.

    A cell is STABLE only if every trial reaches a passing terminal status
    (EXCELLENT or PASS). Any mix of pass/fail (or fail/timeout/error) flags
    the cell FLAKY — that's the signal users actually need: a one-off lucky
    pass should not be reported as the same thing as a 3/3. BROKEN means
    zero trials passed.

    The section is suppressed when ``trials==1`` for every cell, since
    stability is undefined with a single observation.
    """
    cells: list[tuple[str, str, int, int]] = []  # (model, case, passing, total)
    for (model, case), trials in b.by_cell.items():
        total = len(trials)
        passing = sum(
            1 for t in trials if t.status in _BOLD_ELIGIBLE_STATUSES
        )
        cells.append((model, case, passing, total))

    if all(total == 1 for _, _, _, total in cells):
        return []

    lines: list[str] = ["\n## Stability\n\n"]
    lines.append("Per-(model, test case) pass rate across trials. ")
    lines.append(
        "🟢 stable = all trials passed; 🟡 flaky = mixed; 🔴 broken = none passed.\n\n"
    )
    lines.append("| Model | Test Case | Pass Rate | Stability |\n")
    lines.append("|-------|-----------|-----------|-----------|\n")
    for model, case, passing, total in sorted(cells):
        if total <= 0:
            continue
        rate = passing / total
        if passing == total:
            icon = "🟢 STABLE"
        elif passing == 0:
            icon = "🔴 BROKEN"
        else:
            icon = "🟡 FLAKY"
        lines.append(
            f"| {model} | {case} | {passing}/{total} ({rate * 100:.0f}%) | {icon} |\n"
        )
    return lines


# @sdlc REQ-040, REQ-041
def _render_failing(b: _AggregateBuckets) -> list[str]:
    """Render the Failing / Timeout Trials section."""
    lines: list[str] = ["\n## Failing / Timeout Trials\n\n"]
    if not b.failing:
        lines.append("No failing or timeout trials.\n")
        return lines
    lines.append("| Model | Test Case | Trial | Status | Duration (s) |\n")
    lines.append("|-------|-----------|-------|--------|--------------|\n")
    for r in sorted(b.failing, key=_trial_sort_key):
        lines.append(
            f"| {r.model} | {r.test_case} | {r.trial_index} | "
            f"{_status_cell(r.status)} | {r.duration:.1f} |\n"
        )
    return lines


# @sdlc REQ-003, REQ-017, NFR-003
def generate_json_report(experiment: Experiment, output_path: Path) -> Report:
    """Generate a structured JSON report of an experiment.

    Writes the full ``Experiment`` envelope (config + results + timing) to
    ``output_path`` atomically.

    Args:
    ----
        experiment: The experiment to serialize.
        output_path: Path to write the JSON file.

    Returns:
    -------
        A ``Report`` manifest describing the produced artifact.

    """
    data = experiment.model_dump(mode="json")
    parent = output_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp: Path | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(parent),
            prefix=".report_tmp_",
            suffix=".json",
        )
        os.close(fd)
        tmp = Path(tmp_path)
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(output_path))
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink(missing_ok=True)
    return Report(
        experiment_id=experiment.id,
        json_path=str(output_path),
        generated_at=datetime.now(timezone.utc),
    )


# @sdlc REQ-003, REQ-025, REQ-026, REQ-027, REQ-028, REQ-029,
#       REQ-030, REQ-031, REQ-032, REQ-033, REQ-034, REQ-042, NFR-004
def generate_markdown_report(experiment: Experiment, output_path: Path) -> Report:
    """Generate a human-readable Markdown report.

    The report is pure Markdown (no embedded HTML). Trial rows are sorted
    by ``(model, test_case, trial_index)`` ascending. Within each test
    case, the best metric values across ``PASS``/``EXCELLENT`` trials are
    wrapped in Markdown bold; tied values produce multiple bold cells.
    Status cells are prefixed with a fixed icon mapping.

    Args:
    ----
        experiment: The experiment to render.
        output_path: Path to write the Markdown file.

    Returns:
    -------
        A ``Report`` manifest describing the produced artifact.

    """
    # Use a deterministic generation timestamp derived from the experiment so
    # repeated rendering of the same experiment produces byte-identical output.
    generated_at = experiment.completed_at or experiment.started_at
    sorted_results: list[TrialResult] = sorted(experiment.results, key=_trial_sort_key)
    best_by_case = _compute_best_metrics_by_case(sorted_results)

    started_str = experiment.started_at.isoformat() if experiment.started_at else "—"
    completed_str = (
        experiment.completed_at.isoformat() if experiment.completed_at else "—"
    )
    lines: list[str] = [
        "# Experiment Report\n",
        f"- **Experiment ID**: {experiment.id}\n",
        f"- **Started**: {started_str}\n",
        f"- **Completed**: {completed_str}\n",
        f"- **Generated**: {generated_at.isoformat()}\n",
        "\n",
    ]

    # Aggregate sections (REQ-030) — computed at render time only (REQ-033).
    aggregates = _collect_aggregates(sorted_results)
    lines.extend(_render_overall_status(aggregates))
    lines.extend(_render_by_model(aggregates))
    lines.extend(_render_by_test_case(aggregates))
    lines.extend(_render_grid(aggregates))
    lines.extend(_render_stability(aggregates))
    lines.extend(_render_failing(aggregates))

    lines.append("\n## Summary\n\n")
    lines.append(
        "| Model | Test Case | Trial | Status | Duration (s) | Score | "
        "Total Tokens | Input | Output | Cache | Tool Calls |\n"
    )
    lines.append(
        "|-------|-----------|-------|--------|-------------|-------|"
        "--------------|-------|--------|-------|------------|\n"
    )

    for r in sorted_results:
        lines.append(_render_summary_row(r, best_by_case.get(r.test_case)))

    lines.append("\n## Per-Trial Details\n\n")
    for r in sorted_results:
        lines.append(f"### {r.model} / {r.test_case} / Trial {r.trial_index}\n\n")
        lines.append(f"- **Status**: {_status_cell(r.status)}\n")
        lines.append(f"- **Duration**: {r.duration:.2f}s\n")
        lines.append(f"- **Exit code**: {r.exit_code}\n")
        lines.append(f"- **History path**: {r.log_path}\n")
        if r.stdout_log_path:
            lines.append(f"- **Stdout log path**: {r.stdout_log_path}\n")
        lines.append(
            f"- **Tokens**: total={r.total_tokens}, input={r.input_tokens}, "
            f"output={r.output_tokens}, cache={r.cache_read_tokens}\n"
        )
        if r.tool_call_count > 0:
            lines.append(
                f"- **Tool calls** ({r.tool_call_count}): "
                f"{', '.join(r.tool_calls)}\n"
            )
        if r.verification_result is not None:
            lines.append(f"- **Validation score**: {r.verification_result.score}\n")
            for check in r.verification_result.details:
                mark = "✓" if check.passed else "✗"
                lines.append(f"  - {check.name}: {mark} {check.message}\n")
        lines.append("\n")

    output_path.write_text("".join(lines), encoding="utf-8")
    return Report(
        experiment_id=experiment.id,
        markdown_path=str(output_path),
        generated_at=datetime.now(timezone.utc),
    )
