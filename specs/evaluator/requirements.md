# Requirements: evaluator

> Multi-trial experiment runner for `zrb chat`. Reverse-engineered from code at commit `8a52af8`.

## 1. CLI Entry Point

### REQ-001 — Unique Session Names
WHEN a trial is executed THEN SHALL a unique session name be generated from its model identifier, test case name, and trial index.
WHEN the session name is generated THEN SHALL colons in the model name be replaced with underscores to produce a filesystem-safe string.

### REQ-002 — Concurrency-Bounded Trial Execution
WHERE the experiment configuration specifies a parallelism value P THEN SHALL at most P trials execute concurrently using an `asyncio.Semaphore`.

### REQ-003 — Pydantic Model Persistence
ALWAYS SHALL all structured results (trial results, experiment envelopes, validation results) use Pydantic v2 models with `model_dump(mode="json")` for serialization.
ALWAYS SHALL file writes use an atomic write pattern (write to a temporary file in the same directory, then `os.replace`).

### REQ-004 — Cell Plan Cartesian Product
WHEN an experiment is started THEN SHALL a cell plan be built as the Cartesian product of all specified models, all specified test-case directories, and all trial indices (1..trials).

### REQ-005 — Process-Group Timeout Kill
WHEN a trial exceeds its configured timeout THEN SHALL the entire descendant process group be terminated via `os.killpg(pgid, signal.SIGKILL)`.
WHEN the subprocess is created THEN SHALL `start_new_session=True` be passed so the child becomes its own process-group leader.

### REQ-006 — Resume on Re-run
WHEN an experiment output directory already contains a `results.json` file THEN SHALL existing terminal-status trials be skipped and only pending cells executed.
ALWAYS SHALL the experiment ID and `started_at` timestamp from a prior incomplete run be preserved on resume.

### REQ-007 — Verification Marker Override
WHEN the subprocess stdout contains a line matching `VERIFICATION_RESULT: {EXCELLENT|PASS|FAIL}` THEN SHALL that status override the exit-code-based classification.
UNLESS the verification marker is present THEN SHALL a non-zero exit code produce status `ERROR`.

