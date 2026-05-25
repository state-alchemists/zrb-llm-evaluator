# COVERS: REQ-030, REQ-031, REQ-032, REQ-033, REQ-034, REQ-035, REQ-036,
#         REQ-037, REQ-038, REQ-039, REQ-040, REQ-041, REQ-042, REQ-043,
#         NFR-002, NFR-003, NFR-004,
#         UT-A001, UT-A002, UT-A003, UT-A004, UT-A005, UT-A006, UT-A007,
#         UT-A008, UT-A009, UT-A010, UT-A011, UT-A012, UT-A013, UT-A014,
#         UT-A015, UT-A016, UT-A017, UT-A018, UT-A019, UT-A020, UT-A021,
#         UT-A022, UT-A023, UT-A024, UT-A025, UT-A026, UT-A027

"""Unit tests for the aggregate sections of the Markdown report."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from zrb_llm_evaluator.models import (
    Experiment,
    ExperimentConfig,
    TrialResult,
    ValidationResult,
)
from zrb_llm_evaluator.reporter import (
    generate_json_report,
    generate_markdown_report,
)

TrialStatus = Literal["EXCELLENT", "PASS", "FAIL", "TIMEOUT", "ERROR"]

GOLDEN_DIR = Path(__file__).resolve().parent.parent / "golden" / "aggregate"

AGGREGATE_HEADERS: tuple[str, ...] = (
    "## Overall Status",
    "## By Model",
    "## By Test Case",
    "## Grid",
    "## Failing / Timeout Trials",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trial(
    model: str = "openai:gpt-4o",
    test_case: str = "case-a",
    trial_index: int = 1,
    status: TrialStatus = "PASS",
    duration: float = 1.0,
    score: float | None = None,
    total_tokens: int = 0,
    tool_call_count: int = 0,
    trial_id: str | None = None,
) -> TrialResult:
    """Construct a TrialResult with sensible defaults for rendering tests."""
    vr: ValidationResult | None = None
    if score is not None:
        vr_status: Literal["EXCELLENT", "PASS", "FAIL"]
        if status in ("EXCELLENT", "PASS"):
            vr_status = status
        else:
            vr_status = "FAIL"
        vr = ValidationResult(status=vr_status, score=score, details=[])
    fixed_id = trial_id or f"trial-{model}-{test_case}-{trial_index}"
    return TrialResult(
        id=fixed_id,
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


def _make_experiment(
    results: list[TrialResult], exp_id: str = "exp-fixed"
) -> Experiment:
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
        id=exp_id,
        config=cfg,
        results=results,
        started_at=started,
        completed_at=completed,
    )


def _slice_aggregate_region(text: str) -> str:
    """Return the substring from the ``**Total trials**:`` line up to ``## Summary``."""
    start_marker = "**Total trials**:"
    end_marker = "## Summary"
    start = text.find(start_marker)
    end = text.find(end_marker)
    assert start != -1, "expected **Total trials**: marker"
    assert end != -1, "expected ## Summary marker"
    assert start < end, "expected aggregate region before Summary"
    return text[start:end]


def _slice_section(text: str, header: str) -> str:
    """Return the body of section ``header`` up to the next ``## ``-prefixed header."""
    start = text.find(header)
    assert start != -1, f"expected section {header}"
    body_start = start + len(header)
    next_idx = text.find("\n## ", body_start)
    if next_idx == -1:
        return text[body_start:]
    return text[body_start:next_idx]


_HEADER_FIRST_CELLS: frozenset[str] = frozenset(
    {"Model", "Status", "Test Case"}
)


def _table_rows(section: str) -> list[str]:
    """Return data rows (no header, no separator) from a Markdown table block."""
    rows: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if set(stripped.replace("|", "").strip()) <= {"-", " "}:
            continue
        cells = _row_cells(stripped)
        if cells and cells[0] in _HEADER_FIRST_CELLS:
            continue
        rows.append(stripped)
    return rows


def _row_cells(row: str) -> list[str]:
    inner = row.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [c.strip() for c in inner.split("|")]


