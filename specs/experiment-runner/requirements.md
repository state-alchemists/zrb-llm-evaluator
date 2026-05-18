# Feature Requirements: experiment-runner

## EARS Requirements

### Invariants (ALWAYS SHALL)
- `REQ-001` (from AC-003): ALWAYS SHALL each trial generate a unique session name that survives timeout.
- `REQ-002` (from AC-006): ALWAYS SHALL the number of concurrent subprocesses not exceed the configured parallelism.
- `REQ-003` (from AC-007): ALWAYS SHALL completed trial results persist to disk before the next trial begins.

### Event-Driven (WHEN/THEN SHALL)
- `REQ-004` (from AC-001): WHEN the user invokes `run` THEN SHALL the framework iterate every model × test case × trial combination.
- `REQ-005` (from AC-006): WHEN a trial exceeds the configured timeout THEN SHALL the subprocess be killed and the trial recorded as TIMEOUT.
- `REQ-006` (from AC-007): WHEN the framework starts and finds an existing `results.json` THEN SHALL it load the file and skip all cells with a terminal status.
- `REQ-007`: WHEN a subprocess returns a non-zero exit code THEN SHALL the trial be recorded as ERROR unless a verification marker overrides it.

### State-Driven (WHERE/THEN SHALL)
- `REQ-008` (from AC-003): WHERE a trial is in TIMEOUT or ERROR state THEN SHALL the partial LLM history file on disk still be referenced in the result.
- `REQ-009` (from AC-002): WHERE a trial completed with a valid output THEN SHALL the test case's validator be invoked with the output directory and log content.

### Conditional (AS/THEN SHALL)
- `REQ-010` (from AC-006): AS parallelism is greater than 1 THEN SHALL trials be dispatched across concurrent async tasks gated by a semaphore.
- `REQ-011` (from AC-002): AS a validator raises an exception THEN SHALL the trial be recorded as ERROR with the exception message in details.
- `REQ-012` (from AC-004): AS `--cli-name` is provided THEN SHALL the runner invoke that binary instead of `zrb`.

### Exception (UNLESS/THEN SHALL)
- `REQ-013` (from AC-002): UNLESS a test case directory contains a valid validator module THEN SHALL the runner reject that test case with a clear error message.
- `REQ-014` (from AC-001): UNLESS all required arguments (models, test-cases, trials) are provided THEN SHALL the CLI print usage and exit non-zero.

### Mandatory (SHALL)
- `REQ-015` (from AC-001): The runner SHALL accept models in `provider:model_name` format (e.g., `openai:gpt-4o`).
- `REQ-016` (from AC-003): The runner SHALL set `ZRB_LLM_HISTORY_DIR` and pass `--session` to each `zrb chat` invocation.
- `REQ-017` (from AC-005): The runner SHALL write each completed `TrialResult` to `results.json` immediately upon finishing.
- `REQ-018` (from AC-001): The runner SHALL create a per-cell output directory: `{output_dir}/{model_safe}/{test_case}/trial-{N}/`.
- `REQ-019`: The runner SHALL parse the cost summary line from subprocess stdout and populate token fields in `TrialResult`.

## Non-Functional Requirements
| ID | Requirement | Target | Validated By |
|----|-------------|--------|--------------|
| NFR-001 | Per-trial overhead (setup + parsing + validation) shall not exceed 2 seconds when no LLM call is made | < 2s | test (benchmark) |
| NFR-002 | The runner shall handle at least 100 model × test case cells without OOM | 100 cells | test (stress) |

## NFRs Validated Outside Code
- None.