### REQ-008 — Log Path Reference
WHEN a trial result is produced THEN SHALL its `log_path` reference the saved LLM conversation history file (a `.json` file inside the cell's `history/` directory).

### REQ-009 — Validator Invocation
WHEN a trial completes with a clean exit (non-ERROR, non-TIMEOUT) THEN SHALL its test case's validator be invoked with `output_dir`, `log_content`, and `trace` arguments.
WHEN the validator returns a `ValidationResult` THEN SHALL the result's status become the trial's final status (unless a verification marker already determined it).
ALWAYS SHALL validators implement `ValidatorProtocol` (a `@runtime_checkable` Protocol with a `validate` method returning `ValidationResult`).

### REQ-010 — Configurable Parallelism
WHEN the experiment configuration specifies a parallelism value THEN SHALL it be passed to the `asyncio.Semaphore` constructor.
WHERE parallelism is 1 THEN SHALL trials execute sequentially.

### REQ-011 — Validator Exception Handling
WHEN a validator raises an exception during trial validation THEN SHALL the trial status be set to `ERROR` and a `ValidationResult` with status `FAIL`, score `0.0`, and a `validator_error` detail check be recorded.

### REQ-012 — Async Core Runner
ALWAYS SHALL concurrent experiment runs use `asyncio` (not `threading` or `multiprocessing`).
WHEN the CLI entry point is invoked THEN SHALL it use `asyncio.run()` as a sync wrapper.

### REQ-013 — Test Case Loading and Validation
WHEN a test case directory is loaded THEN SHALL it contain an `instruction.txt` file and a `validator.py` module.
WHERE `validator.py` is missing THEN SHALL a `ValueError` be raised.
WHERE `instruction.txt` is missing THEN SHALL a `ValueError` be raised.
WHERE the loaded module does not expose a `validator` attribute that implements `ValidatorProtocol` THEN SHALL a `ValueError` be raised.
WHEN loading multiple test cases THEN SHALL all errors be collected and raised in a single batch `ValueError`.

### REQ-014 — CLI Argument Validation
WHEN the `run` command is invoked THEN SHALL `--models` and `--test-cases` be required.
WHEN required arguments are missing THEN SHALL the process exit with a non-zero code.
WHEN an `ExperimentConfig` validation error occurs THEN SHALL the error be displayed on stderr and the process exit with code 1.

### REQ-015 — Model Identifier Format
ALWAYS SHALL each model identifier be in `provider:name` format (e.g. `openai:gpt-4o`).
WHERE a model identifier does not contain a colon or has an empty provider/name THEN SHALL a `ValidationError` be raised.

### REQ-016 — Per-Trial LLM Journal Isolation
WHEN a trial is executed THEN SHALL the environment variables `{env_prefix}_LLM_HISTORY_DIR` and `{env_prefix}_LLM_JOURNAL_DIR` be set to per-trial paths.
ALWAYS SHALL the journal directory be a `notes/` sibling of the `history/` directory inside the cell directory.
ALWAYS SHALL each trial receive its own isolated journal directory.

### REQ-017 — Result Persistence
WHEN a trial completes THEN SHALL its result be atomically appended to `results.json` in the output directory.
WHEN the experiment completes THEN SHALL the full `Experiment` envelope be atomically written to `experiment.json`.
WHEN the `list` command is invoked THEN SHALL it read and display results from `results.json`.
WHEN the `report` command is invoked THEN SHALL it read the `Experiment` envelope from `experiment.json` and regenerate the Markdown report.

### REQ-018 — Subprocess Invocation
WHEN a trial runs THEN SHALL the configured CLI binary (`cli_name`, default `zrb`) be invoked as a subprocess with arguments: `chat --interactive false --yolo true --model <model> --message <instruction> --session <session_name>`.
WHEN the subprocess is invoked THEN SHALL stdout and stderr be merged and streamed directly to a `stdout.log` file in the cell directory.

### REQ-019 — Cost and Tool-Call Extraction
WHEN a trial completes THEN SHALL token counts be parsed from the last `💸` cost summary line in the subprocess output.
WHEN the cost summary line is missing or incomplete THEN SHALL token fields default to 0.
WHEN multiple `💸` lines are present THEN SHALL only the last line be used.
WHEN the trial history JSON file is available THEN SHALL tool-call names be extracted from it.
WHEN the history file is missing, malformed, or of an unexpected shape THEN SHALL an empty list be returned (defensive).

## 2. Workdir Isolation

### REQ-020 — Subprocess cwd Is Nested Workdir
WHEN a trial is executed THEN SHALL the subprocess current working directory be `{cell_dir}/workdir/`, not the cell directory root.

### REQ-021 — Evaluation Artifacts Outside Workdir
ALWAYS SHALL evaluation artifacts (`stdout.log`, `history/`, `notes/`) be siblings of `workdir/` inside the cell directory, not children of `workdir/`.

### REQ-022 — Empty Workdir When No Source
WHERE a test case directory has no `workdir/` subdirectory THEN SHALL an empty `{cell_dir}/workdir/` be created for the subprocess.

### REQ-023 — Staged Files Land in Nested Workdir
WHEN a test case has a `workdir/` directory with files THEN SHALL those files be copied into `{cell_dir}/workdir/` during trial setup.
ALWAYS SHALL staged files appear only inside the nested workdir, never at the cell directory root.

### REQ-024 — Metadata Files Never Staged
ALWAYS SHALL `validator.py` and `instruction.txt` never be copied into the subprocess working directory.
ALWAYS SHALL `{test_case_dir}/workdir` be the explicit staging source (not `{test_case_dir}` itself).

## 3. Report Generation

### REQ-025 — Sorted Trial Rows
WHEN a Markdown report is generated THEN SHALL trial rows be sorted by (model ASC, test_case ASC, trial_index ASC).

### REQ-026 — Per-Case Best Metric Bolding
WHERE a trial has status `PASS` or `EXCELLENT` THEN SHALL its best (minimum duration, maximum score, minimum total_tokens, minimum tool_call_count) metric values within the same test case be wrapped in Markdown bold.
WHERE a trial has status `FAIL`, `TIMEOUT`, or `ERROR` THEN SHALL it be excluded from the bold scope.
WHERE multiple trials are tied for the best value THEN SHALL all be bolded.

### REQ-027 — Pure Markdown (No HTML)
ALWAYS SHALL the report be pure Markdown without embedded HTML tags (`<b>`, `<span>`, `<i>`, etc.).

### REQ-028 — Bold Best Metrics
UNLESS there are no eligible trials THEN SHALL for each test case the minimum `duration`, maximum `score`, minimum `total_tokens`, and minimum `tool_call_count` among `PASS`/`EXCELLENT` trials be rendered in bold.

### REQ-029 — Status Icon Mapping
WHEN a trial status is displayed THEN SHALL it be prefixed with the corresponding icon:
- `EXCELLENT` → `👍`
- `PASS` → `✅`
- `FAIL` → `❌`
- `TIMEOUT` → `⏱️`
- `ERROR` → `⚠️`

### REQ-030 — Aggregate Sections
WHEN a Markdown report is generated THEN SHALL it include aggregate sections: Overall Status, By Model, By Test Case, Grid, Stability, and Failing / Timeout Trials.

### REQ-031 — Deterministic Report Output
WHEN the same experiment is rendered twice THEN SHALL the Markdown report be byte-identical.

### REQ-032 — Per-Trial Details
WHEN a Markdown report is generated THEN SHALL each trial have a detail section showing: status, duration, exit code, history path, token breakdown, tool calls, and validation results with per-check pass/fail.

### REQ-033 — Aggregate Sections Computed at Render Time
ALWAYS SHALL aggregate metrics be computed when the report is generated, not stored pre-computed in the experiment envelope.

### REQ-034 — Report Header
WHEN a Markdown report is generated THEN SHALL it include a header with: experiment ID, start time, completion time, and generation timestamp.

### REQ-035 — Overall Status Table
WHEN the Overall Status section is rendered THEN SHALL it show per-status counts and percentages in canonical order: EXCELLENT, PASS, FAIL, TIMEOUT, ERROR.

### REQ-036 — By Model Table
WHEN the By Model section is rendered THEN SHALL it show per-model trial counts by status and average duration.

### REQ-037 — By Test Case Table
WHEN the By Test Case section is rendered THEN SHALL it show per-test-case trial counts by status.

### REQ-038 — Grid Section
WHEN the Grid section is rendered THEN SHALL models be rows, test cases be columns, and each cell show trial outcome icons.

### REQ-039 — Empty Grid Cells
WHERE a (model × test_case) combination has no trials THEN SHALL its grid cell display an em dash (`—`).

### REQ-040 — Failing / Timeout Trials Section
WHEN the Failing / Timeout section is rendered THEN SHALL it list trials with status FAIL, TIMEOUT, or ERROR, sorted by (model, test_case, trial_index).

### REQ-041 — Stable vs Flaky vs Broken Classification
WHEN the Stability section is rendered THEN SHALL per-(model, test_case) pass rate be shown:
- ALL trials passed → `🟢 STABLE`
- SOME passed → `🟡 FLAKY`
- NONE passed → `🔴 BROKEN`

### REQ-042 — JSON Report Output
WHEN JSON report is generated THEN SHALL the full `Experiment` envelope be serialized to a `.json` file atomically.

## 4. Non-Functional Requirements

### NFR-001 — Per-Trial Overhead
ALWAYS SHALL per-trial overhead (setup, teardown, file I/O without LLM call) be less than 2 seconds.

### NFR-002 — 100+ Cell Throughput
ALWAYS SHALL the runner handle 100+ trial cells without error, with all results persisted to disk.

### NFR-003 — Atomic JSON Persistence
ALWAYS SHALL all JSON file writes use an atomic pattern (tempfile + os.replace) to prevent partial writes.

### NFR-004 — No HTML in Reports
ALWAYS SHALL generated reports be pure Markdown with no HTML markup.

---
*Documented from code at 2026-05-27T06-16-43. Scope: evaluator module (src/zrb_llm_evaluator/ + tests/experiment-runner/). Source commit: 8a52af8.*
