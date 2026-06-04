# zrb-llm-evaluator — Technology Overview

## Stack
| Layer | Technology | Version | Rationale |
|-------|-----------|---------|-----------|
| Language | Python | >=3.11 | zrb ecosystem is Python; existing llm-challenges runner is Python |
| Package manager | Poetry | — | Standard for zrb ecosystem |
| Result models | Pydantic | v2 | Typed, serializable validation results |
| LLM invocation | zrb chat CLI (subprocess) | — | The system-under-test; no direct API calls |
| Report output | Markdown + JSON | — | Human-readable + machine-parseable; same pattern as existing runner |

## Architecture Principles
1. **History-first capture** — Full LLM conversation history is persisted to disk before any validation runs. A timeout during the LLM call still preserves everything up to that point.
2. **Pluggable test cases** — Test cases are user-defined Python modules with a standard interface (instruction, workdir, validator). The framework provides no built-in cases.
3. **Structured results** — Every validation result is a typed dataclass/Pydantic model. No ad-hoc dicts or string parsing for downstream tooling.
4. **CLI-first** — The primary interface is a command-line tool (extensible for white-labeled zrb forks). No web UI, no daemon.

## Constraints
- Must invoke zrb via subprocess (`zrb chat ...`), not the zrb Python API
- Must run on macOS and Linux

## Dependencies
| Dependency | Purpose | License |
|------------|---------|---------|
| pydantic | Typed result models | MIT |
| typer/click | CLI framework | MIT |
| rich | Report rendering (optional) | MIT |
