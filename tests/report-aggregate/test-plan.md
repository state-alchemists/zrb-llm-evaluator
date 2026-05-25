# Test Plan: report-aggregate

**Convention**: pytest — `test_<component>_<condition>_<expected>()`. Tests live in `tests/test_reporter_aggregate.py` (sibling to the existing `tests/test_reporter.py`).

## Unit Tests

| ID | Req | Test Name | Input | Expected |
|----|-----|-----------|-------|----------|
| UT-A001 | REQ-030 | test_aggregates_sections_present_in_fixed_order | Experiment with 2 models × 2 cases × 2 trials | `report.md` contains the headers `## Overall Status`, `## By Model`, `## By Test Case`, `## Grid`, `## Failing / Timeout Trials` in that order, each appearing before `## Summary` |
| UT-A002 | REQ-031 | test_summary_and_details_sections_unchanged | Same fixture used for the existing test_markdown_report golden | The `## Summary` and `## Per-Trial Details` substrings (rows, sort order, bolding) are byte-identical to the pre-feature golden snapshot for those regions |
| UT-A003 | REQ-032 | test_aggregate_status_cells_use_canonical_icons | Fixture with all five statuses present | Every status cell across the five new sections matches the mapping (👍/✅/❌/⏱️/⚠️); no other glyph appears in status columns |
| UT-A004 | REQ-033 | test_results_json_unaffected_by_aggregates | Same fixture rendered twice (pre-feature golden vs. post-feature) | `results.json` byte content is identical; no top-level `aggregates` key appears |
| UT-A005 | REQ-034 | test_aggregates_region_is_byte_identical_on_rerender | Render `generate_markdown_report` twice into different paths | Aggregate-region substring (between header and `## Summary`) is byte-identical across the two outputs |
| UT-A006 | REQ-035 | test_overall_status_rows_in_canonical_order | Experiment with 4 EXCELLENT, 2 PASS, 1 FAIL, 1 TIMEOUT, 0 ERROR | Rows appear in order EXCELLENT, PASS, FAIL, TIMEOUT; ERROR row is omitted (zero trials); column headers are `Status \| Count \| %` |
| UT-A007 | REQ-035 | test_overall_status_omits_zero_count_statuses | All-EXCELLENT experiment (10 trials) | Table has exactly one body row (EXCELLENT) |
| UT-A008 | REQ-035 | test_overall_status_percentage_one_decimal | 3 of 8 trials FAIL | The FAIL row's `%` cell renders as `37.5` (one decimal place) |
| UT-A009 | REQ-035 | test_total_trials_bold_line_precedes_overall_status | Experiment with 8 trials | The line `**Total trials**: 8` appears immediately above the `## Overall Status` table header |
| UT-A010 | REQ-036 | test_by_model_avg_duration_includes_failed_trials | Model `m1` with durations [10.0, 30.0, 20.0] where one is FAIL | `Avg dur (s)` cell for m1 reads `20.0` (mean over all three, including the FAIL) |
| UT-A011 | REQ-036 | test_by_model_avg_duration_one_decimal | Durations [1.0, 2.0] → mean 1.5 | `Avg dur (s)` cell renders as `1.5` (not `1.50` or `1`) |
| UT-A012 | REQ-036 | test_by_model_rows_sorted_ascending | Models `zeta`, `alpha`, `mid` in fixture | Row order in `## By Model` is `alpha`, `mid`, `zeta`; column headers include `👍`, `✅`, `❌`, `⏱️`, `⚠️`, `Avg dur (s)` |
| UT-A013 | REQ-037 | test_by_test_case_omits_avg_duration_column | Any non-empty experiment | `## By Test Case` table header contains exactly `Test Case \| Trials \| 👍 \| ✅ \| ❌ \| ⏱️ \| ⚠️`; no `Avg dur` substring appears within this section |
| UT-A014 | REQ-037 | test_by_test_case_rows_sorted_ascending | Test cases `refactor`, `bug-fix`, `feature` | Row order is `bug-fix`, `feature`, `refactor` |
| UT-A015 | REQ-038 | test_grid_dimensions_and_axis_sort | 2 models × 3 test cases | Grid header row lists test cases in ASC order; body rows list models in ASC order |
| UT-A016 | REQ-038 | test_grid_cell_icons_in_trial_index_order | Cell `(m1, case1)` with trials 1=EXCELLENT, 2=FAIL, 3=PASS | Cell renders exactly `👍 ❌ ✅` (single-space-separated, no status text) |
| UT-A017 | REQ-039 | test_grid_cell_empty_renders_em_dash | Model `m1` has no trials for `case2` (other cells populated) | Cell `(m1, case2)` renders as `—` (U+2014) |
| UT-A018 | REQ-040 | test_failing_table_includes_fail_timeout_error | Fixture with one of each: FAIL, TIMEOUT, ERROR | All three appear as rows in `## Failing / Timeout Trials`; columns are `Model \| Test Case \| Trial \| Status \| Duration (s)` |
| UT-A019 | REQ-040 | test_failing_table_sorted_by_model_case_trial | Rows seeded out of order | Output order is `(model ASC, test_case ASC, trial_index ASC)`; `Duration (s)` is one decimal place |
| UT-A020 | REQ-041 | test_failing_section_empty_state_literal | All-EXCELLENT experiment | The section emits the header `## Failing / Timeout Trials` followed by the literal line `No failing or timeout trials.` (no table header, no rows) |
| UT-A021 | REQ-042 | test_aggregates_contain_no_html | Fixture covering every section | Substring scan over the aggregate region rejects `<`, `>`, `&lt;`, `&gt;`, `<br`, `<table`, etc. |
| UT-A022 | REQ-030 | test_aggregates_render_with_zero_trials | Experiment with empty `results` list | `**Total trials**: 0` line emitted; Overall Status / By Model / By Test Case tables have header rows only; Grid renders only its header row; Failing section uses the empty-state literal |
| UT-A023 | NFR-002 | test_aggregates_render_linear_in_trial_count | Synthetic experiment of 1_000 trials (10 models × 10 cases × 10 trials) | `generate_markdown_report` completes under a generous wall-clock budget (e.g., 2.0s) on CI; no quadratic scan over results |
| UT-A024 | NFR-003 | test_results_json_byte_identical_to_pregolden | Reference fixture rendered post-feature | `results.json` bytes match the pre-feature golden file |
| UT-A025 | NFR-004 | test_aggregates_byte_identical_across_two_calls | Same Experiment instance, two `generate_markdown_report` calls into different temp paths | Aggregate-region substrings are equal (duplicates the assertion target of UT-A005 with a different fixture covering all five statuses) |
| UT-A026 | REQ-043 | test_whole_report_byte_identical_on_rerender | Same Experiment instance (covering all five statuses) rendered into two different paths via `generate_markdown_report` | Both files' full byte content is equal — including header (`**Generated**` line), aggregate region, `## Summary`, and `## Per-Trial Details` — not only the aggregate region <!-- added 2026-05-25 (sdlc-test-plan; covers REQ-043 from drift-report-2026-05-25T01-14-05) --> |
| UT-A027 | REQ-043 | test_generated_timestamp_derived_from_experiment_timestamps | (a) Experiment with `completed_at = datetime(2024,1,1,1,0,0,tz=UTC)`; (b) Experiment with `completed_at=None` and `started_at = datetime(2024,1,1,0,0,0,tz=UTC)` — both rendered | (a) The `**Generated**:` header line contains `2024-01-01T01:00:00+00:00`; (b) the line falls back to `2024-01-01T00:00:00+00:00`; neither value depends on wall-clock time at render <!-- added 2026-05-25 (sdlc-test-plan; covers REQ-043 from drift-report-2026-05-25T01-14-05) --> |

