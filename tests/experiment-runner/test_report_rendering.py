# COVERS: EXPERIMENT-RUNNER:REQ-025, EXPERIMENT-RUNNER:REQ-026, EXPERIMENT-RUNNER:REQ-027, EXPERIMENT-RUNNER:REQ-028, EXPERIMENT-RUNNER:REQ-029,
#   EXPERIMENT-RUNNER:UT-032, EXPERIMENT-RUNNER:UT-033, EXPERIMENT-RUNNER:UT-034, EXPERIMENT-RUNNER:UT-035, EXPERIMENT-RUNNER:UT-036, EXPERIMENT-RUNNER:UT-037, EXPERIMENT-RUNNER:UT-038, EXPERIMENT-RUNNER:UT-039,
#   EXPERIMENT-RUNNER:UT-040, EXPERIMENT-RUNNER:UT-041, EXPERIMENT-RUNNER:UT-042, EXPERIMENT-RUNNER:IT-006, EXPERIMENT-RUNNER:E2E-004

"""Markdown report rendering tests (sort order, bold-best, status icons)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import pytest
from zrb_llm_evaluator.models import (
    Experiment,
    ExperimentConfig,
    TrialResult,
    ValidationResult,
)
from zrb_llm_evaluator.reporter import generate_markdown_report

# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

TrialStatus = Literal["EXCELLENT", "PASS", "FAIL", "TIMEOUT", "ERROR"]


def _make_trial(
    model: str = "openai:gpt-4o",
    test_case: str = "case-a",
    trial_index: int = 1,
    status: TrialStatus = "PASS",
    duration: float = 1.0,
    score: float | None = None,
    total_tokens: int = 0,
    tool_call_count: int = 0,
) -> TrialResult:
    """Construct a TrialResult with sensible defaults for rendering tests."""
    vr: ValidationResult | None = None
    if score is not None:
        # Score is only used in extrema if status is PASS/EXCELLENT.
        vr_status: Literal["EXCELLENT", "PASS", "FAIL"]
        if status in ("EXCELLENT", "PASS"):
            vr_status = status
        else:
            vr_status = "FAIL"
        vr = ValidationResult(status=vr_status, score=score, details=[])
    return TrialResult(
        model=model,
        test_case=test_case,
        trial_index=trial_index,
        status=status,
        duration=duration,
        exit_code=0,
        log_path="/tmp/fake.log",
        verification_result=vr,
        total_tokens=total_tokens,
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=0,
        tool_calls=[],
        tool_call_count=tool_call_count,
    )


def _make_experiment(results: list[TrialResult]) -> Experiment:
    """Wrap trial results in an Experiment with a stable timestamp."""
    cfg = ExperimentConfig(
        models=["openai:gpt-4o"],
        test_case_dirs=[Path("/tmp/fake-case")],
        trials=1,
        parallelism=1,
        timeout=30,
    )
    started = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    completed = datetime(2024, 1, 1, 1, 0, 0, tzinfo=timezone.utc)
    return Experiment(
        id="exp-fixed",
        config=cfg,
        results=results,
        started_at=started,
        completed_at=completed,
    )


def _summary_rows(md_text: str) -> list[str]:
    """Extract data rows of the summary table.

    Returns rows beginning with ``|`` whose first column matches a model name
    pattern (i.e. excludes the header and separator rows).
    """
    rows: list[str] = []
    in_summary = False
    for line in md_text.splitlines():
        if line.strip() == "## Summary":
            in_summary = True
            continue
        if in_summary and line.startswith("## "):
            break
        if not in_summary:
            continue
        if not line.startswith("|"):
            continue
        # Skip header / separator rows.
        if line.startswith("| Model ") or line.startswith("|---"):
            continue
        rows.append(line)
    return rows


def _row_cells(row: str) -> list[str]:
    """Split a Markdown table row into trimmed cells."""
    # Drop leading/trailing pipe then split.
    inner = row.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [c.strip() for c in inner.split("|")]


# Column indices for the summary table.
# 0:Model 1:Test Case 2:Trial 3:Status 4:Duration 5:Score 6:Total 7:Input
# 8:Output 9:Cache 10:Tool Calls
COL_MODEL = 0
COL_CASE = 1
COL_TRIAL = 2
COL_STATUS = 3
COL_DURATION = 4
COL_SCORE = 5
COL_TOTAL = 6
COL_TOOL_CALLS = 10


# ---------------------------------------------------------------------------
# EXPERIMENT-RUNNER:UT-032 / EXPERIMENT-RUNNER:REQ-025 — rows sorted by (model, case, trial_index) ASC
# ---------------------------------------------------------------------------


def test_markdown_report_rows_sorted_by_model_case_trial(tmp_path: Path) -> None:
    """Trial rows are sorted by (model ASC, case ASC, trial_index ASC)."""
    trials: list[TrialResult] = []
    # Scrambled creation order.
    for model in ("zeta:b", "alpha:a"):
        for case in ("case-z", "case-a"):
            for idx in (2, 1):
                trials.append(
                    _make_trial(
                        model=model,
                        test_case=case,
                        trial_index=idx,
                        duration=1.0 + idx,
                        score=0.5,
                    )
                )
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)

    rows = _summary_rows(out.read_text(encoding="utf-8"))
    keys = [
        (cells[COL_MODEL], cells[COL_CASE], int(cells[COL_TRIAL]))
        for cells in (_row_cells(r) for r in rows)
    ]
    assert keys == sorted(keys), f"rows not sorted: {keys}"
    # Verify we have all 8 rows.
    assert len(keys) == 8


# ---------------------------------------------------------------------------
# EXPERIMENT-RUNNER:UT-033 / EXPERIMENT-RUNNER:REQ-026 — failures excluded from bold scope
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_status", ["FAIL", "TIMEOUT", "ERROR"])
def test_markdown_report_excludes_failures_from_bold_scope(
    tmp_path: Path, bad_status: TrialStatus
) -> None:
    """A FAIL/TIMEOUT/ERROR trial with a lower duration must not steal bold."""
    trials = [
        _make_trial(test_case="case-a", trial_index=1, status=bad_status, duration=0.5),
        _make_trial(test_case="case-a", trial_index=2, status="PASS", duration=1.0),
    ]
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    rows = _summary_rows(out.read_text(encoding="utf-8"))
    assert len(rows) == 2
    by_trial = {int(_row_cells(r)[COL_TRIAL]): _row_cells(r) for r in rows}

    pass_cells = by_trial[2]
    bad_cells = by_trial[1]
    assert pass_cells[COL_DURATION] == "**1.00**", pass_cells
    # The failing row must contain no bold cells.
    assert "**" not in "|".join(bad_cells), bad_cells


# ---------------------------------------------------------------------------
# EXPERIMENT-RUNNER:UT-034 / EXPERIMENT-RUNNER:REQ-026 — bold scope is per-test-case
# ---------------------------------------------------------------------------


def test_markdown_report_bold_scope_is_per_test_case(tmp_path: Path) -> None:
    """Each test case's best is bolded within its own scope."""
    trials = [
        _make_trial(test_case="case-a", trial_index=1, status="PASS", duration=1.0),
        _make_trial(test_case="case-b", trial_index=1, status="PASS", duration=2.0),
    ]
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    rows = _summary_rows(out.read_text(encoding="utf-8"))
    by_case = {_row_cells(r)[COL_CASE]: _row_cells(r) for r in rows}
    assert by_case["case-a"][COL_DURATION] == "**1.00**"
    assert by_case["case-b"][COL_DURATION] == "**2.00**"


