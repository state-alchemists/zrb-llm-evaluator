# Problem Brief: zrb-llm-evaluator

## Problem Statement
zrb's existing llm-challenges runner evaluates each model × challenge exactly once, capturing stdout that vanishes on timeout. There is no structured way to define per-case validators with typed results, run multiple trials, or compare results across prompt/harness versions. Every improvement becomes anecdotal rather than measurable.

## User Stories
- `US-001`: As a **zrb maintainer**, I want to **run an experiment across multiple models, test cases, and trials** so that **I can measure whether a prompt or harness change improves, regresses, or leaves performance unchanged**.
- `US-002`: As a **zrb maintainer**, I want **each test case to define its own typed validator** so that **validation logic is precise, structured, and reusable across experiments**.
- `US-003`: As a **zrb maintainer**, I want **full LLM conversation history captured to disk before validation runs** so that **I can debug failures even if the LLM call times out**.
- `US-004`: As a **white-label zrb CLI builder**, I want **to define custom CLI entry points for my fork** so that **I can run the same benchmark suite with a different binary name**.
- `US-005`: As a **framework evaluator**, I want **a structured report (Markdown + JSON)** so that **I can compare results across models, test cases, and trials in both human-readable and machine-parseable formats**.
- `US-006`: As a **zrb maintainer**, I want **configurable parallelism and per-experiment timeout** so that **I can balance execution speed against API rate limits and model latency**.
- `US-007`: As a **zrb maintainer**, I want **to resume an interrupted experiment** so that **I don't re-run already-completed model × test case cells on restart**.
- `US-008`: As a **zrb maintainer**, I want **each trial's LLM subprocess to run in an isolated working directory that contains only the staged test-case files** so that **the LLM cannot inspect evaluation artifacts (its own stdout log, conversation history, validator source, prior trial results) that would contaminate the experiment**.
- `US-009`: As a **framework evaluator**, I want **the Markdown report sorted by model → test case → trial with best-metric highlights and status icons** so that **I can scan and compare results across runs at a glance**.
- `US-010`: As a **framework evaluator**, I want **the Markdown report to start with aggregate tables (overall status counts, per-model and per-test-case breakdowns, a model × test-case grid, and a failures-only focus table)** so that **I can scan high-level health at a glance before drilling into individual trials, while still seeing the same color-blind-safe status icons everywhere**.
- `US-011`: As a **framework evaluator**, I want **to select the CLI-under-test (zrb, Claude Code, opencode) with a `--cli-template` flag** so that **I can benchmark agent CLIs other than zrb using the same test cases, validators, and report format**.
- `US-012`: As a **framework evaluator**, I want **each CLI template to handle its own subprocess invocation, history capture, and usage/token parsing** so that **`TrialResult`s stay structurally comparable across models and CLIs regardless of which one produced them**.
- `US-013`: As a **white-label CLI builder / advanced user**, I want **to register a custom CLI adapter via a dotted Python import path** so that **I can benchmark an agent CLI the framework doesn't ship a template for, without modifying the evaluator's source**.

