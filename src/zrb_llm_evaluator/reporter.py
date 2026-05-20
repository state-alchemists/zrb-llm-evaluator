# GENERATED FROM SPEC: specs/experiment-runner/requirements.md
# IMPLEMENTS: REQ-003, REQ-017, REQ-025, REQ-026, REQ-027, REQ-028, REQ-029

"""Report generation — Markdown and JSON output."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
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


# @sdlc REQ-003, REQ-017
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


# @sdlc REQ-003, REQ-025, REQ-026, REQ-027, REQ-028, REQ-029
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
        f"**Experiment ID**: {experiment.id}\n",
        f"**Total trials**: {len(sorted_results)}\n",
        f"**Started**: {started_str}\n",
        f"**Completed**: {completed_str}\n",
        f"**Generated**: {generated_at.isoformat()}\n",
        "\n## Summary\n\n",
        "| Model | Test Case | Trial | Status | Duration (s) | Score | "
        "Total Tokens | Input | Output | Cache | Tool Calls |\n",
        "|-------|-----------|-------|--------|-------------|-------|"
        "--------------|-------|--------|-------|------------|\n",
    ]

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