# ---------------------------------------------------------------------------
# EXPERIMENT-RUNNER:UT-035 / EXPERIMENT-RUNNER:REQ-027 — no HTML
# ---------------------------------------------------------------------------


def test_markdown_report_contains_no_html(tmp_path: Path) -> None:
    """Report must be pure Markdown — no embedded HTML tags."""
    trials = [
        _make_trial(test_case=c, trial_index=i, status=s, duration=d, score=sc)
        for (c, i, s, d, sc) in [
            ("case-a", 1, "PASS", 1.0, 0.9),
            ("case-a", 2, "FAIL", 0.5, 0.1),
            ("case-b", 1, "EXCELLENT", 0.8, 1.0),
            ("case-b", 2, "TIMEOUT", 5.0, None),
        ]
    ]
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")
    for tag in ("<b>", "</b>", "<span", "<i>", "</i>", "<u>", "</u>"):
        assert tag not in text, f"HTML tag {tag!r} should not appear"


# ---------------------------------------------------------------------------
# EXPERIMENT-RUNNER:UT-036 / EXPERIMENT-RUNNER:REQ-028 — bold best duration
# ---------------------------------------------------------------------------


def test_markdown_report_bolds_best_duration(tmp_path: Path) -> None:
    """The single minimum duration cell is bold; others are not."""
    trials = [
        _make_trial(test_case="case-a", trial_index=i, status="PASS", duration=d)
        for i, d in enumerate([1.0, 2.0, 3.0], start=1)
    ]
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    rows = _summary_rows(out.read_text(encoding="utf-8"))
    durs = [_row_cells(r)[COL_DURATION] for r in rows]
    assert durs == ["**1.00**", "2.00", "3.00"]