def _two_by_two_by_two_trials() -> list[TrialResult]:
    """A 2x2x2 fixture used by UT-A001."""
    return [
        _make_trial(model=m, test_case=c, trial_index=i, status="PASS", duration=1.0)
        for m in ("alpha:a", "beta:b")
        for c in ("case-a", "case-b")
        for i in (1, 2)
    ]


def _all_five_status_fixture() -> list[TrialResult]:
    """A fixture that covers every status at least once."""
    spec: list[tuple[str, str, int, TrialStatus, float]] = [
        ("alpha:a", "case-a", 1, "EXCELLENT", 1.0),
        ("alpha:a", "case-a", 2, "PASS", 2.0),
        ("alpha:a", "case-b", 1, "FAIL", 0.5),
        ("alpha:a", "case-b", 2, "TIMEOUT", 30.0),
        ("beta:b", "case-a", 1, "ERROR", 0.1),
        ("beta:b", "case-a", 2, "PASS", 1.5),
        ("beta:b", "case-b", 1, "PASS", 3.0),
        ("beta:b", "case-b", 2, "EXCELLENT", 2.5),
    ]
    return [
        _make_trial(
            model=m, test_case=c, trial_index=i, status=s, duration=d, score=0.8
        )
        for (m, c, i, s, d) in spec
    ]


# ---------------------------------------------------------------------------
# UT-A001 / REQ-030
# ---------------------------------------------------------------------------


def test_aggregates_sections_present_in_fixed_order(tmp_path: Path) -> None:
    """Headers appear in canonical order and before ``## Summary``."""
    exp = _make_experiment(_two_by_two_by_two_trials())
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")

    positions = [text.find(h) for h in AGGREGATE_HEADERS]
    assert all(p != -1 for p in positions), positions
    assert positions == sorted(positions), positions
    summary_pos = text.find("## Summary")
    assert summary_pos != -1
    assert positions[-1] < summary_pos


# ---------------------------------------------------------------------------
# UT-A002 / REQ-031
# ---------------------------------------------------------------------------


def test_summary_and_details_sections_unchanged(tmp_path: Path) -> None:
    """The Summary + Per-Trial Details substrings match the committed golden."""
    exp = _make_experiment(_all_five_status_fixture())
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")

    summary_body = "## Summary" + _slice_section(text, "## Summary")
    details_body = "## Per-Trial Details" + _slice_section(text, "## Per-Trial Details")
    combined = summary_body + details_body

    golden_path = GOLDEN_DIR / "report_summary_and_details.md"
    assert golden_path.exists(), f"missing golden: {golden_path}"
    assert combined == golden_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# UT-A003 / REQ-032
# ---------------------------------------------------------------------------


def test_aggregate_status_cells_use_canonical_icons(tmp_path: Path) -> None:
    """Only the five canonical icons appear in status-bearing aggregate cells."""
    exp = _make_experiment(_all_five_status_fixture())
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")
    region = _slice_aggregate_region(text)

    # Every status word that appears in the aggregate region must be paired
    # with its canonical icon immediately preceding it.
    expected_pairs = {
        "EXCELLENT": "👍",
        "PASS": "✅",
        "FAIL": "❌",
        "TIMEOUT": "⏱️",
        "ERROR": "⚠️",
    }
    for status, icon in expected_pairs.items():
        if status in region:
            assert f"{icon} {status}" in region, (status, icon)


# ---------------------------------------------------------------------------
# UT-A004 / REQ-033
# ---------------------------------------------------------------------------


def test_results_json_unaffected_by_aggregates(tmp_path: Path) -> None:
    """``results.json`` byte content matches the committed golden."""
    exp = _make_experiment(_all_five_status_fixture())
    out = tmp_path / "results.json"
    generate_json_report(exp, out)
    produced = out.read_bytes()
    golden_path = GOLDEN_DIR / "results.json"
    assert golden_path.exists(), f"missing golden: {golden_path}"
    assert produced == golden_path.read_bytes()
    # And it has no top-level ``aggregates`` field.
    import json as _json

    data = _json.loads(produced.decode("utf-8"))
    assert "aggregates" not in data


# ---------------------------------------------------------------------------
# UT-A005 / REQ-034
# ---------------------------------------------------------------------------


