# Feature Requirements: report-aggregate

## EARS Requirements

### Invariants (ALWAYS SHALL)
- `REQ-030` (from AC-013): ALWAYS SHALL `report.md` contain five aggregate sections — `## Overall Status`, `## By Model`, `## By Test Case`, `## Grid`, `## Failing / Timeout Trials` — emitted in that order, between the header lines and the existing `## Summary` table.
- `REQ-031` (from AC-013): ALWAYS SHALL the existing `## Summary` and `## Per-Trial Details` sections of `report.md` retain the content and ordering defined by REQ-025 through REQ-029; the aggregate sections are additive and never modify per-trial rows.
- `REQ-032` (from AC-013, AC-014, AC-015, AC-016, AC-017): ALWAYS SHALL every status cell in every aggregate section use the icon mapping already mandated by REQ-029 (`EXCELLENT` → 👍, `PASS` → ✅, `FAIL` → ❌, `TIMEOUT` → ⏱️, `ERROR` → ⚠️).
- `REQ-033` (from AC-013): ALWAYS SHALL the aggregate sections be computed from `Experiment.results` at render time only; `results.json` shall not gain an `aggregates` field or any other byte-level change attributable to this feature.
- `REQ-034` (from AC-013): ALWAYS SHALL two renders of the same `Experiment` instance produce byte-identical aggregate sections (deterministic ordering, formatting, and content).

### State-Driven (WHERE/THEN SHALL)
- `REQ-035` (from AC-014): WHERE the Overall Status table is rendered THEN SHALL it contain exactly the columns `Status | Count | %`, with one row per status that has at least one trial, in the canonical order `EXCELLENT, PASS, FAIL, TIMEOUT, ERROR`; the `%` value SHALL be the row's count divided by total trials, rendered to one decimal place; and a bold line `**Total trials**: N` SHALL appear immediately above the table.
- `REQ-036` (from AC-015): WHERE the By Model table is rendered THEN SHALL it contain exactly the columns `Model | Trials | 👍 | ✅ | ❌ | ⏱️ | ⚠️ | Avg dur (s)`, with one row per distinct `TrialResult.model` in the experiment sorted ASC by model name; the `Avg dur (s)` cell SHALL be the arithmetic mean of `duration` over every trial of that model (including FAIL, TIMEOUT, and ERROR), rendered to one decimal place.
- `REQ-037` (from AC-015): WHERE the By Test Case table is rendered THEN SHALL it contain exactly the columns `Test Case | Trials | 👍 | ✅ | ❌ | ⏱️ | ⚠️`, with one row per distinct `TrialResult.test_case` sorted ASC by name; the table SHALL NOT contain an `Avg dur (s)` column.
- `REQ-038` (from AC-016): WHERE the Grid table is rendered THEN SHALL its rows be the distinct `TrialResult.model` values sorted ASC, its columns be the distinct `TrialResult.test_case` values sorted ASC, and each cell SHALL contain the icon (per REQ-032) of every trial for that `(model, test_case)` pair in `trial_index` ASC order, separated by a single space, with no status text.
- `REQ-039` (from AC-016): WHERE a Grid cell has zero trials for its `(model, test_case)` pair THEN SHALL the cell render as the literal `—` (U+2014 em dash).
- `REQ-040` (from AC-017): WHERE the Failing / Timeout Trials table is rendered AND at least one trial has status `FAIL`, `TIMEOUT`, or `ERROR` THEN SHALL the table contain exactly the columns `Model | Test Case | Trial | Status | Duration (s)`, with one row per such trial sorted by `(model, test_case, trial_index)` ASC, and `Duration (s)` rendered to one decimal place.

### Exception (UNLESS/THEN SHALL)
- `REQ-041` (from AC-017): UNLESS at least one trial has status `FAIL`, `TIMEOUT`, or `ERROR` THEN SHALL the `## Failing / Timeout Trials` header still be emitted, followed by the literal line `No failing or timeout trials.` (with no table).

### Mandatory (SHALL)
- `REQ-042` (from AC-013): The reporter SHALL render the aggregate sections using pure Markdown only (no embedded HTML), consistent with REQ-027.

## Non-Functional Requirements

| ID | Requirement | Target | Validated By |
|----|-------------|--------|--------------|
| NFR-002 | Aggregate rendering must be O(T) in the number of trials with a single pass per section. | Render time stays linear; no quadratic blow-up on M × N × T inputs. | code review + targeted unit test on a synthetic large experiment |
| NFR-003 | `results.json` byte-content for a given Experiment must be unchanged by this feature. | Pre-feature golden JSON matches post-feature output. | regression unit test (golden-file comparison) |
| NFR-004 | The aggregate sections must be byte-identical across repeated renders of the same Experiment. | Two successive `generate_markdown_report` calls produce identical strings for the aggregate region. | unit test (call twice, assert equality) |

## NFRs Validated Outside Code
None — every NFR for this feature is exercised by a corresponding test.
