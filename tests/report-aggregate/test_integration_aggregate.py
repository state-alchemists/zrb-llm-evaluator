# COVERS: REPORT-AGGREGATE:REQ-030, REPORT-AGGREGATE:REQ-035, REPORT-AGGREGATE:REQ-036, REPORT-AGGREGATE:REQ-037, REPORT-AGGREGATE:REQ-038, IT-A001

"""Integration test: aggregate values match the per-trial Summary table."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from zrb_llm_evaluator.models import (
    Experiment,
    ExperimentConfig,
    TrialResult,
    ValidationResult,
)
from zrb_llm_evaluator.reporter import generate_markdown_report

TrialStatus = Literal["EXCELLENT", "PASS", "FAIL", "TIMEOUT", "ERROR"]

ICON_TO_STATUS: dict[str, str] = {
    "👍": "EXCELLENT",
    "✅": "PASS",
    "❌": "FAIL",
    "⏱️": "TIMEOUT",
    "⚠️": "ERROR",
}
STATUS_TO_ICON: dict[str, str] = {v: k for k, v in ICON_TO_STATUS.items()}


def _make_trial(
    model: str,
    test_case: str,
    trial_index: int,
    status: TrialStatus,
    duration: float,
) -> TrialResult:
    vr: ValidationResult | None = None
    if status in ("EXCELLENT", "PASS"):
        vr_status: Literal["EXCELLENT", "PASS", "FAIL"] = status
        vr = ValidationResult(status=vr_status, score=0.8, details=[])
    return TrialResult(
        model=model,
        test_case=test_case,
        trial_index=trial_index,
        status=status,
        duration=duration,
        exit_code=0,
        log_path="/tmp/fake.log",
        verification_result=vr,
    )


def _make_experiment(results: list[TrialResult]) -> Experiment:
    cfg = ExperimentConfig(
        models=["openai:gpt-4o"],
        test_case_dirs=[Path("/tmp/fake-case")],
        trials=3,
        parallelism=1,
        timeout=30,
    )
    started = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    completed = datetime(2024, 1, 1, 1, 0, 0, tzinfo=timezone.utc)
    return Experiment(
        id="exp-it-a001",
        config=cfg,
        results=results,
        started_at=started,
        completed_at=completed,
    )


def _slice_section(text: str, header: str) -> str:
    start = text.find(header)
    assert start != -1, f"missing section {header}"
    body_start = start + len(header)
    next_idx = text.find("\n## ", body_start)
    if next_idx == -1:
        return text[body_start:]
    return text[body_start:next_idx]


def _row_cells(row: str) -> list[str]:
    inner = row.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [c.strip() for c in inner.split("|")]


def _data_rows(section: str, header_first_cell: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if set(stripped.replace("|", "").strip()) <= {"-", " "}:
            continue
        cells = _row_cells(stripped)
        if cells[0] == header_first_cell:
            continue
        rows.append(cells)
    return rows


def _status_from_cell(cell: str) -> str:
    # Status cell looks like ``👍 EXCELLENT``.
    parts = cell.split(" ", 1)
    return parts[1].strip() if len(parts) == 2 else cell.strip()


def test_full_report_aggregates_match_per_trial_summary(tmp_path: Path) -> None:
    """Parse Summary rows; recompute aggregate counts and compare."""
    spec: list[tuple[str, str, int, TrialStatus, float]] = [
        ("alpha:a", "case-a", 1, "EXCELLENT", 1.0),
        ("alpha:a", "case-a", 2, "PASS", 1.2),
        ("alpha:a", "case-a", 3, "FAIL", 0.4),
        ("alpha:a", "case-b", 1, "PASS", 2.0),
        ("alpha:a", "case-b", 2, "TIMEOUT", 30.0),
        ("alpha:a", "case-b", 3, "PASS", 2.5),
        ("beta:b", "case-a", 1, "EXCELLENT", 0.9),
        ("beta:b", "case-a", 2, "ERROR", 0.1),
        ("beta:b", "case-a", 3, "PASS", 1.5),
        ("beta:b", "case-b", 1, "PASS", 3.0),
        ("beta:b", "case-b", 2, "PASS", 3.5),
        ("beta:b", "case-b", 3, "EXCELLENT", 2.5),
    ]
    trials = [_make_trial(m, c, i, s, d) for (m, c, i, s, d) in spec]
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")

    # Parse Summary table.
    summary_rows = _data_rows(_slice_section(text, "## Summary"), "Model")
    # Sanity: same number of trials.
    assert len(summary_rows) == len(spec)

    # Recompute Overall counts.
    summary_statuses = [_status_from_cell(r[3]) for r in summary_rows]
    expected_overall = Counter(summary_statuses)

    # Parse the rendered Overall Status table.
    overall_rows = _data_rows(_slice_section(text, "## Overall Status"), "Status")
    rendered_overall: dict[str, int] = {}
    for cells in overall_rows:
        status = _status_from_cell(cells[0])
        rendered_overall[status] = int(cells[1])
    assert rendered_overall == dict(expected_overall)

    # Recompute By Model counts.
    by_model_expected: dict[str, Counter[str]] = {}
    by_model_dur: dict[str, list[float]] = {}
    for cells in summary_rows:
        model = cells[0]
        status = _status_from_cell(cells[3])
        duration = float(cells[4].replace("*", ""))
        by_model_expected.setdefault(model, Counter())[status] += 1
        by_model_dur.setdefault(model, []).append(duration)

    by_model_rendered = _data_rows(_slice_section(text, "## By Model"), "Model")
    for cells in by_model_rendered:
        model = cells[0]
        trials_n = int(cells[1])
        ex = int(cells[2])
        pa = int(cells[3])
        fa = int(cells[4])
        to = int(cells[5])
        er = int(cells[6])
        avg = float(cells[-1])  # Avg dur (s) is the last column
        expected_counts = by_model_expected[model]
        assert trials_n == sum(expected_counts.values()), (model, trials_n)
        assert ex == expected_counts["EXCELLENT"]
        assert pa == expected_counts["PASS"]
        assert fa == expected_counts["FAIL"]
        assert to == expected_counts["TIMEOUT"]
        assert er == expected_counts["ERROR"]
        expected_avg = sum(by_model_dur[model]) / len(by_model_dur[model])
        assert abs(avg - expected_avg) < 0.05, (model, avg, expected_avg)

    # Recompute By Test Case counts.
    by_case_expected: dict[str, Counter[str]] = {}
    for cells in summary_rows:
        case = cells[1]
        status = _status_from_cell(cells[3])
        by_case_expected.setdefault(case, Counter())[status] += 1

    by_case_rendered = _data_rows(_slice_section(text, "## By Test Case"), "Test Case")
    for cells in by_case_rendered:
        case = cells[0]
        trials_n = int(cells[1])
        ex = int(cells[2])
        pa = int(cells[3])
        fa = int(cells[4])
        to = int(cells[5])
        er = int(cells[6])
        expected_counts = by_case_expected[case]
        assert trials_n == sum(expected_counts.values()), (case, trials_n)
        assert ex == expected_counts["EXCELLENT"]
        assert pa == expected_counts["PASS"]
        assert fa == expected_counts["FAIL"]
        assert to == expected_counts["TIMEOUT"]
        assert er == expected_counts["ERROR"]

    # Recompute Grid: for each (model, case) cell, the icons in trial_index ASC.
    by_cell_expected: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for cells in summary_rows:
        model = cells[0]
        case = cells[1]
        trial_idx = int(cells[2])
        status = _status_from_cell(cells[3])
        by_cell_expected.setdefault((model, case), []).append((trial_idx, status))

    grid_section = _slice_section(text, "## Grid")
    grid_lines = [
        line for line in grid_section.splitlines() if line.strip().startswith("|")
    ]
    # First line is the header, second is the separator.
    header_cells = _row_cells(grid_lines[0])
    case_columns = header_cells[1:]
    data_lines = [
        ln
        for ln in grid_lines[2:]
        if set(ln.strip().replace("|", "").strip()) - {"-", " "}
    ]
    for line in data_lines:
        cells = _row_cells(line)
        model = cells[0]
        for col_idx, case in enumerate(case_columns, start=1):
            cell_value = cells[col_idx]
            expected = by_cell_expected.get((model, case), [])
            if not expected:
                assert cell_value == "—", (model, case, cell_value)
                continue
            expected_sorted = sorted(expected, key=lambda x: x[0])
            expected_icons = " ".join(
                STATUS_TO_ICON[status] for (_idx, status) in expected_sorted
            )
            assert cell_value == expected_icons, (model, case, cell_value, expected_icons)