# ---------------------------------------------------------------------------
# EXPERIMENT-RUNNER:UT-037 / EXPERIMENT-RUNNER:REQ-028 — bold best score
# ---------------------------------------------------------------------------


def test_markdown_report_bolds_best_score(tmp_path: Path) -> None:
    """The single maximum score cell is bold; others are not."""
    trials = [
        _make_trial(
            test_case="case-a",
            trial_index=i,
            status="PASS",
            duration=1.0,
            score=s,
        )
        for i, s in enumerate([0.5, 0.8, 1.0], start=1)
    ]
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    rows = _summary_rows(out.read_text(encoding="utf-8"))
    scores = [_row_cells(r)[COL_SCORE] for r in rows]
    assert scores == ["0.50", "0.80", "**1.00**"]


# ---------------------------------------------------------------------------
# EXPERIMENT-RUNNER:UT-038 / EXPERIMENT-RUNNER:REQ-028 — bold best total_tokens
# ---------------------------------------------------------------------------


def test_markdown_report_bolds_best_total_tokens(tmp_path: Path) -> None:
    """The single minimum total_tokens cell is bold."""
    trials = [
        _make_trial(
            test_case="case-a",
            trial_index=i,
            status="PASS",
            duration=1.0,
            total_tokens=tt,
        )
        for i, tt in enumerate([100, 200, 300], start=1)
    ]
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    rows = _summary_rows(out.read_text(encoding="utf-8"))
    totals = [_row_cells(r)[COL_TOTAL] for r in rows]
    assert totals == ["**100**", "200", "300"]


# ---------------------------------------------------------------------------
# EXPERIMENT-RUNNER:UT-039 / EXPERIMENT-RUNNER:REQ-028 — bold best tool_call_count
# ---------------------------------------------------------------------------


def test_markdown_report_bolds_best_tool_call_count(tmp_path: Path) -> None:
    """The single minimum tool_call_count cell is bold."""
    trials = [
        _make_trial(
            test_case="case-a",
            trial_index=i,
            status="PASS",
            duration=1.0,
            tool_call_count=tc,
        )
        for i, tc in enumerate([1, 3, 5], start=1)
    ]
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    rows = _summary_rows(out.read_text(encoding="utf-8"))
    tcs = [_row_cells(r)[COL_TOOL_CALLS] for r in rows]
    assert tcs == ["**1**", "3", "5"]


# ---------------------------------------------------------------------------
# EXPERIMENT-RUNNER:UT-040 / EXPERIMENT-RUNNER:REQ-028 — ties bold all matching cells
# ---------------------------------------------------------------------------