## Integration Tests

| ID | Scope | Test Name | Setup | Assertion |
|----|-------|-----------|-------|-----------|
| IT-A001 | reporter ↔ models ↔ runner | test_full_report_aggregates_match_per_trial_summary | Run a real (mocked-subprocess) experiment of 2 models × 2 cases × 3 trials with mixed statuses, then call `generate_markdown_report` | Counts in Overall Status / By Model / By Test Case derived solely from the aggregate tables equal the counts re-derived by parsing the existing `## Summary` table; the Grid's icon sequence per cell matches the per-trial rows for that `(model, test_case)` pair |

## End-to-End Tests

| ID | Story | Scenario | Steps | Expected |
|----|-------|----------|-------|----------|
| E2E-A001 | US-010 | Operator scans a finished experiment for failing models | (1) Run `zrb-llm-evaluator run` with an experiment whose `refactor` case fails on one model; (2) open `report.md` | The first non-header lines of the report are the five aggregate sections; the operator can read total counts, per-model breakdown, and the failing model × test-case rows without scrolling into `## Summary` |

## Property-Based Tests
N/A — no property-testing framework configured in `docs/test-strategy.md` or `docs/tech.md`.

## Design Property Coverage

| Property | Covered By | Notes |
|----------|------------|-------|
| Round-Trip | N/A | design.md declares N/A — aggregate sections are a render-only projection of `Experiment.results`; no new persisted fields. |
| Uniqueness | UT-A012, UT-A014, UT-A015 | Each `model`, `test_case`, and `(model, test_case)` key appears at most once in its respective aggregate table. |
| Atomicity | N/A | design.md declares N/A at the aggregates layer — the existing `generate_markdown_report` atomic write covers the whole file; no separate atomicity surface introduced by this feature. |
| Validation | UT-A022 | Zero-trial Experiment exercises the defensive empty-input paths through every aggregate renderer. |
| Idempotency | UT-A005, UT-A025, UT-A026, UT-A027 | Two successive renders of the same Experiment produce byte-identical aggregate output (UT-A005 / UT-A025) and byte-identical whole-file output (UT-A026); the `**Generated**` timestamp is derived from `experiment.completed_at or experiment.started_at`, not wall-clock time (UT-A027). |