def test_aggregates_region_is_byte_identical_on_rerender(tmp_path: Path) -> None:
    """Two renders of the same Experiment produce identical aggregate regions."""
    exp = _make_experiment(_all_five_status_fixture())
    out1 = tmp_path / "report1.md"
    out2 = tmp_path / "report2.md"
    generate_markdown_report(exp, out1)
    generate_markdown_report(exp, out2)
    r1 = _slice_aggregate_region(out1.read_text(encoding="utf-8"))
    r2 = _slice_aggregate_region(out2.read_text(encoding="utf-8"))
    assert r1 == r2


# ---------------------------------------------------------------------------
# UT-A006 / REQ-035
# ---------------------------------------------------------------------------


def test_overall_status_rows_in_canonical_order(tmp_path: Path) -> None:
    """Overall Status rows appear in canonical order, omitting ERROR (count 0)."""
    trials: list[TrialResult] = []
    idx = 0
    for status in (["EXCELLENT"] * 4 + ["PASS"] * 2 + ["FAIL"] + ["TIMEOUT"]):
        idx += 1
        trials.append(
            _make_trial(
                model="m:1",
                test_case=f"case-{idx}",
                trial_index=1,
                status=status,  # type: ignore[arg-type]  # values are valid TrialStatus literals
                duration=1.0,
            )
        )
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")
    section = _slice_section(text, "## Overall Status")
    rows = _table_rows(section)
    statuses = [_row_cells(r)[0].split(" ", 1)[-1] for r in rows]
    assert statuses == ["EXCELLENT", "PASS", "FAIL", "TIMEOUT"]
    assert "ERROR" not in statuses


# ---------------------------------------------------------------------------
# UT-A007 / REQ-035
# ---------------------------------------------------------------------------


def test_overall_status_omits_zero_count_statuses(tmp_path: Path) -> None:
    """Statuses with zero count are not rendered."""
    trials = [
        _make_trial(
            model="m:1",
            test_case=f"c-{i}",
            trial_index=1,
            status="EXCELLENT",
            duration=1.0,
        )
        for i in range(10)
    ]
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")
    rows = _table_rows(_slice_section(text, "## Overall Status"))
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# UT-A008 / REQ-035
# ---------------------------------------------------------------------------


def test_overall_status_percentage_one_decimal(tmp_path: Path) -> None:
    """Percentages render with exactly one decimal place."""
    trials: list[TrialResult] = []
    for i in range(3):
        trials.append(
            _make_trial(
                model="m:1",
                test_case=f"case-fail-{i}",
                trial_index=1,
                status="FAIL",
                duration=1.0,
            )
        )
    for i in range(5):
        trials.append(
            _make_trial(
                model="m:1",
                test_case=f"case-pass-{i}",
                trial_index=1,
                status="PASS",
                duration=1.0,
            )
        )
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")
    rows = _table_rows(_slice_section(text, "## Overall Status"))
    fail_row = [r for r in rows if "FAIL" in r][0]
    cells = _row_cells(fail_row)
    assert cells[2] == "37.5", cells


# ---------------------------------------------------------------------------
# UT-A009 / REQ-035
# ---------------------------------------------------------------------------


def test_total_trials_bold_line_precedes_overall_status(tmp_path: Path) -> None:
    """The ``**Total trials**: N`` line immediately precedes ``## Overall Status``."""
    trials = [
        _make_trial(
            model="m:1",
            test_case=f"c-{i}",
            trial_index=1,
            status="PASS",
            duration=1.0,
        )
        for i in range(8)
    ]
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")
    lines = text.split("\n")
    overall_idx = lines.index("## Overall Status")
    # Skip blank lines walking backward.
    prev_idx = overall_idx - 1
    while prev_idx >= 0 and lines[prev_idx].strip() == "":
        prev_idx -= 1
    assert lines[prev_idx] == "**Total trials**: 8", lines[prev_idx]


# ---------------------------------------------------------------------------
# UT-A010 / REQ-036
# ---------------------------------------------------------------------------