def test_markdown_report_bolds_all_tied_cells(tmp_path: Path) -> None:
    """Tied best values produce multiple bold cells."""
    trials = [
        _make_trial(test_case="case-a", trial_index=1, status="PASS", duration=1.0),
        _make_trial(test_case="case-a", trial_index=2, status="PASS", duration=1.0),
    ]
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    rows = _summary_rows(out.read_text(encoding="utf-8"))
    durs = [_row_cells(r)[COL_DURATION] for r in rows]
    assert durs == ["**1.00**", "**1.00**"]


# ---------------------------------------------------------------------------
# EXPERIMENT-RUNNER:UT-041 / EXPERIMENT-RUNNER:REQ-029 — status icons mapped correctly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "icon"),
    [
        ("EXCELLENT", "👍"),
        ("PASS", "✅"),
        ("FAIL", "❌"),
        ("TIMEOUT", "⏱️"),
        ("ERROR", "⚠️"),
    ],
)
def test_markdown_report_status_icons_mapped(
    tmp_path: Path, status: TrialStatus, icon: str
) -> None:
    """Each status is rendered with its mapped icon prefix."""
    trials = [
        _make_trial(test_case="case-a", trial_index=1, status=status, duration=1.0)
    ]
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    rows = _summary_rows(out.read_text(encoding="utf-8"))
    assert len(rows) == 1
    status_cell = _row_cells(rows[0])[COL_STATUS]
    assert status_cell == f"{icon} {status}", status_cell


# ---------------------------------------------------------------------------
# EXPERIMENT-RUNNER:UT-042 / EXPERIMENT-RUNNER:REQ-025 — deterministic byte-identical output
# ---------------------------------------------------------------------------


def test_markdown_report_deterministic_byte_identical(tmp_path: Path) -> None:
    """Rendering the same experiment twice produces byte-identical reports."""
    trials = [
        _make_trial(
            model=m,
            test_case=c,
            trial_index=i,
            status="PASS",
            duration=1.0 + i,
            score=0.5 + 0.1 * i,
            total_tokens=100 * i,
            tool_call_count=i,
        )
        for m in ("alpha:a", "beta:b")
        for c in ("case-a", "case-b")
        for i in (1, 2)
    ]
    exp = _make_experiment(trials)
    out1 = tmp_path / "report1.md"
    out2 = tmp_path / "report2.md"
    generate_markdown_report(exp, out1)
    generate_markdown_report(exp, out2)
    assert out1.read_bytes() == out2.read_bytes()


# ---------------------------------------------------------------------------
# EXPERIMENT-RUNNER:IT-006 — full pipeline: sort + bold + icons + no HTML
# ---------------------------------------------------------------------------


