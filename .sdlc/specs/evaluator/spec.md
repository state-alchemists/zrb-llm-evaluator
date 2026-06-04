# Feature Spec: evaluator

> Multi-trial experiment runner for `zrb chat`. Reverse-engineered from code at commit `8a52af8`.

## Requirements

### 1. CLI Entry Point

#### REQ-001 — Unique Session Names
WHEN a trial is executed THEN SHALL a unique session name be generated from its model identifier, test case name, and trial index.
WHEN the session name is generated THEN SHALL colons in the model name be replaced with underscores to produce a filesystem-safe string.

#### REQ-002 — Concurrency-Bounded Trial Execution
WHERE the experiment configuration specifies a parallelism value P THEN SHALL at most P trials execute concurrently using an `asyncio.Semaphore`.

#### REQ-003 — Pydantic Model Persistence
ALWAYS SHALL all structured results (trial results, experiment envelopes, validation results) use Pydantic v2 models with `model_dump(mode="json")` for serialization.
ALWAYS SHALL file writes use an atomic write pattern (write to a temporary file in the same directory, then `os.replace`).

#### REQ-004 — Cell Plan Cartesian Product
WHEN an experiment is started THEN SHALL a cell plan be built as the Cartesian product of all specified models, all specified test-case directories, and all trial indices (1..trials).

#### REQ-005 — Process-Group Timeout Kill
WHEN a trial exceeds its configured timeout THEN SHALL the entire descendant process group be terminated via `os.killpg(pgid, signal.SIGKILL)`.
WHEN the subprocess is created THEN SHALL `start_new_session=True` be passed so the child becomes its own process-group leader.

#### REQ-006 — Resume on Re-run
WHEN an experiment output directory already contains a `results.json` file THEN SHALL existing terminal-status trials be skipped and only pending cells executed.
ALWAYS SHALL the experiment ID and `started_at` timestamp from a prior incomplete run be preserved on resume.

#### REQ-007 — Verification Marker Override
WHEN the subprocess stdout contains a line matching `VERIFICATION_RESULT: {EXCELLENT|PASS|FAIL}` THEN SHALL that status override the exit-code-based classification.
UNLESS the verification marker is present THEN SHALL a non-zero exit code produce status `ERROR`.

