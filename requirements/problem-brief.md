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

## Dependencies
| Dependency | Type | Status |
|------------|------|--------|
| zrb (any version with `zrb chat --interactive false`) | Runtime | Available |
| Python >= 3.11 | Runtime | Available |
| Poetry | Build | Available |

## Open Questions
None.
