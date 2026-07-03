# Entity Dictionary: zrb-llm-evaluator

## Entities

### Experiment
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, auto-generated | Unique experiment identifier |
| config | ExperimentConfig | Required | The configuration defining this experiment run |
| results | list[TrialResult] | — | All trial results produced by this experiment |
| started_at | datetime | Required | When the experiment began |
| completed_at | datetime | Nullable | When the experiment finished (or null if incomplete) |

### ExperimentConfig
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| models | list[str] | Required, min 1 | Model identifiers (e.g., "openai:gpt-4o") |
| test_case_dirs | list[str] | Required, min 1 | Paths to test case directories |
| trials | int | Required, >= 1 | Number of trials per model × test case |
| parallelism | int | >= 1, default 4 | Max concurrent subprocesses |
| timeout | int | >= 30, default 300 | Per-trial timeout in seconds |
| cli_name | str | default "zrb" | CLI binary name (enables white-label forks) |
| env_prefix | str | default "ZRB" | Env var prefix; used by the `zrb` `CliAdapter` to construct `{prefix}_LLM_HISTORY_DIR` and `{prefix}_LLM_JOURNAL_DIR` env var names. Ignored by adapters that don't use env-var-based history capture. |
| cli_template | str | default "zrb" | Selects the `CliAdapter` used to invoke and parse the CLI under test. One of the built-in names ("zrb", "claude-code", "opencode") or a dotted Python import path to a custom class implementing `CliAdapter`. |

### TestCase
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| name | str | Required, unique within experiment | Directory name of the test case |
| instruction | str | Required | The prompt/instruction sent to the LLM |
| workdir | Path | Required | Source path for files staged into the trial's working directory; may not exist on disk (treated as an empty source). |
| validator | Validator | Required | The typed validation logic for this test case |

### Validator
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| — | — | — | Defined as a Python ABC/Protocol with a single `validate(output_dir: Path, log_content: str) -> ValidationResult` method |

### CliAdapter
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| — | — | — | Defined as a Python Protocol abstracting how the runner invokes and interprets one CLI-under-test. Built-in implementations: `ZrbCliAdapter`, `ClaudeCodeCliAdapter`, `OpencodeCliAdapter`. Users may supply a custom implementation via a dotted import path on `ExperimentConfig.cli_template`. Methods: `build_argv(cli_name: str, model: str, instruction: str, session_name: str) -> list[str]` (full subprocess argv, program name first); `build_env(base_env: dict[str, str], history_dir: Path, journal_dir: Path, env_prefix: str) -> dict[str, str]` (env vars to overlay on the subprocess environment; an adapter may ignore any of `history_dir`/`journal_dir`/`env_prefix` if it manages history capture another way); `history_log_path(history_dir: Path, session_name: str) -> Path` (where this adapter writes/expects the conversation history file); `parse_usage(stdout: str) -> UsageSummary` (token/cost extraction from captured stdout); `extract_tool_calls(history_log_path: Path) -> tuple[list[str], int]` (tool-call names and count from the adapter's own history file format). |

### UsageSummary
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| total_tokens | int | default 0 | Total tokens reported for the trial |
| input_tokens | int | default 0 | Input tokens |
| output_tokens | int | default 0 | Output tokens |
| cache_read_tokens | int | default 0 | Cache read tokens |

### ValidationResult
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| status | enum | Required: EXCELLENT, PASS, FAIL | Overall outcome |
| score | float | Required, 0.0–1.0 | Normalized score |
| details | list[ValidationCheck] | Required | Per-check breakdown |

### ValidationCheck
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| name | str | Required | Check identifier (e.g., "has_type_hints") |
| passed | bool | Required | Whether this check passed |
| message | str | — | Human-readable explanation or failure reason |

### TrialResult
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, auto-generated | Unique trial result identifier |
| model | str | Required | The model used |
| test_case | str | Required | The test case name |
| trial_index | int | Required, >= 1 | Trial number within this model × test case |
| status | enum | Required: EXCELLENT, PASS, FAIL, TIMEOUT, ERROR | Final classification |
| duration | float | Required | Wall-clock duration in seconds |
| exit_code | int | Required | zrb subprocess exit code |
| log_path | str | Required | Path to the saved LLM conversation history |
| stdout_log_path | str | — | Path to the raw subprocess stdout/stderr log on disk |
| verification_result | ValidationResult | — | The typed output from the test case's validator |
| total_tokens | int | — | Token count from cost summary line |
| input_tokens | int | — | Input tokens |
| output_tokens | int | — | Output tokens |
| cache_read_tokens | int | — | Cache read tokens |
| tool_calls | list[str] | — | Ordered list of tool names invoked during the trial |
| tool_call_count | int | — | Length of `tool_calls`; convenience aggregate |

### Report
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| experiment_id | UUID | FK → Experiment | Which experiment this reports |
| markdown_path | Path | Required | Path to the Markdown report file (contains aggregate sections followed by the per-trial summary and per-trial details) |
| json_path | Path | Required | Path to the structured JSON results file |
| generated_at | datetime | Required | When the report was generated |

## Relationships
| Source | Target | Type | Cardinality | Description |
|--------|--------|------|-------------|-------------|
| Experiment | ExperimentConfig | has | 1:1 | One config per experiment |
| Experiment | TrialResult | produces | 1:N | One experiment produces N trial results |
| Experiment | Report | generates | 1:1 | One report per experiment |
| TestCase | Validator | has | 1:1 | One validator per test case |
| TrialResult | ValidationResult | contains | 1:1 | One validation result per trial (if validator ran) |
| ExperimentConfig | CliAdapter | selects | 1:1 | `cli_template` resolves to exactly one `CliAdapter` instance used for every trial in the experiment |
| CliAdapter | UsageSummary | produces | 1:1 | `parse_usage` returns one `UsageSummary` per trial, merged into that trial's `TrialResult` token fields |

## Validation Rules
- `ValidationResult.status` must be EXCELLENT, PASS, or FAIL. The `_classify_final_status` logic from the existing runner (verifier-emitted `VERIFICATION_RESULT:` markers take precedence over execution status) is carried forward.
- `TrialResult.status` may additionally be TIMEOUT or ERROR for non-verification outcomes.
- All token fields default to 0 when the cost summary line is missing (timeout/aborted run).
- `TrialResult.duration` is always populated (wall-clock seconds), even for `TIMEOUT`/`ERROR` trials, so it is safe to include them in the `Avg dur (s)` mean for the **By Model** aggregate table.
- `ExperimentConfig.cli_template` must resolve to either a built-in adapter name (`zrb`, `claude-code`, `opencode`) or a dotted import path to a class implementing the `CliAdapter` protocol; anything else is rejected before any trial begins.
