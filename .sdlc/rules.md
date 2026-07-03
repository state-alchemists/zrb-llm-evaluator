# Project Rules — Constitution

> Immutable invariants. Every SDLC skill reads this file and refuses to violate it.
> Override process: see RULE-999 below. Do not edit rule statements without an Override Record.

## How to Use This File
- Every spec, design, test plan, and implementation must respect every rule below.
- `/sdlc-review` will report a `FAIL` for any code that violates a rule.
- To change a rule, follow the Override Process (RULE-999) and append (do not edit) an entry to the Override Log.

## Rules

### RULE-001 — OOP-first Design
| Field | Value |
|-------|-------|
| Category | Required Patterns |
| Statement | Core abstractions MUST be defined as classes (dataclasses, Pydantic models, or ABCs/protocols). Functions are acceptable for helpers, utilities, and scripts that glue classes together. |
| Rationale | Maintainability and navigability for a growing codebase |
| Enforcement | Review rejection of large procedural blocks that could be classes |
| Added | 2026-05-18 |

### RULE-002 — Type Annotations on All Public APIs
| Field | Value |
|-------|-------|
| Category | Required Patterns |
| Statement | Every public function, method, and class must have complete type annotations (arguments and return). Private/internal helpers should also be annotated where feasible. |
| Rationale | mypy strict is a CI gate; type annotations make the code self-documenting and catch errors early. |
| Enforcement | mypy strict in CI |
| Added | 2026-05-18 |

### RULE-003 — Pydantic for Result Models
| Field | Value |
|-------|-------|
| Category | Required Patterns |
| Statement | All structured results (validation results, experiment configs, report entries) MUST use Pydantic v2 models — not plain dicts, tuples, or unstructured dataclasses. |
| Rationale | Ensures downstream tooling receives typed, validated, serializable payloads. |
| Enforcement | Review and type-checker |
| Added | 2026-05-18 |

### RULE-004 — Protocol/ABC for Pluggable Validators
| Field | Value |
|-------|-------|
| Category | Required Patterns |
| Statement | The test-case validator contract MUST be defined via an ABC or Protocol. User-defined validators implement this contract. |
| Rationale | Ensures all validators provide the expected interface regardless of who writes them. |
| Enforcement | Review; the framework must reject a validator that doesn't implement the protocol |
| Added | 2026-05-18 |

### RULE-005 — Invoke the Target CLI via Subprocess
| Field | Value |
|-------|-------|
| Category | Required Patterns |
| Statement | The experiment runner MUST invoke the configured CLI under test (zrb, Claude Code, opencode, or a custom `CliAdapter` template) as a subprocess, via that CLI's `CliAdapter`. It MUST NOT import or call the target CLI's internal Python APIs directly. |
| Rationale | Tests the actual CLI the user runs, regardless of which agent framework it wraps; works with white-labeled zrb forks and alternative agent CLIs that may have entirely different Python internals (or none at all). |
| Enforcement | Review; no import of a target CLI's internals in the runner module or in any `CliAdapter` implementation |
| Added | 2026-05-18 |
| Amended | 2026-07-03 — generalized from zrb-only to any `CliAdapter`-backed CLI (see Override Log) |

### RULE-006 — Poetry for Packaging
| Field | Value |
|-------|-------|
| Category | Required Patterns |
| Statement | Dependencies, build, and distribution MUST use Poetry. No plain pip, no setup.py. |
| Rationale | Matches zrb ecosystem conventions |
| Enforcement | CI checks for `pyproject.toml` with `[tool.poetry]` section |
| Added | 2026-05-18 |

### RULE-007 — Unit Coverage >= 80%
| Field | Value |
|-------|-------|
| Category | Quality Gates |
| Statement | Overall unit test coverage MUST be >= 80%. Public API surfaces must aim for 100%. |
| Rationale | The test-strategy document defines this as a quality goal |
| Enforcement | pytest-cov in CI |
| Added | 2026-05-18 |

### RULE-008 — mypy Strict Mode
| Field | Value |
|-------|-------|
| Category | Quality Gates |
| Statement | All source code MUST pass mypy in strict mode. No `# type: ignore` without an inline comment explaining why. |
| Rationale | mypy strict is the only way to guarantee type safety across the whole codebase |
| Enforcement | mypy --strict in CI |
| Added | 2026-05-18 |

### RULE-009 — Clean ruff Lint
| Field | Value |
|-------|-------|
| Category | Quality Gates |
| Statement | The codebase MUST pass `ruff check` with zero errors. No selective disabling of rules per-file without documented reason. |
| Rationale | Consistent style and early bug detection |
| Enforcement | ruff check in CI |
| Added | 2026-05-18 |

### RULE-010 — No Dead Code
| Field | Value |
|-------|-------|
| Category | Quality Gates |
| Statement | Unused imports, unreachable branches, and orphaned functions/classes MUST be removed, not commented out. |
| Rationale | Dead code is a maintenance liability and confuses both humans and tooling. |
| Enforcement | `ruff check` (F401, F841) + review |
| Added | 2026-05-18 |

### RULE-011 — No `print()` in Library Code
| Field | Value |
|-------|-------|
| Category | Quality Gates |
| Statement | Library/package code MUST NOT use `print()` for output. CLI entry points and debug utilities are exempt. Use structured logging or rich console where output is needed. |
| Rationale | `print()` output pollutes subprocess capture and is not machine-parseable |
| Enforcement | ruff flake8-print (T201) in CI |
| Added | 2026-05-18 |

### RULE-012 — Async for Concurrent Runs
| Field | Value |
|-------|-------|
| Category | Required Patterns |
| Statement | Concurrent experiment runs MUST use `asyncio` (not `threading` or `multiprocessing`). The CLI entry point may use a sync wrapper, but the core concurrent runner must be async. |
| Rationale | Async scales better for I/O-bound LLM subprocess invocations and is the modern Python standard. |
| Enforcement | Review |
| Added | 2026-05-18 |

## Override Process — RULE-999
| Field | Value |
|-------|-------|
| Category | Process |
| Statement | A rule may only be overridden for a single change, recorded as an entry in the Override Log below, with the approver named. The rule statement itself is never edited. The approver is always the project lead (Go Frendi). |
| Rationale | Prevents silent erosion of invariants. |
| Enforcement | Reviewers reject PRs that violate a rule without a matching Override Log entry. |

## Override Log

| Date | Rule | Scope (PR / commit) | Approver | Reason |
|------|------|---------------------|----------|--------|
| 2026-07-03 | RULE-005 | `cli-templates` feature (experiment-runner spec REQ-035–042) | Go Frendi | Generalize the runner from a zrb-only subprocess call to a pluggable `CliAdapter`, so the evaluator can also benchmark Claude Code, opencode, and custom agent CLIs. |