def test_by_model_avg_duration_includes_failed_trials(tmp_path: Path) -> None:
    """Avg duration includes FAIL/TIMEOUT/ERROR trials."""
    trials = [
        _make_trial(
            model="m:1",
            test_case="c-1",
            trial_index=1,
            status="PASS",
            duration=10.0,
        ),
        _make_trial(
            model="m:1",
            test_case="c-2",
            trial_index=1,
            status="PASS",
            duration=30.0,
        ),
        _make_trial(
            model="m:1",
            test_case="c-3",
            trial_index=1,
            status="FAIL",
            duration=20.0,
        ),
    ]
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")
    rows = _table_rows(_slice_section(text, "## By Model"))
    cells = _row_cells(rows[0])
    assert cells[-1] == "20.0", cells


# ---------------------------------------------------------------------------
# UT-A011 / REQ-036
# ---------------------------------------------------------------------------


def test_by_model_avg_duration_one_decimal(tmp_path: Path) -> None:
    """Avg duration renders with one decimal place."""
    trials = [
        _make_trial(
            model="m:1",
            test_case="c-1",
            trial_index=1,
            status="PASS",
            duration=1.0,
        ),
        _make_trial(
            model="m:1",
            test_case="c-2",
            trial_index=1,
            status="PASS",
            duration=2.0,
        ),
    ]
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")
    rows = _table_rows(_slice_section(text, "## By Model"))
    cells = _row_cells(rows[0])
    assert cells[-1] == "1.5", cells


# ---------------------------------------------------------------------------
# UT-A012 / REQ-036
# ---------------------------------------------------------------------------


def test_by_model_rows_sorted_ascending(tmp_path: Path) -> None:
    """By Model rows are sorted ASC by model name; expected columns present."""
    trials: list[TrialResult] = []
    for m in ("zeta:z", "alpha:a", "mid:m"):
        trials.append(
            _make_trial(
                model=m, test_case="c-1", trial_index=1, status="PASS", duration=1.0
            )
        )
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")
    section = _slice_section(text, "## By Model")
    rows = _table_rows(section)
    models = [_row_cells(r)[0] for r in rows]
    assert models == ["alpha:a", "mid:m", "zeta:z"], models
    for token in ("👍", "✅", "❌", "⏱️", "⚠️", "Avg dur (s)"):
        assert token in section, token


# ---------------------------------------------------------------------------
# UT-A013 / REQ-037
# ---------------------------------------------------------------------------


def test_by_test_case_omits_avg_duration_column(tmp_path: Path) -> None:
    """By Test Case section has no ``Avg dur`` column."""
    trials = [
        _make_trial(
            model="m:1", test_case="c-a", trial_index=1, status="PASS", duration=1.0
        )
    ]
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")
    section = _slice_section(text, "## By Test Case")
    assert "Avg dur" not in section, section


# ---------------------------------------------------------------------------
# UT-A014 / REQ-037
# ---------------------------------------------------------------------------


def test_by_test_case_rows_sorted_ascending(tmp_path: Path) -> None:
    """By Test Case rows are sorted ASC by case name."""
    trials: list[TrialResult] = []
    for c in ("refactor", "bug-fix", "feature"):
        trials.append(
            _make_trial(
                model="m:1", test_case=c, trial_index=1, status="PASS", duration=1.0
            )
        )
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")
    rows = _table_rows(_slice_section(text, "## By Test Case"))
    cases = [_row_cells(r)[0] for r in rows]
    assert cases == ["bug-fix", "feature", "refactor"], cases


# ---------------------------------------------------------------------------
# UT-A015 / REQ-038
# ---------------------------------------------------------------------------


def test_grid_dimensions_and_axis_sort(tmp_path: Path) -> None:
    """Grid has correct dimensions with sorted axes."""
    trials: list[TrialResult] = []
    for m in ("zeta:z", "alpha:a"):
        for c in ("z-case", "a-case", "m-case"):
            trials.append(
                _make_trial(
                    model=m,
                    test_case=c,
                    trial_index=1,
                    status="PASS",
                    duration=1.0,
                )
            )
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")
    section = _slice_section(text, "## Grid")
    rows = _table_rows(section)
    assert len(rows) == 2, rows
    # Header row (first row in the table) is the column listing.
    # _table_rows skips the separator; but the header row is a real row.
    # Recompute headers from raw section to be precise.
    header_line = next(
        line for line in section.splitlines() if line.strip().startswith("| Model |")
    )
    header_cells = _row_cells(header_line)
    assert header_cells == ["Model", "a-case", "m-case", "z-case"], header_cells
    # Drop the header row from data rows.
    data_rows = [r for r in rows if _row_cells(r)[0] != "Model"]
    models = [_row_cells(r)[0] for r in data_rows]
    assert models == ["alpha:a", "zeta:z"], models


