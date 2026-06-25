# Feature Spec: report-aggregate

**Feature Key:** REPORT-AGGREGATE

## Requirements

*Requirements cite the source `AC-*` from the problem brief. EARS keywords appear inline.*

- `REQ-030` (AC-013): `report.md` SHALL contain five aggregate sections — `## Overall Status`, `## By Model`, `## By Test Case`, `## Grid`, `## Failing / Timeout Trials` — emitted in that order, between the header lines and the existing `## Summary` table. <!-- updated 2026-06-25 (quickfix-2026-06-25T06-58-37): canonical EARS, migrated from deprecated ubiquitous form -->
- `REQ-031` (AC-013): The existing `## Summary` and `## Per-Trial Details` sections of `report.md` SHALL retain the content and ordering defined by REQ-025 through REQ-029; the aggregate sections are additive and never modify per-trial rows. <!-- updated 2026-06-25 (quickfix-2026-06-25T06-58-37): canonical EARS, migrated from deprecated ubiquitous form -->
- `REQ-032` (AC-013, AC-014, AC-015, AC-016, AC-017): Every status cell in every aggregate section SHALL use the icon mapping already mandated by REQ-029 (`EXCELLENT` → 👍, `PASS` → ✅, `FAIL` → ❌, `TIMEOUT` → ⏱️, `ERROR` → ⚠️). <!-- updated 2026-06-25 (quickfix-2026-06-25T06-58-37): canonical EARS, migrated from deprecated ubiquitous form -->
- `REQ-033` (AC-013): The aggregate sections SHALL be computed from `Experiment.results` at render time only; `results.json` SHALL NOT gain an `aggregates` field or any other byte-level change attributable to this feature. <!-- updated 2026-06-25 (quickfix-2026-06-25T06-58-37): canonical EARS, migrated from deprecated ubiquitous form -->
- `REQ-034` (AC-013): Two renders of the same `Experiment` instance SHALL produce byte-identical aggregate sections (deterministic ordering, formatting, and content). <!-- updated 2026-06-25 (quickfix-2026-06-25T06-58-37): canonical EARS, migrated from deprecated ubiquitous form -->
- `REQ-035` (AC-014): The Overall Status table SHALL contain exactly the columns `Status | Count | %`, with one row per status that has at least one trial, in the canonical order `EXCELLENT, PASS, FAIL, TIMEOUT, ERROR`; the `%` value SHALL be the row's count divided by total trials, rendered to one decimal place; and a bold line `**Total trials**: N` SHALL appear immediately above the table. <!-- updated 2026-06-25 (quickfix-2026-06-25T06-58-37): canonical EARS, migrated from deprecated state-driven form -->
- `REQ-036` (AC-015): The By Model table SHALL contain exactly the columns `Model | Trials | 👍 | ✅ | ❌ | ⏱️ | ⚠️ | Avg dur (s)`, with one row per distinct `TrialResult.model` in the experiment sorted ASC by model name; the `Avg dur (s)` cell SHALL be the arithmetic mean of `duration` over every trial of that model (including FAIL, TIMEOUT, and ERROR), rendered to one decimal place. <!-- updated 2026-06-25 (quickfix-2026-06-25T06-58-37): canonical EARS, migrated from deprecated state-driven form -->
- `REQ-037` (AC-015): The By Test Case table SHALL contain exactly the columns `Test Case | Trials | 👍 | ✅ | ❌ | ⏱️ | ⚠️`, with one row per distinct `TrialResult.test_case` sorted ASC by name; the table SHALL NOT contain an `Avg dur (s)` column. <!-- updated 2026-06-25 (quickfix-2026-06-25T06-58-37): canonical EARS, migrated from deprecated state-driven form -->
- `REQ-038` (AC-016): The Grid table's rows SHALL be the distinct `TrialResult.model` values sorted ASC, its columns SHALL be the distinct `TrialResult.test_case` values sorted ASC, and each cell SHALL contain the icon (per REQ-032) of every trial for that `(model, test_case)` pair in `trial_index` ASC order, separated by a single space, with no status text. <!-- updated 2026-06-25 (quickfix-2026-06-25T06-58-37): canonical EARS, migrated from deprecated state-driven form -->
- `REQ-039` (AC-016): IF a Grid cell has zero trials for its `(model, test_case)` pair, THEN the cell SHALL render as the literal `—` (U+2014 em dash). <!-- updated 2026-06-25 (quickfix-2026-06-25T06-58-37): canonical EARS, migrated from deprecated conditional form -->
- `REQ-040` (AC-017): WHEN at least one trial has status `FAIL`, `TIMEOUT`, or `ERROR`, the Failing / Timeout Trials table SHALL contain exactly the columns `Model | Test Case | Trial | Status | Duration (s)`, with one row per such trial sorted by `(model, test_case, trial_index)` ASC, and `Duration (s)` rendered to one decimal place. <!-- updated 2026-06-25 (quickfix-2026-06-25T06-58-37): canonical EARS, migrated from deprecated state-driven form to WHEN -->
- `REQ-041` (AC-017): IF no trial has status `FAIL`, `TIMEOUT`, or `ERROR`, THEN the reporter SHALL still emit the `## Failing / Timeout Trials` header followed by the literal line `No failing or timeout trials.` (with no table). <!-- updated 2026-06-25 (quickfix-2026-06-25T06-58-37): canonical EARS, migrated from deprecated negation form to IF…THEN -->
- `REQ-042` (AC-013): The reporter SHALL render the aggregate sections using pure Markdown only (no embedded HTML), consistent with REQ-027.
- `REQ-043`: Repeated calls to `generate_markdown_report` on the same `Experiment` instance SHALL produce byte-identical output across the **entire file** (not only the aggregate region); to make this hold the `**Generated**` timestamp in the report header SHALL be derived from `experiment.completed_at or experiment.started_at`, not from wall-clock time. <!-- added 2026-05-25 (sdlc-document drift-report-2026-05-25T01-14-05); updated 2026-06-25 (quickfix-2026-06-25T06-58-37): canonical EARS, migrated from deprecated ubiquitous form -->

