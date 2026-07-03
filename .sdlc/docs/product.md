# zrb-llm-evaluator — Product Overview

## Problem Statement
zrb's existing llm-challenges runner evaluates each model × challenge exactly once, capturing stdout output that vanishes on timeout. There is no structured way to run multiple trials, define per-case validators with typed results, or compare results across prompt/harness versions. Every improvement becomes anecdotal rather than measurable.

## Target Users
| User Role | Primary Goal |
|-----------|-------------|
| zrb maintainer | Measure whether a prompt/tool-definition change improves LLM task-solving across multiple models |
| White-label zrb CLI builder | Validate that their customized zrb fork still passes the benchmark suite |
| Framework evaluator | Compare model performance across providers (OpenAI, Google, DeepSeek, Ollama) and across agent CLIs (zrb, Claude Code, opencode) on coding tasks |

## Success Criteria
- **Functional**: One command runs N models × M test cases × T trials; full LLM history is captured to disk; per-case validators produce structured PASS/FAIL/EXCELLENT results; a regression-aware report is generated.
- **Non-Functional**: Timeout-safe (history preserved if LLM call hangs). Parallel execution configurable. CLI is extensible for white-labeled zrb forks. The CLI-under-test itself is pluggable via `CliAdapter` templates (zrb, Claude Code, opencode, or custom). Users define their own test cases and validators. Validation results use dataclass/Pydantic models for structural correctness.
- **Business**: Every prompt change, harness improvement, or tool-definition update becomes objectively measurable — no more "feels better" decisions.

## Scope
### In Scope
- Running N models × M test cases × T trials in one command
- Per-test-case Python validators with structured results (dataclass/Pydantic)
- Full LLM history capture to disk (survives timeout)
- Configurable parallelism and timeout
- Report generation (Markdown summary + structured JSON)
- Custom CLI definition for white-labeled zrb forks
- Resume interrupted runs (skip already-completed cells)
- Pluggable CLI templates for evaluating agent CLIs beyond zrb (e.g., Claude Code, opencode) via a common `CliAdapter` interface; custom adapters can be registered for other CLIs via a dotted Python import path

### Out of Scope
- Built-in support for arbitrary/unknown CLIs with no adapter — anything not shipped as a built-in template requires the user to implement the `CliAdapter` protocol themselves
- A built-in library of test cases (users define their own)
- Live model cost tracking or budgeting

## Key Stakeholders
| Stakeholder | Interest |
|-------------|----------|
| Go Frendi — zrb maintainer | Framework quality; making prompt/harness changes scientifically measurable |
| White-label zrb adopters | Ensuring their fork passes regression benchmarks |