# ---------------------------------------------------------------------------
# UT-A016 / REQ-038
# ---------------------------------------------------------------------------


def test_grid_cell_icons_in_trial_index_order(tmp_path: Path) -> None:
    """Grid cell icons appear in trial_index ASC order."""
    spec: list[tuple[int, TrialStatus]] = [
        (3, "PASS"),
        (1, "EXCELLENT"),
        (2, "FAIL"),
    ]
    trials = [
        _make_trial(
            model="m:1",
            test_case="case1",
            trial_index=i,
            status=s,
            duration=1.0,
        )
        for i, s in spec
    ]
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")
    section = _slice_section(text, "## Grid")
    assert "👍 ❌ ✅" in section, section


# ---------------------------------------------------------------------------
# UT-A017 / REQ-039
# ---------------------------------------------------------------------------


def test_grid_cell_empty_renders_em_dash(tmp_path: Path) -> None:
    """A Grid cell with no trials renders as the literal em dash."""
    trials = [
        _make_trial(
            model="m:1", test_case="case1", trial_index=1, status="PASS", duration=1.0
        ),
        _make_trial(
            model="m:2", test_case="case1", trial_index=1, status="PASS", duration=1.0
        ),
        _make_trial(
            model="m:2", test_case="case2", trial_index=1, status="PASS", duration=1.0
        ),
    ]
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")
    section = _slice_section(text, "## Grid")
    # m:1 row for case2 should be em dash.
    rows = [
        line for line in section.splitlines() if line.strip().startswith("| m:1 |")
    ]
    assert rows, section
    cells = _row_cells(rows[0])
    # Cells: [model, case1, case2]
    assert cells[2] == "—", cells


# ---------------------------------------------------------------------------
# UT-A018 / REQ-040
# ---------------------------------------------------------------------------


def test_failing_table_includes_fail_timeout_error(tmp_path: Path) -> None:
    """All three failure statuses appear as rows; header matches exactly."""
    trials = [
        _make_trial(
            model="m:1", test_case="c-1", trial_index=1, status="FAIL", duration=1.0
        ),
        _make_trial(
            model="m:1", test_case="c-2", trial_index=1, status="TIMEOUT", duration=2.0
        ),
        _make_trial(
            model="m:1", test_case="c-3", trial_index=1, status="ERROR", duration=3.0
        ),
        _make_trial(
            model="m:1", test_case="c-4", trial_index=1, status="PASS", duration=4.0
        ),
    ]
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")
    section = _slice_section(text, "## Failing / Timeout Trials")
    assert "| Model | Test Case | Trial | Status | Duration (s) |" in section, section
    rows = _table_rows(section)
    statuses = [_row_cells(r)[3] for r in rows if _row_cells(r)[0] != "Model"]
    assert any("FAIL" in s for s in statuses)
    assert any("TIMEOUT" in s for s in statuses)
    assert any("ERROR" in s for s in statuses)


# ---------------------------------------------------------------------------
# UT-A019 / REQ-040
# ---------------------------------------------------------------------------