#### REQ-008 — Log Path Reference
WHEN a trial result is produced THEN SHALL its `log_path` reference the saved LLM conversation history file (a `.json` file inside the cell's `history/` directory).

#### REQ-009 — Validator Invocation
WHEN a trial completes with a clean exit (non-ERROR, non-TIMEOUT) THEN SHALL its test case's validator be invoked with `output_dir`, `log_content`, and `trace` arguments.
WHEN the validator returns a `ValidationResult` THEN SHALL the result's status become the trial's final status (unless a verification marker already determined it).
ALWAYS SHALL validators implement `ValidatorProtocol` (a `@runtime_checkable` Protocol with a `validate` method returning `ValidationResult`).

#### REQ-010 — Configurable Parallelism
WHEN the experiment configuration specifies a parallelism value THEN SHALL it be passed to the `asyncio.Semaphore` constructor.
WHERE parallelism is 1 THEN SHALL trials execute sequentially.

#### REQ-011 — Validator Exception Handling
WHEN a validator raises an exception during trial validation THEN SHALL the trial status be set to `ERROR` and a `ValidationResult` with status `FAIL`, score `0.0`, and a `validator_error` detail check be recorded.

#### REQ-012 — Async Core Runner
ALWAYS SHALL concurrent experiment runs use `asyncio` (not `threading` or `multiprocessing`).
WHEN the CLI entry point is invoked THEN SHALL it use `asyncio.run()` as a sync wrapper.

#### REQ-013 — Test Case Loading and Validation
WHEN a test case directory is loaded THEN SHALL it contain an `instruction.txt` file and a `validator.py` module.
WHERE `validator.py` is missing THEN SHALL a `ValueError` be raised.
WHERE `instruction.txt` is missing THEN SHALL a `ValueError` be raised.
WHERE the loaded module does not expose a `validator` attribute that implements `ValidatorProtocol` THEN SHALL a `ValueError` be raised.
WHEN loading multiple test cases THEN SHALL all errors be collected and raised in a single batch `ValueError`.

#### REQ-014 — CLI Argument Validation
WHEN the `run` command is invoked THEN SHALL `--models` and `--test-cases` be required.
WHEN required arguments are missing THEN SHALL the process exit with a non-zero code.
WHEN an `ExperimentConfig` validation error occurs THEN SHALL the error be displayed on stderr and the process exit with code 1.

#### REQ-015 — Model Identifier Format
ALWAYS SHALL each model identifier be in `provider:name` format (e.g. `openai:gpt-4o`).
WHERE a model identifier does not contain a colon or has an empty provider/name THEN SHALL a `ValidationError` be raised.

#### REQ-016 — Per-Trial LLM Journal Isolation
WHEN a trial is executed THEN SHALL the environment variables `{env_prefix}_LLM_HISTORY_DIR` and `{env_prefix}_LLM_JOURNAL_DIR` be set to per-trial paths.
ALWAYS SHALL the journal directory be a `notes/` sibling of the `history/` directory inside the cell directory.
ALWAYS SHALL each trial receive its own isolated journal directory.

#### REQ-017 — Result Persistence
WHEN a trial completes THEN SHALL its result be atomically appended to `results.json` in the output directory.
WHEN the experiment completes THEN SHALL the full `Experiment` envelope be atomically written to `experiment.json`.
WHEN the `list` command is invoked THEN SHALL it read and display results from `results.json`.
WHEN the `report` command is invoked THEN SHALL it read the `Experiment` envelope from `experiment.json` and regenerate the Markdown report.

#### REQ-018 — Subprocess Invocation
WHEN a trial runs THEN SHALL the configured CLI binary (`cli_name`, default `zrb`) be invoked as a subprocess with arguments: `chat --interactive false --yolo true --model <model> --message <instruction> --session <session_name>`.
WHEN the subprocess is invoked THEN SHALL stdout and stderr be merged and streamed directly to a `stdout.log` file in the cell directory.

#### REQ-019 — Cost and Tool-Call Extraction
WHEN a trial completes THEN SHALL token counts be parsed from the last `💸` cost summary line in the subprocess output.
WHEN the cost summary line is missing or incomplete THEN SHALL token fields default to 0.
WHEN multiple `💸` lines are present THEN SHALL only the last line be used.
WHEN the trial history JSON file is available THEN SHALL tool-call names be extracted from it.
WHEN the history file is missing, malformed, or of an unexpected shape THEN SHALL an empty list be returned (defensive).

### 2. Workdir Isolation

#### REQ-020 — Subprocess cwd Is Nested Workdir
WHEN a trial is executed THEN SHALL the subprocess current working directory be `{cell_dir}/workdir/`, not the cell directory root.

#### REQ-021 — Evaluation Artifacts Outside Workdir
ALWAYS SHALL evaluation artifacts (`stdout.log`, `history/`, `notes/`) be siblings of `workdir/` inside the cell directory, not children of `workdir/`.

#### REQ-022 — Empty Workdir When No Source
WHERE a test case directory has no `workdir/` subdirectory THEN SHALL an empty `{cell_dir}/workdir/` be created for the subprocess.

#### REQ-023 — Staged Files Land in Nested Workdir
WHEN a test case has a `workdir/` directory with files THEN SHALL those files be copied into `{cell_dir}/workdir/` during trial setup.
ALWAYS SHALL staged files appear only inside the nested workdir, never at the cell directory root.

#### REQ-024 — Metadata Files Never Staged
ALWAYS SHALL `validator.py` and `instruction.txt` never be copied into the subprocess working directory.
ALWAYS SHALL `{test_case_dir}/workdir` be the explicit staging source (not `{test_case_dir}` itself).

### 3. Report Generation

#### REQ-025 — Sorted Trial Rows
WHEN a Markdown report is generated THEN SHALL trial rows be sorted by (model ASC, test_case ASC, trial_index ASC).

#### REQ-026 — Per-Case Best Metric Bolding
WHERE a trial has status `PASS` or `EXCELLENT` THEN SHALL its best (minimum duration, maximum score, minimum total_tokens, minimum tool_call_count) metric values within the same test case be wrapped in Markdown bold.
WHERE a trial has status `FAIL`, `TIMEOUT`, or `ERROR` THEN SHALL it be excluded from the bold scope.
WHERE multiple trials are tied for the best value THEN SHALL all be bolded.

#### REQ-027 — Pure Markdown (No HTML)
ALWAYS SHALL the report be pure Markdown without embedded HTML tags (`<b>`, `<span>`, `<i>`, etc.).

#### REQ-028 — Bold Best Metrics
UNLESS there are no eligible trials THEN SHALL for each test case the minimum `duration`, maximum `score`, minimum `total_tokens`, and minimum `tool_call_count` among `PASS`/`EXCELLENT` trials be rendered in bold.

#### REQ-029 — Status Icon Mapping
WHEN a trial status is displayed THEN SHALL it be prefixed with the corresponding icon:
- `EXCELLENT` → `👍`
- `PASS` → `✅`
- `FAIL` → `❌`
- `TIMEOUT` → `⏱️`
- `ERROR` → `⚠️`

#### REQ-030 — Aggregate Sections
WHEN a Markdown report is generated THEN SHALL it include aggregate sections: Overall Status, By Model, By Test Case, Grid, Stability, and Failing / Timeout Trials.

#### REQ-031 — Deterministic Report Output
WHEN the same experiment is rendered twice THEN SHALL the Markdown report be byte-identical.

#### REQ-032 — Per-Trial Details
WHEN a Markdown report is generated THEN SHALL each trial have a detail section showing: status, duration, exit code, history path, token breakdown, tool calls, and validation results with per-check pass/fail.

#### REQ-033 — Aggregate Sections Computed at Render Time
ALWAYS SHALL aggregate metrics be computed when the report is generated, not stored pre-computed in the experiment envelope.

#### REQ-034 — Report Header
WHEN a Markdown report is generated THEN SHALL it include a header with: experiment ID, start time, completion time, and generation timestamp.

#### REQ-035 — Overall Status Table
WHEN the Overall Status section is rendered THEN SHALL it show per-status counts and percentages in canonical order: EXCELLENT, PASS, FAIL, TIMEOUT, ERROR.

#### REQ-036 — By Model Table
WHEN the By Model section is rendered THEN SHALL it show per-model trial counts by status and average duration.

#### REQ-037 — By Test Case Table
WHEN the By Test Case section is rendered THEN SHALL it show per-test-case trial counts by status.

#### REQ-038 — Grid Section
WHEN the Grid section is rendered THEN SHALL models be rows, test cases be columns, and each cell show trial outcome icons.

#### REQ-039 — Empty Grid Cells
WHERE a (model × test_case) combination has no trials THEN SHALL its grid cell display an em dash (`—`).

#### REQ-040 — Failing / Timeout Trials Section
WHEN the Failing / Timeout section is rendered THEN SHALL it list trials with status FAIL, TIMEOUT, or ERROR, sorted by (model, test_case, trial_index).

#### REQ-041 — Stable vs Flaky vs Broken Classification
WHEN the Stability section is rendered THEN SHALL per-(model, test_case) pass rate be shown:
- ALL trials passed → `🟢 STABLE`
- SOME passed → `🟡 FLAKY`
- NONE passed → `🔴 BROKEN`

#### REQ-042 — JSON Report Output
WHEN JSON report is generated THEN SHALL the full `Experiment` envelope be serialized to a `.json` file atomically.

## Non-Functional Requirements

### NFR-001 — Per-Trial Overhead
ALWAYS SHALL per-trial overhead (setup, teardown, file I/O without LLM call) be less than 2 seconds.

### NFR-002 — 100+ Cell Throughput
ALWAYS SHALL the runner handle 100+ trial cells without error, with all results persisted to disk.

### NFR-003 — Atomic JSON Persistence
ALWAYS SHALL all JSON file writes use an atomic pattern (tempfile + os.replace) to prevent partial writes.

### NFR-004 — No HTML in Reports
ALWAYS SHALL generated reports be pure Markdown with no HTML markup.

## Correctness

> Correctness properties reverse-engineered from code at commit `8a52af8`.

### Round-Trip (Serialization Symmetry)
**Enforced.** All structured results (`TrialResult`, `ValidationResult`, `Experiment`, `ExperimentConfig`, `Report`) are Pydantic v2 models. `model_dump(mode="json")` produces JSON-compatible dicts that `model_validate()` can restore. The test suite explicitly validates round-trip fidelity (`test_round_trip_serialization` in `test_models.py`). **Verified by:** UT-022, IT-001, IT-002.

### Uniqueness
**Partially enforced.**
- **Session names:** `make_session_name()` combines model-safe-name + test-case-name + trial-index, producing distinct session names per cell. Verified by UT-001.
- **Trial result identities:** Each `TrialResult` gets a random UUID `id`. No dedup logic on re-load — duplicate entries from interrupted resume are prevented by `ResumeManager.is_completed()` filtering, not by uniqueness enforcement.
- **Experiment identity:** Each `Experiment` gets a random UUID `id`. On resume, the existing id is preserved, not a new one generated.
- **No DB-level uniqueness constraint since all persistence is file-based.**

### Atomicity
**Enforced at file level.** Three critical write paths all use the same atomic pattern:
1. `ResumeManager._flush()` — writes `results.json` via tempfile + `os.replace` (`runner.py:163-174`).
2. `generate_json_report()` — writes experiment JSON via tempfile + `os.replace` (`reporter.py:398-411`).
3. `_persist_experiment()` — writes `experiment.json` via tempfile + `os.replace` (`runner.py:632-648`).

**Not enforced at subprocess level.** A trial interrupted mid-execution (before `ResumeManager.append()` is called) loses its partial output — the cell directory is cleaned and re-created on retry (`shutil.rmtree(cell_dir)` in `TrialRunner.run()`). This is acceptable since the trial has no side effects outside its cell directory.

### Validation
**Enforced at multiple layers:**
1. **CLI layer (`cli.py:58-69`):** `ExperimentConfig` construction validates model format, field ranges.
2. **Config layer (`models.py:101-110`):** Pydantic field validators enforce: `models` (min_length=1, each `provider:name`), `test_case_dirs` (min_length=1), `trials` (ge=1), `parallelism` (ge=1), `timeout` (ge=30).
3. **Test case loading layer (`loader.py`):** Missing `instruction.txt` / `validator.py` raises `ValueError`; validator module without `validator` attribute raises `ValueError`; validator not implementing `ValidatorProtocol` raises `ValueError`; batch loading aggregates all errors before raising.
4. **Runtime validation in runner:** `_extract_verification_marker()` validates marker values against allowed set (`EXCELLENT`, `PASS`, `FAIL`). Validator exceptions are caught and produce structured error results.

**Not enforced:** No schema validation on subprocess output (stdout parsing uses regex with defaults). No validation that the CLI binary (`cli_name`) actually exists before trial execution.

### Idempotency
**Enforced for re-runs (resume).** `ResumeManager.is_completed()` checks each cell against persisted terminal-status results before scheduling. Re-running the same experiment against the same output directory skips all completed cells and preserves the experiment identity.

**Not enforced at trial level.** Re-running a partially-complete experiment where some cell directories exist but no `results.json` entry was appended will wipe and re-execute those cells (cell directory cleanup via `shutil.rmtree`). This is safe — no persistent side effects outside the cell directory.

### Defensive Design
**Widespread.** Key defensive patterns:
- **Cost parser:** Missing file → empty fields. Malformed JSON → empty fields. Unknown history shapes → empty list.
- **Trial runner:** Unexpected exceptions during trial execution → `ERROR` status with log. Validator exceptions → structured `ValidationResult` with error details.
- **Build trace (`build_trial_trace`):** Missing/malformed history files → empty `TrialTrace` (never blocks validation).
- **Experiment envelope loading:** Corrupt `experiment.json` → fresh envelope created (silent fallback).

## File Persistence Architecture

```
{output_dir}/
├── results.json              # Streaming result log (appended per trial)
├── experiment.json           # Full experiment envelope (written at end)
├── report.md                 # Markdown report (generated on completion)
├── {model_safe}/
│   └── {test_case}/
│       ├── trial-{N}/
│       │   ├── workdir/      # Subprocess cwd (staged test case files)
│       │   ├── stdout.log    # Combined subprocess stdout+stderr
│       │   ├── history/      # LLM conversation history JSON
│       │   │   └── {session}.json
│       │   └── notes/        # LLM journal (per-trial isolation)
│       └── ...
└── ...
```

Key invariants:
- `workdir/` contains ONLY staged test-case files (never `validator.py`, `instruction.txt`, or evaluation artifacts).
- `history/`, `stdout.log`, `notes/` are always siblings of `workdir/`, never children.
- Cell directory is cleaned before each fresh trial run.

## Concurrency Model

```
asyncio.run()
  └─ run_experiment()
       └─ WorkSteward.run_all()
            ├─ Semaphore(config.parallelism)
            └─ asyncio.gather(*tasks)
                 └─ TrialRunner.run()
                      ├─ create_subprocess_exec(zrb chat ...)
                      ├─ await asyncio.wait_for(proc.wait(), timeout)
                      └─ validate() → ResumeManager.append()
```

- **Scheduling:** Semaphore limits concurrent subprocesses to `config.parallelism`.
- **Timeout:** `asyncio.wait_for` wraps `proc.wait()`; on expiry, `os.killpg` terminates the entire process group.
- **Resilience:** A failure in one trial does not cascade — each trial runs in its own task with independent error handling.

## Token Cost Extraction

```
stdout ──→ regex parse ──→ {total, input, output, cache_read}
             (last 💸 line only)
```

The regex uses negative lookbehinds to distinguish `Input:` from `Audio Input:` and `Output:` from `Audio Output:`. When no match is found, all fields default to 0.

## Test Coverage Status

The test suite (`tests/experiment-runner/`) provides good coverage of the public API. Notable coverage:

| Area | Coverage | Key Tests |
|------|----------|-----------|
| Cell plan generation | Full | UT-004 |
| Session naming | Full | UT-001 |
| Resume/restart | Full | UT-006, IT-002 |
| Timeout + process group kill | Full | UT-005, UT-043 |
| Workdir isolation | Full | UT-027..UT-031, IT-005 |
| Cost summary parsing | Full | UT-022, UT-044, UT-045 |
| Tool call extraction | Full | UT-026 |
| Verification markers | Full | UT-008 |
| Validator invocation | Full | UT-010, UT-011, UT-013 |
| Report rendering | Full | UT-032..UT-042 |
| CLI argument validation | Full | UT-016, UT-049, UT-050 |
| Env prefix customization | Full | UT-048 |
| Experiment lifecycle (corrupt JSON recovery) | Full | UT-051 |
| Concurrent append safety | Full | UT-052 |
| Parallel execution | Partial | UT-002, UT-012, IT-003 |
| Stress (100+ cells) | Full | NFR-002 |
| No zrb import | Full | UT-025 |

All 5 gaps from the initial assessment were resolved by quickfix `quickfix-2026-05-27T06-26-31.md` (UT-048 through UT-052).

---
*Merged from `requirements.md` + `design.md` into the single-file spec format on 2026-06-04. Originally documented from code at 2026-05-27T06-16-43. Scope: evaluator module (src/zrb_llm_evaluator/ + tests/experiment-runner/). Source commit: 8a52af8.*
