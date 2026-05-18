# Design: experiment-runner

## Correctness Properties

### Round-Trip
All result models (`TrialResult`, `ValidationResult`, `ValidationCheck`) are Pydantic v2 models. Serialization uses `.model_dump(mode="json")`; deserialization uses `.model_validate()`. The `results.json` file is a list of `TrialResult` dicts. Token fields default to 0 when absent (timeout/aborted runs). The uuid field ensures every result round-trips to a unique identity.

### Uniqueness
Each trial cell is identified by the triple `(model, test_case, trial_index)`. This triple must be unique within an experiment. The output directory hierarchy enforces this: `{output_dir}/{model_safe}/{test_case}/trial-{N}` maps exactly to one cell. On resume, cells are deduplicated by this triple using a dictionary key.

### Atomicity
Each trial result is appended to `results.json` atomically: write to a temp file, then `os.rename()` — which is atomic on the same filesystem. If the process crashes mid-trial, the partial `results.json` (missing only the in-flight trial) is valid JSON. Unused workdirs from interrupted trials are cleaned up on resume.

### Validation
`ExperimentConfig` is a Pydantic model validated at CLI entry:
- `models`: list of strings matching `provider:name` pattern, min 1
- `test_case_dirs`: existing directory paths, min 1
- `trials`: int >= 1
- `parallelism`: int >= 1
- `timeout`: int >= 30
- `cli_name`: non-empty string

Test case modules are dynamically imported and checked against `ValidatorProtocol` at load time. A test case that fails protocol conformance is rejected with a clear error before any trial begins.

### Idempotency
The runner is idempotent when pointed at an existing output directory. On startup, it loads `results.json` and skips any cell whose triple `(model, test_case, trial_index)` already has a terminal status (EXCELLENT/PASS/FAIL/TIMEOUT/ERROR). Re-running the same command produces the same results without duplication. Non-terminal cells (from a prior interrupted run) are retried.

## API Surface

The primary interface is a CLI with subcommands:

| Method | Path | Request | Response | Auth |
|--------|------|---------|----------|------|
| CLI | `zrb-llm-evaluator run` | `--models`, `--test-cases`, `--trials`, `--parallelism`, `--timeout`, `--cli-name`, `--output-dir` | stdout progress + filesystem results | None |
| CLI | `zrb-llm-evaluator list [dir]` | `--dir` (optional, default CWD) | Table of previously-run experiments | None |
| CLI | `zrb-llm-evaluator report [dir]` | `--dir` (optional, default CWD) | Re-generated report to stdout | None |

## Error Handling

| Error | Code | Status | Recovery |
|-------|------|--------|----------|
| Test case validator not found or invalid | `INVALID_CASE` | Runner exits non-zero before any trial | User fixes validator module |
| zrb chat subprocess not found | `CLI_NOT_FOUND` | Trial: ERROR, continue to next cell | User installs zrb or corrects --cli-name |
| Subprocess timeout | `TIMEOUT` | Trial: TIMEOUT, partial log preserved | Retry with higher timeout |
| Subprocess non-zero exit | `EXIT_ERROR` | Trial: ERROR (unless overridden by verification marker) | Debug via preserved log |
| Validator raised exception | `VALIDATOR_ERROR` | Trial: ERROR with exception message | Fix validator, resume |
| results.json write failure | `WRITE_ERROR` | Runner exits with partial results | Fix filesystem, resume (skips completed cells) |
| Ctrl+C / SIGINT | — | In-progress trials are killed; results.json is consistent (mid-write cell may be partial) | Resume skips completed cells, retries in-progress ones |

## Data Model

| Entity | Fields Used | Notes |
|--------|-------------|-------|
| ExperimentConfig | models, test_case_dirs, trials, parallelism, timeout, cli_name | Input to the runner |
| TestCase | name, instruction, workdir, validator | Discovered from disk per test case directory |
| TrialResult | model, test_case, trial_index, status, duration, tool_calls, tool_call_count, exit_code, log_path, verification_result, total_tokens, input_tokens, output_tokens, cache_read_tokens | Written to results.json after each cell |
| ValidationResult | status, score, details | Returned by the validator protocol |
| ValidationCheck | name, passed, message | Per-check breakdown within ValidationResult |

### Entity Modifications
None — the entity dictionary covers all fields this feature needs.