## Rule Coverage

| Rule | Covered By | Notes |
|------|------------|-------|
| RULE-003 (Pydantic for result models) | UT-A018, UT-A024 | Aggregate renderers consume typed `TrialResult` fields; the JSON regression test confirms no leakage into `results.json`. |
| RULE-011 (no `print()` in library code) | (CI gate — ruff T201) | Validated outside the test plan by ruff in CI; no new `print()` introduced. |

## Test Data Strategy
- **Fixtures**: New module-scoped fixtures in `tests/conftest.py` (or a sibling `tests/fixtures_aggregate.py`) build `Experiment` instances directly via Pydantic `model_construct` — no subprocess invocation needed for aggregate-section assertions.
  - `experiment_all_excellent` — 10 trials, all EXCELLENT.
  - `experiment_mixed_statuses` — 2 models × 2 cases × 2 trials covering EXCELLENT/PASS/FAIL/TIMEOUT/ERROR.
  - `experiment_empty` — zero trials.
  - `experiment_large_linear` — 10 × 10 × 10 = 1000 trials for NFR-002.
- **Synthetic data**: Trial durations are seeded as deterministic floats (e.g., `10.0`, `20.0`, `30.0`) so `Avg dur (s)` assertions remain stable. No randomness; no PBT generator (PBT section is N/A).
- **Golden snapshots**: One pre-feature `results.json` golden file (committed under `tests/golden/aggregate/results_pre_feature.json`) and one post-feature reference markdown region (committed under `tests/golden/aggregate/report_aggregates.md`) anchor UT-A002, UT-A004, UT-A024.
- **Cleanup**: Tests write to `tmp_path` (pytest builtin); no shared global state to reset.
