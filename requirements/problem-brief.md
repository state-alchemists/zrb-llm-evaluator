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

## Acceptance Criteria
- [ ] `AC-001` (US-001): User runs `zrb-llm-evaluator run --models m1,m2 --test-cases ./cases/ --trials 3` and the tool executes 3 trials of every model × test case combination.
- [ ] `AC-002` (US-002): A user-defined validator implementing the framework's Protocol returns a Pydantic result model with status (EXCELLENT/PASS/FAIL), score, and details — the framework accepts and reports this result correctly.
- [ ] `AC-003` (US-003): When a trial times out, the partial LLM log is present on disk and the validation runs against whatever output was captured.
- [ ] `AC-004` (US-004): A white-label fork can register an alternative CLI name (e.g., `my-cli-evaluator`) and the same experiment config file works without modification.
- [ ] `AC-005` (US-005): Running an experiment produces `report.md` (Markdown summary table + detailed per-cell results) and `results.json` (structured JSON, resume-compatible).
- [ ] `AC-006` (US-006): Specifying `--parallelism 8 --timeout 120` runs up to 8 concurrent subprocesses and kills any trial exceeding 120s.
- [ ] `AC-007` (US-007): If the experiment is interrupted mid-run and restarted with the same output directory, already-completed cells are skipped and only pending cells execute.

## Dependencies
| Dependency | Type | Status |
|------------|------|--------|
| zrb (any version with `zrb chat --interactive false`) | Runtime | Available |
| Python >= 3.11 | Runtime | Available |
| Poetry | Build | Available |

## Open Questions
None.