## Non-Functional Requirements

| ID | Requirement | Target | Validated By |
|----|-------------|--------|--------------|
| NFR-002 | Aggregate rendering must avoid super-linear blow-up in the number of trials: a single O(T) collection pass over `Experiment.results` plus per-section sorting whose total cost stays within O(T log T). | No quadratic blow-up on M × N × T inputs. <!-- relaxed 2026-05-25 (sdlc-document drift-report-2026-05-25T01-14-05): code uses sorted() on per-section buckets, adding a log T factor on top of the O(T) collection pass --> | code review + targeted unit test on a synthetic large experiment |
| NFR-003 | `results.json` byte-content for a given Experiment must be unchanged by this feature. | Pre-feature golden JSON matches post-feature output. | regression unit test (golden-file comparison) |
| NFR-004 | The aggregate sections must be byte-identical across repeated renders of the same Experiment. | Two successive `generate_markdown_report` calls produce identical strings for the aggregate region. | unit test (call twice, assert equality) |

## NFRs Validated Outside Code

None — every NFR for this feature is exercised by a corresponding test.

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

| Condition | Status | Body |
|-----------|--------|------|
| Empty `Experiment.results` | Aggregates render with zero rows (header-only tables); Overall Status shows `Total trials: 0`; Failing section uses the empty-state literal | None needed |
| `TrialResult.status` outside `_STATUS_ICONS` (defensive only — enum-protected) | Cell renders bare status text without icon prefix, mirroring `_status_cell` | None needed; surfaces in review if the enum widens |
| Filesystem write failure during atomic rename | Propagates from `generate_markdown_report` as today | Unchanged from experiment-runner design |

## Correctness

*Only the properties that apply to this render-only feature. Round-Trip and Atomicity are not applicable — the aggregate sections persist nothing new; file-level atomic write is already provided by `generate_markdown_report` and the aggregate string is concatenated into the same single atomic write.*

- **Uniqueness:** The Grid is keyed by `(model, test_case)` pairs derived from `TrialResult` rows. By Model rows are keyed by `model`; By Test Case rows are keyed by `test_case`. Each key appears at most once per table — enforced by populating `dict[str, _Bucket]` accumulators on a single pass and rendering in sorted key order.
- **Validation:** Inputs to the aggregate functions are typed `Experiment` / `list[TrialResult]` instances — Pydantic models already validated on construction (RULE-003). No extra runtime validation is required. The reporter defensively handles an experiment with zero trials (every aggregate table renders zero rows; Overall Status emits `**Total trials**: 0`; Grid renders header row only; Failing / Timeout follows the empty-state path per REQ-041) and a status value not present in the canonical icon map (falls back to bare status text, matching `_status_cell` at `reporter.py:83`).
- **Idempotency:** Calling `generate_markdown_report` N times on the same `Experiment` produces N byte-identical files. The aggregate computation reads only the input list and a single `_STATUS_ICONS` constant; there is no hidden state, no clock read (the report's `generated_at` uses `experiment.completed_at or experiment.started_at`, already deterministic per `reporter.py:191`).

## Entities

See `.sdlc/requirements/entity-dictionary.md`. Fields this feature reads:

| Entity | Fields Used | Notes |
|--------|-------------|-------|
| Experiment | `results` | The list of trials this feature aggregates over |
| TrialResult | `model`, `test_case`, `trial_index`, `status`, `duration` | All fields are required and always populated per the entity dictionary's validation rules; `duration` is non-null even for TIMEOUT/ERROR |
| Report | `markdown_path` | Description mentions the aggregate sections; no field-shape change |

### Entity Modifications

None. The clarifying edits to `Report.markdown_path` and the validation rule on `TrialResult.duration` were already mirrored in `.sdlc/requirements/entity-dictionary.md` during the prior `/sdlc-requirements` run.

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

---
*Merged from `requirements.md` + `design.md` into the single-file spec format on 2026-06-04. Originally documented from code at 2026-05-25T01-14-05. Scope: report-aggregate. Source commit: 5eaf52d.*
