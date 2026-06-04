# ADR-9: Aggregate Sections in the Markdown Report

## Status
Accepted

## Context
US-010 (problem-brief AC-013 through AC-017) requires `report.md` to open with five aggregate sections — Overall Status, By Model, By Test Case, Grid (model × test case), and Failing / Timeout Trials — before the existing per-trial Summary and Details. The reporter today produces only per-trial output; reviewers triaging a 100+ trial experiment cannot quickly answer "how many failed?", "which model is weakest?", or "is one test case the universal blocker?" without scanning every row.

ADR-8 already governs sort order, best-metric bolding, status icons, and the no-HTML rule for the existing sections. We need a complementary decision for the new aggregates that keeps the same conventions, locks down formatting precision, and stays purely computed-on-render (no new persisted state).

## Decision
The `MarkdownReporter` is extended with an **aggregates pre-section** that is emitted between the header lines and the existing `## Summary` table:

1. **Sections and order (fixed)**: `## Overall Status` → `## By Model` → `## By Test Case` → `## Grid` → `## Failing / Timeout Trials`. Existing `## Summary` and `## Per-Trial Details` sections are unchanged.

2. **Pure-render, no persistence**: aggregates are computed from `Experiment.results` at render time. `results.json` is unchanged — no `aggregates` field is added.

3. **Reuse of ADR-8 conventions**:
   - The same `_STATUS_ICONS` mapping (👍/✅/❌/⏱️/⚠️) drives every status cell in every new table.
   - Pure Markdown — no embedded HTML.
   - Deterministic ordering: models sorted ASC by name, test cases sorted ASC by name, trials within a grid cell sorted by `trial_index` ASC.

4. **Per-section rules**:
   - **Overall Status**: `Status | Count | %`. One row per status with ≥1 trial, in the canonical order `EXCELLENT, PASS, FAIL, TIMEOUT, ERROR`. `%` to one decimal. A bold "**Total trials**: N" line precedes the table.
   - **By Model**: `Model | Trials | 👍 | ✅ | ❌ | ⏱️ | ⚠️ | Avg dur (s)`. `Avg dur (s)` is the arithmetic mean of `duration` over *all* of that model's trials (including FAIL/TIMEOUT/ERROR — safe per the validation rule that `duration` is always populated), to one decimal.
   - **By Test Case**: same columns minus `Avg dur (s)` (case-level duration averages mix incomparable models).
   - **Grid**: rows = models, columns = test cases. Each cell is the space-separated icon sequence (no status text) for that pair's trials in `trial_index` ASC order. Empty cells render as `—`.
   - **Failing / Timeout Trials**: `Model | Test Case | Trial | Status | Duration (s)`. One row per trial with status `FAIL`/`TIMEOUT`/`ERROR`, sorted `(model, test_case, trial_index)` ASC. When no such trials exist, the section header is still emitted followed by the literal line `No failing or timeout trials.` (no table).

5. **Determinism**: the aggregates section must be byte-identical for any two renders of the same `Experiment` (mirrors the existing reporter's deterministic `generated_at` derivation).

## Consequences
### Positive
- Reviewers get a triage layer at the top of every report without diff churn in the existing sections.
- No JSON schema change → existing downstream consumers of `results.json` are unaffected.
- Pure-render means resume runs and re-renders of the same experiment produce stable, diffable output.

### Negative
- The Markdown report grows by ~10–20 lines plus an `M × N` grid per experiment; very large experiments (many models, many cases) make the grid wide.
- Adds rendering logic without a corresponding JSON counterpart — two downstream consumers asking the same aggregate question (a CI dashboard vs. the report) would each have to compute it.
- The "no avg duration in By Test Case" asymmetry is a small surprise; documented here to forestall a future PR that "fixes" it.

## Implements Rules
- RULE-003 — Aggregates are computed from typed `TrialResult` Pydantic fields, not ad-hoc dicts.
- RULE-011 — All aggregate rendering goes through the same library code path as the existing reporter; no `print()` introduced.

## Verification
- Unit tests on `MarkdownReporter` extended to cover:
  - Presence and order of the five new section headers, placed before `## Summary`.
  - Overall Status row order (canonical) and `%` precision.
  - By Model / By Test Case column shapes, sort order, and `Avg dur (s)` including FAIL/TIMEOUT/ERROR trials.
  - Grid cell rendering for: multiple trials, zero trials (`—`), mixed statuses, sort order.
  - Failing / Timeout Trials row filter and the empty-state literal line.
  - `results.json` is byte-identical before/after the aggregates change for the same experiment.

## References
- .sdlc/requirements/problem-brief.md — US-010, AC-013, AC-014, AC-015, AC-016, AC-017
- .sdlc/docs/adr/ADR-8.md — companion decision for the existing report sections
- .sdlc/docs/architecture.md — `MarkdownReporter` component