def test_report_md_full_pipeline_sort_bold_icons(tmp_path: Path) -> None:
    """Full pipeline check: ordering, per-case bold cells, icons, no HTML."""
    spec: list[tuple[str, str, int, TrialStatus, float, float | None]] = [
        # (model, case, trial, status, duration, score)
        ("alpha:a", "case-a", 1, "PASS", 1.0, 0.9),
        ("alpha:a", "case-a", 2, "EXCELLENT", 1.5, 1.0),
        ("alpha:a", "case-b", 1, "FAIL", 0.5, None),
        ("alpha:a", "case-b", 2, "PASS", 2.0, 0.7),
        ("beta:b", "case-a", 1, "TIMEOUT", 5.0, None),
        ("beta:b", "case-a", 2, "PASS", 2.0, 0.8),
        ("beta:b", "case-b", 1, "PASS", 3.0, 0.6),
        ("beta:b", "case-b", 2, "PASS", 4.0, 0.5),
    ]
    # Insert in scrambled order to verify sort.
    trials = [
        _make_trial(
            model=m,
            test_case=c,
            trial_index=i,
            status=s,
            duration=d,
            score=sc,
        )
        for (m, c, i, s, d, sc) in reversed(spec)
    ]
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")

    # No HTML.
    for tag in ("<b>", "</b>", "<span", "<i>", "</i>", "<u>", "</u>"):
        assert tag not in text

    rows = _summary_rows(text)
    keys = [
        (cells[COL_MODEL], cells[COL_CASE], int(cells[COL_TRIAL]))
        for cells in (_row_cells(r) for r in rows)
    ]
    assert keys == sorted(keys)

    # Status icons present for each row.
    for r in rows:
        cells = _row_cells(r)
        status_cell = cells[COL_STATUS]
        # Every status cell starts with an icon and a space.
        assert re.match(r"^\S+\s+[A-Z]+$", status_cell), status_cell

    # Per-case best bolding:
    # case-a PASS/EXCELLENT trials:
    #   (alpha:a/1, PASS, dur=1.0, score=0.9)
    #   (alpha:a/2, EXCELLENT, dur=1.5, score=1.0)
    #   (beta:b/2, PASS, dur=2.0, score=0.8)
    # -> min duration 1.0 (alpha:a/1), max score 1.0 (alpha:a/2)
    by_key = {
        (cells[COL_MODEL], cells[COL_CASE], int(cells[COL_TRIAL])): cells
        for cells in (_row_cells(r) for r in rows)
    }
    assert by_key[("alpha:a", "case-a", 1)][COL_DURATION] == "**1.00**"
    assert by_key[("alpha:a", "case-a", 2)][COL_SCORE] == "**1.00**"
    # case-a FAIL/TIMEOUT rows must not be bolded anywhere.
    for r in rows:
        cells = _row_cells(r)
        status_text = cells[COL_STATUS]
        if any(bad in status_text for bad in ("FAIL", "TIMEOUT", "ERROR")):
            assert "**" not in "|".join(cells)

    # case-b PASS trials: (alpha:a/2, dur=2.0, score=0.7), (beta:b/1, dur=3.0,
    # score=0.6), (beta:b/2, dur=4.0, score=0.5). Best duration=2.0
    # (alpha:a/2), best score=0.7 (alpha:a/2).
    assert by_key[("alpha:a", "case-b", 2)][COL_DURATION] == "**2.00**"
    assert by_key[("alpha:a", "case-b", 2)][COL_SCORE] == "**0.70**"


# ---------------------------------------------------------------------------
# EXPERIMENT-RUNNER:E2E-004 — user-scannable report
# ---------------------------------------------------------------------------


def test_user_scannable_report_after_run(tmp_path: Path) -> None:
    """A representative experiment yields a scannable report."""
    spec: list[tuple[str, str, int, TrialStatus, float, float | None]] = [
        ("alpha:a", "case-a", 1, "EXCELLENT", 1.0, 1.0),
        ("alpha:a", "case-a", 2, "PASS", 2.0, 0.8),
        ("alpha:a", "case-b", 1, "FAIL", 0.4, None),
        ("alpha:a", "case-b", 2, "TIMEOUT", 30.0, None),
        ("beta:b", "case-a", 1, "ERROR", 0.1, None),
        ("beta:b", "case-a", 2, "PASS", 1.5, 0.9),
        ("beta:b", "case-b", 1, "PASS", 3.0, 0.7),
        ("beta:b", "case-b", 2, "EXCELLENT", 2.5, 1.0),
    ]
    trials = [
        _make_trial(
            model=m,
            test_case=c,
            trial_index=i,
            status=s,
            duration=d,
            score=sc,
        )
        for (m, c, i, s, d, sc) in spec
    ]
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")

    # Sorted rows.
    rows = _summary_rows(text)
    keys = [
        (cells[COL_MODEL], cells[COL_CASE], int(cells[COL_TRIAL]))
        for cells in (_row_cells(r) for r in rows)
    ]
    assert keys == sorted(keys)

    # All five icons appear at least once.
    for icon in ("👍", "✅", "❌", "⏱️", "⚠️"):
        assert icon in text, f"missing icon {icon}"

    # At least one bolded cell per test case that has eligible trials.
    # case-a has EXCELLENT/PASS rows; case-b has PASS/EXCELLENT rows.
    # The summary section must contain bold markers.
    summary_text = "\n".join(rows)
    assert "**" in summary_text

    # No HTML.
    for tag in ("<b>", "</b>", "<span", "<i>", "</i>", "<u>", "</u>"):
        assert tag not in text
