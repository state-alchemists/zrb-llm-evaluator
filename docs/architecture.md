# Architecture: zrb-llm-evaluator

## System Context (C4 Level 1)

```
┌─────────────────────────────────────┐
│         zrb-llm-evaluator           │
│  (experiment orchestrator + report) │
└──────┬────────────────────────┬─────┘
       │ subprocess             │ output
       ▼                        ▼
┌──────────────┐        ┌──────────────┐
│  zrb chat    │        │  Filesystem  │
│  (system     │        │  (history,   │
│   under test)│        │   results,   │
└──────────────┘        │   report)    │
                        └──────────────┘
```

The evaluator orchestrates multiple `zrb chat` subprocess invocations in parallel. Each invocation is a trial (one model × one test case × one attempt). The only external system is the filesystem — no database, no API server, no web UI.

## Container Diagram (C4 Level 2)

| Container | Technology | Responsibility |
|-----------|-----------|----------------|
| Experiment CLI | Typer (Python) | Entry point: `zrb-llm-evaluator run`, resume, list |
| Async Runner | asyncio (Python) | Orchestrates N concurrent subprocesses with Semaphore + wait_for |
| Test Case Loader | Python importlib | Discovers and validates user-defined test case modules |
| Report Generator | Python + Jinja2 | Produces `report.md` and `results.json` from accumulated `TrialResult`s |
| zrb chat | subprocess | The system-under-test; invoked with `--session`, `--interactive false` |

## Component Diagram (C4 Level 3)

### Runner
| Component | Responsibility | Dependencies |
|-----------|---------------|-------------|
| `ExperimentConfig` | Pydantic model for CLI-parsed config | Pydantic |
| `TrialRunner` | Runs one trial: set env, invoke subprocess, parse cost, validate | asyncio.subprocess |
| `WorkSteward` | Maintains `asyncio.Semaphore`, schedules `TrialRunner` tasks | asyncio |
| `ResumeManager` | Loads `results.json`, filters completed cells | json |

### Test Case
| Component | Responsibility | Dependencies |
|-----------|---------------|-------------|
| `TestCase` | Pydantic model representing one test case (instruction, workdir, validator) | Pydantic |
| `ValidatorProtocol` | typing.Protocol defining the validator interface | — |
| `ValidationResult` | Pydantic model with status, score, details | Pydantic |

### Models
| Component | Responsibility | Dependencies |
|-----------|---------------|-------------|
| `TrialResult` | Pydantic model for one trial's outcome | Pydantic |
| `Report` | Pydantic model for the generated report | Pydantic |

### Report
| Component | Responsibility | Dependencies |
|-----------|---------------|-------------|
| `MarkdownReporter` | Generates Markdown summary + per-cell detail tables | — |
| `JSONReporter` | Serializes all results to structured JSON | json |

## Key Decisions
| ADR | Title | Status |
|-----|-------|--------|
| ADR-1 | CLI Framework — Typer | Accepted |
| ADR-2 | Async Runner with asyncio | Accepted |
| ADR-3 | Leverage zrb's Built-in History for History Capture | Accepted |
| ADR-4 | Result Models with Pydantic v2 | Accepted |
| ADR-5 | Protocol-Based Validator Contract | Accepted |
| ADR-6 | Filesystem-Based Experiment State with JSON Resume | Accepted |
| ADR-7 | Trial Subprocess Isolation via Nested Workdir | Accepted |

## Data Flow

```
CLI args → ExperimentConfig → WorkSteward (async queue)
                                  │
                    ┌─────────────┴─────────────┐
                    │  (parallelism=N)           │
                    ▼                            ▼
              TrialRunner 1                 TrialRunner N
                    │                            │
         ┌──────────┼──────────┐       ┌─────────┼──────────┐
         ▼          ▼          ▼       ▼         ▼          ▼
    Set env     Invoke     Parse     Set env  Invoke     Parse
    ZRB_LLM     zrb chat   cost     ZRB_LLM  zrb chat   cost
    _HISTORY    --session  from     _HISTORY --session  from
    _DIR        (async)    stdout   _DIR     (async)    stdout
         │          │          │         │        │         │
         └──────────┴──────────┘         └────────┴─────────┘
                    │                            │
                    ▼                            ▼
             Validator.run()               Validator.run()
                    │                            │
                    ▼                            ▼
             Append TrialResult            Append TrialResult
             to results.json               to results.json
                    │                            │
                    └────────────┬───────────────┘
                                 ▼
                         ReportGenerator
                                 │
                        ┌────────┴────────┐
                        ▼                 ▼
                   report.md        results.json
```

## Deployment

| Environment | Infrastructure | Strategy |
|-------------|---------------|----------|
| Local dev | macOS / Linux | Manual `poetry install && zrb-llm-evaluator run` |
| CI (GitHub Actions) | ubuntu-latest | `poetry install && poetry run pytest` |
