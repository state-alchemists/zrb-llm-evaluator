# Feature Requirements: experiment-runner

## EARS Requirements

### Invariants (ALWAYS SHALL)
- `REQ-001` (from AC-003): ALWAYS SHALL each trial generate a unique session name that survives timeout.
- `REQ-002` (from AC-006): ALWAYS SHALL the number of concurrent subprocesses not exceed the configured parallelism.
- `REQ-003` (from AC-007): ALWAYS SHALL completed trial results persist to disk before the next trial begins.
- `REQ-020` (from AC-008): ALWAYS SHALL the trial subprocess `cwd` be a nested `workdir/` directory inside the per-trial cell directory — never the cell directory itself.
- `REQ-021` (from AC-008): ALWAYS SHALL the trial's `stdout.log`, `history/` directory, and any other evaluation artifacts live as siblings of `workdir/` and not inside it.
- `REQ-025` (from AC-010): ALWAYS SHALL trial rows in `report.md` be sorted by `model` ascending, then `test_case` ascending, then `trial_index` ascending.
- `REQ-026` (from AC-011): ALWAYS SHALL the best-metric bolding scope be one test case (spanning all models and all trials in that test case), and ALWAYS SHALL trials with status `FAIL`, `TIMEOUT`, or `ERROR` be excluded from the best-metric computation.
- `REQ-027` (from AC-012): ALWAYS SHALL `report.md` use pure Markdown syntax — no embedded HTML — for sort order, bolding, and status icons.

### Event-Driven (WHEN/THEN SHALL)
- `REQ-004` (from AC-001): WHEN the user invokes `run` THEN SHALL the framework iterate every model × test case × trial combination.
- `REQ-005` (from AC-006): WHEN a trial exceeds the configured timeout THEN SHALL the subprocess **and its entire descendant process group** be killed and the trial recorded as TIMEOUT. <!-- updated 2026-05-21 (quickfix-2026-05-21T15-03-46) -->
- `REQ-006` (from AC-007): WHEN the framework starts and finds an existing `results.json` THEN SHALL it load the file and skip all cells with a terminal status.
- `REQ-007`: WHEN a subprocess returns a non-zero exit code THEN SHALL the trial be recorded as ERROR unless a verification marker overrides it.
- `REQ-022` (from AC-009): WHEN a test case has no dedicated `workdir/` source to stage THEN SHALL the runner create an empty `workdir/` directory inside the trial cell before launching the subprocess.

### State-Driven (WHERE/THEN SHALL)
- `REQ-008` (from AC-003): WHERE a trial is in TIMEOUT or ERROR state THEN SHALL the partial LLM history file on disk still be referenced in the result.
- `REQ-009` (from AC-002): WHERE a trial completed with a valid output THEN SHALL the test case's validator be invoked with the output directory and log content.
- `REQ-028` (from AC-011): WHERE a trial with status `PASS` or `EXCELLENT` ties or sets the best value within its test case for any of (`duration` min, `score` max, `total_tokens` min, `tool_call_count` min) THEN SHALL the corresponding metric cell in `report.md` be wrapped in Markdown bold (`**…**`).

### Conditional (AS/THEN SHALL)
- `REQ-010` (from AC-006): AS parallelism is greater than 1 THEN SHALL trials be dispatched across concurrent async tasks gated by a semaphore.
- `REQ-011` (from AC-002): AS a validator raises an exception THEN SHALL the trial be recorded as ERROR with the exception message in details.
- `REQ-012` (from AC-004): AS `--cli-name` is provided THEN SHALL the runner invoke that binary instead of `zrb`.
- `REQ-029` (from AC-012): AS a trial's status is rendered in `report.md` THEN SHALL the status text be prefixed with the icon mapping: `EXCELLENT` → 👍, `PASS` → ✅, `FAIL` → ❌, `TIMEOUT` → ⏱️, `ERROR` → ⚠️.

### Exception (UNLESS/THEN SHALL)
- `REQ-013` (from AC-002): UNLESS a test case directory contains a valid validator module THEN SHALL the runner reject that test case with a clear error message.
- `REQ-014` (from AC-001): UNLESS all required arguments (models, test-cases, trials) are provided THEN SHALL the CLI print usage and exit non-zero.

### Mandatory (SHALL)
- `REQ-015` (from AC-001): The runner SHALL accept models in `provider:model_name` format (e.g., `openai:gpt-4o`).
- `REQ-016` (from AC-003): The runner SHALL set `ZRB_LLM_HISTORY_DIR` and `ZRB_LLM_JOURNAL_DIR` to per-cell sibling directories of `workdir/`, and SHALL pass `--session` to each `zrb chat` invocation, so that conversation history and journal notes are isolated per trial. <!-- updated 2026-05-24 (quickfix-2026-05-24T23-45-24) -->
- `REQ-017` (from AC-005): The runner SHALL write each completed `TrialResult` to `results.json` immediately upon finishing.
- `REQ-018` (from AC-001): The runner SHALL create a per-cell output directory: `{output_dir}/{model_safe}/{test_case}/trial-{N}/`.
- `REQ-019`: The runner SHALL parse the zrb `💸` usage summary line from subprocess stdout — matching the actual zrb format `💸 (Requests: … | Tool Calls: … | Total: T) Input: I | Audio Input: … | Output: O | Audio Output: … | Cache Read: C | …` — and populate `total_tokens`, `input_tokens`, `output_tokens`, and `cache_read_tokens` in `TrialResult`. WHERE multiple summary lines appear, ONLY the LAST one SHALL be used (zrb's per-run totals are already cumulative across turns; summing would double-count). <!-- updated 2026-05-24 (quickfix-2026-05-24T23-45-24) -->
- `REQ-023` (from AC-008): The runner SHALL stage the test case's `workdir/` contents into the trial's nested `workdir/` directory, never into the cell directory itself.
- `REQ-024` (from AC-008): The runner SHALL ensure that `validator.py`, `instruction.txt`, and any other test-case metadata files are never copied into the trial's `workdir/`.

## Non-Functional Requirements
| ID | Requirement | Target | Validated By |
|----|-------------|--------|--------------|
| NFR-001 | Per-trial overhead (setup + parsing + validation) shall not exceed 2 seconds when no LLM call is made | < 2s | test (benchmark) |
| NFR-002 | The runner shall handle at least 100 model × test case cells without OOM | 100 cells | test (stress) |

## NFRs Validated Outside Code
- None.