def test_failing_table_sorted_by_model_case_trial(tmp_path: Path) -> None:
    """Failing rows are sorted by (model, case, trial_index) ASC."""
    spec: list[tuple[str, str, int, TrialStatus, float]] = [
        ("zeta:z", "c-b", 2, "FAIL", 9.0),
        ("alpha:a", "c-b", 1, "TIMEOUT", 1.25),
        ("alpha:a", "c-a", 2, "ERROR", 4.50),
        ("alpha:a", "c-a", 1, "FAIL", 0.50),
    ]
    trials = [
        _make_trial(
            model=m, test_case=c, trial_index=i, status=s, duration=d
        )
        for (m, c, i, s, d) in spec
    ]
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")
    section = _slice_section(text, "## Failing / Timeout Trials")
    rows = [
        _row_cells(r)
        for r in _table_rows(section)
        if _row_cells(r)[0] != "Model"
    ]
    keys = [(c[0], c[1], int(c[2])) for c in rows]
    assert keys == [
        ("alpha:a", "c-a", 1),
        ("alpha:a", "c-a", 2),
        ("alpha:a", "c-b", 1),
        ("zeta:z", "c-b", 2),
    ], keys
    # Duration one decimal place.
    durs = [c[4] for c in rows]
    assert durs == ["0.5", "4.5", "1.2", "9.0"], durs


# ---------------------------------------------------------------------------
# UT-A020 / REQ-041
# ---------------------------------------------------------------------------


def test_failing_section_empty_state_literal(tmp_path: Path) -> None:
    """Empty-state literal appears with no table header."""
    trials = [
        _make_trial(
            model="m:1",
            test_case=f"c-{i}",
            trial_index=1,
            status="EXCELLENT",
            duration=1.0,
        )
        for i in range(4)
    ]
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")
    section = _slice_section(text, "## Failing / Timeout Trials")
    assert "No failing or timeout trials." in section, section
    assert "| Model | Test Case | Trial | Status | Duration (s) |" not in section, (
        section
    )


# ---------------------------------------------------------------------------
# UT-A021 / REQ-042
# ---------------------------------------------------------------------------


def test_aggregates_contain_no_html(tmp_path: Path) -> None:
    """Aggregate region contains no HTML markup."""
    exp = _make_experiment(_all_five_status_fixture())
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")
    region = _slice_aggregate_region(text)
    for forbidden in ("<", ">", "&lt;", "&gt;", "<br", "<table"):
        assert forbidden not in region, (forbidden, region)


# ---------------------------------------------------------------------------
# UT-A022 / REQ-030
# ---------------------------------------------------------------------------


def test_aggregates_render_with_zero_trials(tmp_path: Path) -> None:
    """Empty results yield header-only tables and the empty-state failing literal."""
    exp = _make_experiment([])
    out = tmp_path / "report.md"
    generate_markdown_report(exp, out)
    text = out.read_text(encoding="utf-8")
    assert "**Total trials**: 0" in text
    for header in AGGREGATE_HEADERS:
        assert header in text, header
    # Overall, By Model, By Test Case, Grid: no data rows.
    for header in (
        "## Overall Status",
        "## By Model",
        "## By Test Case",
        "## Grid",
    ):
        section = _slice_section(text, header)
        rows = _table_rows(section)
        # Only the header row (if present) — no data rows beyond it.
        data_rows = [r for r in rows if _row_cells(r)[0] not in {"Model", "Status", "Test Case"}]
        assert data_rows == [], (header, rows)
    failing = _slice_section(text, "## Failing / Timeout Trials")
    assert "No failing or timeout trials." in failing


# ---------------------------------------------------------------------------
# UT-A023 / NFR-002
# ---------------------------------------------------------------------------


def test_aggregates_render_linear_in_trial_count(tmp_path: Path) -> None:
    """Rendering 1000 trials completes under 2.0s."""
    trials: list[TrialResult] = []
    statuses: tuple[TrialStatus, ...] = (
        "EXCELLENT",
        "PASS",
        "FAIL",
        "TIMEOUT",
        "ERROR",
    )
    for mi in range(10):
        for ci in range(10):
            for ti in range(10):
                trials.append(
                    _make_trial(
                        model=f"m:{mi:02d}",
                        test_case=f"c-{ci:02d}",
                        trial_index=ti + 1,
                        status=statuses[(mi + ci + ti) % 5],
                        duration=float(ti + 1),
                    )
                )
    exp = _make_experiment(trials)
    out = tmp_path / "report.md"
    t0 = time.perf_counter()
    generate_markdown_report(exp, out)
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0, f"render took {elapsed:.2f}s"


# ---------------------------------------------------------------------------
# UT-A024 / NFR-003
# ---------------------------------------------------------------------------


