# ADR-8: Markdown Report Rendering Conventions

## Status
Accepted

## Context
US-009 requires the Markdown report to be scannable across many model × test-case × trial cells. Without a stable convention for row ordering, "best result" highlighting, and at-a-glance status signaling, every run produces a differently-shaped artifact that's hard to diff or review.

## Decision
The `MarkdownReporter` renders `report.md` with these conventions:

1. **Sort order** — Trial rows are ordered by `model` ASC, then `test_case` ASC, then `trial_index` ASC.
2. **Best-metric bolding** — Per test case (across all models and all trials), only trials with status `PASS` or `EXCELLENT` participate. The cells rendering the minimum `duration`, maximum `score`, minimum `total_tokens`, and minimum `tool_call_count` are wrapped in Markdown `**...**`. Ties bold every tied cell. Trials with `FAIL`, `TIMEOUT`, or `ERROR` are excluded from this computation and are never bolded.
3. **Status icons** — Status is rendered with a leading Unicode emoji: `EXCELLENT` → 👍, `PASS` → ✅, `FAIL` → ❌, `TIMEOUT` → ⏱️, `ERROR` → ⚠️.
4. **Pure Markdown** — Output uses Markdown syntax only; no embedded HTML.

## Consequences
### Positive
- Pure-Markdown output renders correctly in GitHub, VSCode, and terminal viewers (glow, rich).
- Stable sort makes report diffs across experiment runs reviewable in git.
- Per-test-case bolding scope reflects the reality that test cases are not comparable to each other — each test case has its own "winners."

### Negative
- Emoji width and rendering vary by terminal; some monospace fonts misalign emoji columns.
- Per-test-case scope means a model that is globally fastest but never the per-test-case best gets no bold cells.
- Tie-bolding can produce many bold cells if trials are deterministic and frequently match.

## Implements Rules
- RULE-003 — The reporter consumes `TrialResult` Pydantic models; all sort keys, bolded metrics, and status icons are derived from typed Pydantic fields rather than ad-hoc dicts.

## Verification
- Unit tests on `MarkdownReporter` cover: sort order across mixed models/cases/trials, best-metric computation (including ties and FAIL/TIMEOUT/ERROR exclusion), and all five status-icon mappings.

## References
- requirements/problem-brief.md — US-009, AC-010, AC-011, AC-012
- docs/architecture.md — `MarkdownReporter` component
