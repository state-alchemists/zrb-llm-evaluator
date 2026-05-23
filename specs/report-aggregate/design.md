# Design: report-aggregate

## Correctness Properties

### Round-Trip
N/A — the aggregate sections are a render-only projection. No new persisted fields, no deserialization path. The source of truth is `Experiment.results`, which already round-trips per the experiment-runner design.

### Uniqueness
The Grid is keyed by `(model, test_case)` pairs derived from `TrialResult` rows. By Model rows are keyed by `model`; By Test Case rows are keyed by `test_case`. Each key appears at most once per table — enforced by populating `dict[str, _Bucket]` accumulators on a single pass and rendering in sorted key order.

### Atomicity
N/A at the aggregates layer — file-level atomic write (temp file + `os.replace`) is already provided by `generate_markdown_report`; the aggregate string is built in memory and concatenated into the same `lines` list before that single atomic write. Either the whole report (header + aggregates + summary + details) is written, or none of it is.

### Validation
Inputs to the aggregate functions are typed `Experiment` / `list[TrialResult]` instances — Pydantic models already validated on construction (RULE-003). No extra runtime validation is required. The reporter must, however, defensively handle:
- An experiment with zero trials → every aggregate table renders zero rows; the Overall Status section emits `**Total trials**: 0` followed by an empty table (header-row only); the Grid renders a single header row with no body; Failing / Timeout follows the empty-state path (REQ-041).
- A status value not present in the canonical icon map → not possible given the `TrialResult.status` enum, but if it somehow occurs the reporter falls back to the bare status text with no icon (matches existing `_status_cell` behavior at `reporter.py:83`).

### Idempotency
Calling `generate_markdown_report` N times on the same `Experiment` produces N byte-identical files. The aggregate computation reads only the input list and a single `_STATUS_ICONS` constant; there is no hidden state, no clock read (the report's `generated_at` uses `experiment.completed_at or experiment.started_at`, already deterministic per `reporter.py:191`).

## API Surface

This feature adds no new public API. The existing public function

```python
def generate_markdown_report(experiment: Experiment, output_path: Path) -> Report
```

(at `src/zrb_llm_evaluator/reporter.py:170`) gains new private helpers but its signature, return type, and error semantics are unchanged.

Internal helpers added (all module-private):

| Helper | Purpose |
|--------|---------|
| `_AggregateBuckets` (frozen dataclass) | Holds `overall: dict[str, int]`, `by_model: dict[str, _StatusCounts]`, `by_case: dict[str, _StatusCounts]`, `by_cell: dict[tuple[str, str], list[TrialResult]]`, `failing: list[TrialResult]`, `model_duration_sum: dict[str, float]`, `total: int`. |
| `_collect_aggregates(results)` | Single O(T) pass that populates an `_AggregateBuckets` instance. |
| `_render_overall_status(b)` | Returns the `## Overall Status` section lines. |
| `_render_by_model(b)` | Returns the `## By Model` section lines. |
| `_render_by_test_case(b)` | Returns the `## By Test Case` section lines. |
| `_render_grid(b)` | Returns the `## Grid` section lines. |
| `_render_failing(b)` | Returns the `## Failing / Timeout Trials` section lines. |

`generate_markdown_report` calls `_collect_aggregates(sorted_results)` once and then appends each renderer's output to `lines` between the existing header block and the existing `## Summary` block.

## Error Handling

| Error | Code | Status | Recovery |
|-------|------|--------|----------|
| Empty `Experiment.results` | — | Aggregates render with zero rows (header-only tables); Overall Status shows `Total trials: 0`; Failing section uses the empty-state literal | None needed |
| `TrialResult.status` outside `_STATUS_ICONS` (defensive only — enum-protected) | — | Cell renders bare status text without icon prefix, mirroring `_status_cell` | None needed; surfaces in review if the enum widens |
| Filesystem write failure during atomic rename | (existing) | Propagates from `generate_markdown_report` as today | Unchanged from experiment-runner design |

## Data Model

| Entity | Fields Used | Notes |
|--------|-------------|-------|
| Experiment | `results` | The list of trials this feature aggregates over |
| TrialResult | `model`, `test_case`, `trial_index`, `status`, `duration` | All fields are required and always populated per the entity dictionary's validation rules; `duration` is non-null even for TIMEOUT/ERROR (per the rule added in this round of requirements) |
| Report | `markdown_path` | Description was updated in the entity dictionary to mention the aggregate sections; no field-shape change |

### Entity Modifications
None. The clarifying edits to `Report.markdown_path` and the new validation rule on `TrialResult.duration` were already mirrored in `requirements/entity-dictionary.md` during the prior `/sdlc-requirements` run.

## Section Layout (illustrative)

Rendered for an experiment with 2 models × 2 test cases × 2 trials, one FAIL:

```
**Total trials**: 8

## Overall Status

| Status | Count | % |
|---|---:|---:|
| 👍 EXCELLENT | 5 | 62.5 |
| ✅ PASS | 2 | 25.0 |
| ❌ FAIL | 1 | 12.5 |

## By Model

| Model | Trials | 👍 | ✅ | ❌ | ⏱️ | ⚠️ | Avg dur (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| openai:gpt-4o | 4 | 2 | 1 | 1 | 0 | 0 | 22.4 |
| google:gemini-2.5-flash | 4 | 3 | 1 | 0 | 0 | 0 | 31.7 |

## By Test Case

| Test Case | Trials | 👍 | ✅ | ❌ | ⏱️ | ⚠️ |
|---|---:|---:|---:|---:|---:|---:|
| bug-fix | 4 | 3 | 1 | 0 | 0 | 0 |
| refactor | 4 | 2 | 1 | 1 | 0 | 0 |

## Grid

| Model | bug-fix | refactor |
|---|---|---|
| google:gemini-2.5-flash | 👍 👍 | 👍 ✅ |
| openai:gpt-4o | 👍 ✅ | 👍 ❌ |

## Failing / Timeout Trials

| Model | Test Case | Trial | Status | Duration (s) |
|---|---|---:|---|---:|
| openai:gpt-4o | refactor | 2 | ❌ FAIL | 31.4 |
```