def test_results_json_byte_identical_to_pregolden(tmp_path: Path) -> None:
    """``results.json`` is byte-equal to the committed golden."""
    exp = _make_experiment(_all_five_status_fixture())
    out = tmp_path / "results.json"
    generate_json_report(exp, out)
    golden_path = GOLDEN_DIR / "results.json"
    assert golden_path.exists(), f"missing golden: {golden_path}"
    assert out.read_bytes() == golden_path.read_bytes()


# ---------------------------------------------------------------------------
# UT-A025 / NFR-004
# ---------------------------------------------------------------------------


def test_aggregates_byte_identical_across_two_calls(tmp_path: Path) -> None:
    """Two calls on the same Experiment yield identical aggregate regions."""
    # Different fixture from UT-A005: covers all 5 statuses with multiple trials.
    spec: list[tuple[str, str, int, TrialStatus, float]] = [
        ("m:1", "c-a", 1, "EXCELLENT", 1.0),
        ("m:1", "c-a", 2, "PASS", 1.5),
        ("m:1", "c-b", 1, "FAIL", 0.3),
        ("m:2", "c-a", 1, "TIMEOUT", 12.0),
        ("m:2", "c-b", 1, "ERROR", 0.1),
        ("m:2", "c-b", 2, "PASS", 2.0),
    ]
    trials = [
        _make_trial(
            model=m, test_case=c, trial_index=i, status=s, duration=d
        )
        for (m, c, i, s, d) in spec
    ]
    exp = _make_experiment(trials)
    out1 = tmp_path / "r1.md"
    out2 = tmp_path / "r2.md"
    generate_markdown_report(exp, out1)
    generate_markdown_report(exp, out2)
    r1 = _slice_aggregate_region(out1.read_text(encoding="utf-8"))
    r2 = _slice_aggregate_region(out2.read_text(encoding="utf-8"))
    assert r1 == r2


# ---------------------------------------------------------------------------
# UT-A026 / REQ-043 — whole-file byte equality across re-renders
# ---------------------------------------------------------------------------


# @sdlc REQ-043
def test_whole_report_byte_identical_on_rerender(tmp_path: Path) -> None:
    """Two renders of the same Experiment produce a byte-identical whole file.

    Strengthens UT-A005, which only checks the aggregate region. REQ-043
    requires the entire file (header, aggregates, Summary, Per-Trial Details)
    to be byte-equal across re-renders.
    """
    exp = _make_experiment(_all_five_status_fixture())
    out1 = tmp_path / "report1.md"
    out2 = tmp_path / "report2.md"
    generate_markdown_report(exp, out1)
    generate_markdown_report(exp, out2)
    assert out1.read_bytes() == out2.read_bytes()


# ---------------------------------------------------------------------------
# UT-A027 / REQ-043 — Generated timestamp derived from experiment timestamps
# ---------------------------------------------------------------------------


# @sdlc REQ-043
def test_generated_timestamp_derived_from_experiment_timestamps(
    tmp_path: Path,
) -> None:
    """The ``**Generated**:`` header line is derived from experiment timestamps.

    Case (a): when ``completed_at`` is set, its isoformat appears in the line.
    Case (b): when ``completed_at`` is ``None``, the line falls back to
    ``started_at``'s isoformat.
    In neither case is wall-clock time at render permitted to leak into the
    header — that is what makes UT-A026's whole-file byte-equality possible.
    """
    # Case (a): completed_at populated (default fixture value).
    exp_a = _make_experiment(_all_five_status_fixture())
    out_a = tmp_path / "report_a.md"
    generate_markdown_report(exp_a, out_a)
    text_a = out_a.read_text(encoding="utf-8")
    assert exp_a.completed_at is not None
    assert f"**Generated**: {exp_a.completed_at.isoformat()}\n" in text_a

    # Case (b): completed_at=None → fall back to started_at.
    exp_b = _make_experiment(_all_five_status_fixture())
    exp_b.completed_at = None
    out_b = tmp_path / "report_b.md"
    generate_markdown_report(exp_b, out_b)
    text_b = out_b.read_text(encoding="utf-8")
    assert f"**Generated**: {exp_b.started_at.isoformat()}\n" in text_b