## Acceptance Criteria
- [ ] `AC-001` (US-001): User runs `zrb-llm-evaluator run --models m1,m2 --test-cases ./cases/ --trials 3` and the tool executes 3 trials of every model × test case combination.
- [ ] `AC-002` (US-002): A user-defined validator implementing the framework's Protocol returns a Pydantic result model with status (EXCELLENT/PASS/FAIL), score, and details — the framework accepts and reports this result correctly.
- [ ] `AC-003` (US-003): When a trial times out, the partial LLM log is present on disk and the validation runs against whatever output was captured.
- [ ] `AC-004` (US-004): A white-label fork can register an alternative CLI name (e.g., `my-cli-evaluator`) and the same experiment config file works without modification.
- [ ] `AC-005` (US-005): Running an experiment produces `report.md` (Markdown summary table + detailed per-cell results) and `results.json` (structured JSON, resume-compatible).
- [ ] `AC-006` (US-006): Specifying `--parallelism 8 --timeout 120` runs up to 8 concurrent subprocesses and kills any trial exceeding 120s.
- [ ] `AC-007` (US-007): If the experiment is interrupted mid-run and restarted with the same output directory, already-completed cells are skipped and only pending cells execute.
- [ ] `AC-008` (US-008): When a trial runs, the subprocess `cwd` is a dedicated per-trial workdir containing only the staged test-case files; the trial's `stdout.log`, `history/` directory, `validator.py`, and any other evaluation files live in a sibling/parent location and are not present in or reachable as relative siblings of the subprocess `cwd`.
- [ ] `AC-009` (US-008): A test case with no dedicated `workdir/` to stage still runs with `cwd` pointed at a freshly-created empty directory — never at the cell directory containing the trial's logs and history.
- [ ] `AC-010` (US-009): Trial rows in `report.md` are ordered by `model` ascending, then `test_case` ascending, then `trial_index` ascending.
- [ ] `AC-011` (US-009): Within each test case (across all models and trials), for trials whose status is `PASS` or `EXCELLENT` only, the cells showing the shortest `duration`, highest `score`, lowest `total_tokens`, and lowest `tool_call_count` are rendered in bold. When multiple trials tie for a best value, every tied cell is bolded. Trials with status `FAIL`, `TIMEOUT`, or `ERROR` are excluded from the best-metric computation and are never bolded.
- [ ] `AC-012` (US-009): Status is rendered in the Markdown report with icons: `EXCELLENT` → 👍, `PASS` → ✅, `FAIL` → ❌, `TIMEOUT` → ⏱️, `ERROR` → ⚠️.
- [ ] `AC-013` (US-010): `report.md` opens (after the header lines) with the new aggregate sections in this order: **Overall Status**, **By Model**, **By Test Case**, **Grid**, **Failing / Timeout Trials**. These sections appear *before* the existing `## Summary` table; the `## Summary` and `## Per-Trial Details` sections remain unchanged in content and order.
- [ ] `AC-014` (US-010): The **Overall Status** section is a table with columns `Status | Count | %`, one row per status that has at least one trial, in fixed order `EXCELLENT, PASS, FAIL, TIMEOUT, ERROR`. The `Status` cell uses the same icon-prefixed rendering as the existing report (e.g., `👍 EXCELLENT`). `%` is the trial count divided by total trials, rendered to one decimal place. The total trials count appears as a bold line immediately above the table.
- [ ] `AC-015` (US-010): The **By Model** section is a table `Model | Trials | 👍 | ✅ | ❌ | ⏱️ | ⚠️ | Avg dur (s)`, one row per distinct model in the experiment, sorted by model name ascending. `Avg dur (s)` is the arithmetic mean of `duration` over all of that model's trials (including FAIL/TIMEOUT/ERROR), to one decimal place. The **By Test Case** section uses the same columns and rules except keyed by test case (no `Avg dur (s)` column) and sorted by test case name ascending.
- [ ] `AC-016` (US-010): The **Grid** section is a table whose rows are models (sorted ascending), whose columns are test cases (sorted ascending), and whose cells contain the status icons (no status text, no extra whitespace separators beyond a single space) of every trial for that model × test case pair in `trial_index` ascending order. A cell with zero trials renders as `—`.
- [ ] `AC-017` (US-010): The **Failing / Timeout Trials** section is a table `Model | Test Case | Trial | Status | Duration (s)`, listing one row per trial whose status is `FAIL`, `TIMEOUT`, or `ERROR`. Rows are sorted by `(model, test_case, trial_index)` ascending. `Duration (s)` is rendered to one decimal place. If no trial has a failing status, the section header is still emitted followed by the literal line `No failing or timeout trials.` (no table).
- [ ] `AC-018` (US-011): Running `zrb-llm-evaluator run --cli-template claude-code ...` or `--cli-template opencode ...` invokes that CLI's non-interactive mode instead of `zrb chat`, using the same `--models/--test-cases/--trials` flags and the same test case directories/validators as the zrb path.
- [ ] `AC-019` (US-011): `--cli-template` defaults to `zrb` when omitted; existing zrb-only configs and commands continue to work with no behavior change.
- [ ] `AC-020` (US-012): Regardless of `--cli-template`, `TrialResult`'s status, duration, token fields, and `tool_calls`/`tool_call_count` are populated using that template's own parsing logic, defaulting to their existing "unavailable" values (0 for token counts, empty list for tool calls) when the adapter cannot determine them.
- [ ] `AC-021` (US-012): For every built-in template, if a trial times out, the partial conversation history captured by that template is present on disk, preserving the same timeout-safety guarantee as `AC-003`.
- [ ] `AC-022` (US-013): A user can pass a dotted Python import path (e.g. `--cli-template mypkg.MyAdapter`) as `--cli-template`; the runner imports and uses that class exactly like a built-in template, and rejects (exits non-zero, before any trial) a `cli_template` value that is neither a built-in name nor an importable class implementing the adapter contract.

## Dependencies
| Dependency | Type | Status |
|------------|------|--------|
| zrb (any version with `zrb chat --interactive false`) | Runtime | Available |
| Python >= 3.11 | Runtime | Available |
| Poetry | Build | Available |

## Open Questions
None.
