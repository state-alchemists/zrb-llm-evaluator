# Feature Spec: experiment-runner

## Requirements

*Requirements cite the source `AC-*` from the problem brief. EARS keywords appear inline.*

- `REQ-001` (AC-003): ALWAYS SHALL each trial generate a unique session name that survives timeout.
- `REQ-002` (AC-006): ALWAYS SHALL the number of concurrent subprocesses not exceed the configured parallelism.
- `REQ-003` (AC-007): ALWAYS SHALL completed trial results persist to disk before the next trial begins.
- `REQ-004` (AC-001): WHEN the user invokes `run` THEN SHALL the framework iterate every model × test case × trial combination.
- `REQ-005` (AC-006): WHEN a trial exceeds the configured timeout THEN SHALL the subprocess **and its entire descendant process group** be killed and the trial recorded as TIMEOUT. <!-- updated 2026-05-21 (quickfix-2026-05-21T15-03-46) -->
- `REQ-006` (AC-007): WHEN the framework starts and finds an existing `results.json` THEN SHALL it load the file and skip all cells with a terminal status.
- `REQ-007`: WHEN a subprocess returns a non-zero exit code THEN SHALL the trial be recorded as ERROR unless a verification marker overrides it.
- `REQ-008` (AC-003): WHERE a trial is in TIMEOUT or ERROR state THEN SHALL the partial LLM history file on disk still be referenced in the result.
- `REQ-009` (AC-002): WHERE a trial completed with a valid output THEN SHALL the test case's validator be invoked with the output directory and log content.
- `REQ-010` (AC-006): AS parallelism is greater than 1 THEN SHALL trials be dispatched across concurrent async tasks gated by a semaphore.
- `REQ-011` (AC-002): AS a validator raises an exception THEN SHALL the trial be recorded as ERROR with the exception message in details.
- `REQ-012` (AC-004): AS `--cli-name` is provided THEN SHALL the runner invoke that binary instead of `zrb`.
- `REQ-013` (AC-002): UNLESS a test case directory contains a valid validator module THEN SHALL the runner reject that test case with a clear error message.
- `REQ-014` (AC-001): UNLESS all required arguments (models, test-cases, trials) are provided THEN SHALL the CLI print usage and exit non-zero.
- `REQ-015` (AC-001): The runner SHALL accept models in `provider:model_name` format (e.g., `openai:gpt-4o`).
- `REQ-016` (AC-003): The runner SHALL set `{env_prefix}_LLM_HISTORY_DIR` and `{env_prefix}_LLM_JOURNAL_DIR` (where `env_prefix` is the configured env-var prefix on `ExperimentConfig`, default `ZRB`) to per-cell sibling directories of `workdir/`, and SHALL pass `--session` to each `zrb chat` invocation, so that conversation history and journal notes are isolated per trial. <!-- updated 2026-05-24 (quickfix-2026-05-24T23-45-24); merged with env_prefix support from feat/override-env -->
- `REQ-017` (AC-005): The runner SHALL write each completed `TrialResult` to `results.json` immediately upon finishing.
- `REQ-018` (AC-001): The runner SHALL create a per-cell output directory: `{output_dir}/{model_safe}/{test_case}/trial-{N}/`.
- `REQ-019`: The runner SHALL parse the zrb `💸` usage summary line from subprocess stdout — matching the actual zrb format `💸 (Requests: … | Tool Calls: … | Total: T) Input: I | Audio Input: … | Output: O | Audio Output: … | Cache Read: C | …` — and populate `total_tokens`, `input_tokens`, `output_tokens`, and `cache_read_tokens` in `TrialResult`. WHERE multiple summary lines appear, ONLY the LAST one SHALL be used (zrb's per-run totals are already cumulative across turns; summing would double-count). <!-- updated 2026-05-24 (quickfix-2026-05-24T23-45-24) -->
- `REQ-020` (AC-008): ALWAYS SHALL the trial subprocess `cwd` be a nested `workdir/` directory inside the per-trial cell directory — never the cell directory itself.
- `REQ-021` (AC-008): ALWAYS SHALL the trial's `stdout.log`, `history/` directory, `notes/` directory, and any other evaluation artifacts live as siblings of `workdir/` and not inside it.
- `REQ-022` (AC-009): WHEN a test case has no dedicated `workdir/` source to stage THEN SHALL the runner create an empty `workdir/` directory inside the trial cell before launching the subprocess.
- `REQ-023` (AC-008): The runner SHALL stage the test case's `workdir/` contents into the trial's nested `workdir/` directory, never into the cell directory itself.
- `REQ-024` (AC-008): The runner SHALL ensure that `validator.py`, `instruction.txt`, and any other test-case metadata files are never copied into the trial's `workdir/`.
- `REQ-025` (AC-010): ALWAYS SHALL trial rows in `report.md` be sorted by `model` ascending, then `test_case` ascending, then `trial_index` ascending.
- `REQ-026` (AC-011): ALWAYS SHALL the best-metric bolding scope be one test case (spanning all models and all trials in that test case), and ALWAYS SHALL trials with status `FAIL`, `TIMEOUT`, or `ERROR` be excluded from the best-metric computation.
- `REQ-027` (AC-012): ALWAYS SHALL `report.md` use pure Markdown syntax — no embedded HTML — for sort order, bolding, and status icons.
- `REQ-028` (AC-011): WHERE a trial with status `PASS` or `EXCELLENT` ties or sets the best value within its test case for any of (`duration` min, `score` max, `total_tokens` min, `tool_call_count` min) THEN SHALL the corresponding metric cell in `report.md` be wrapped in Markdown bold (`**…**`).
- `REQ-029` (AC-012): AS a trial's status is rendered in `report.md` THEN SHALL the status text be prefixed with the icon mapping: `EXCELLENT` → 👍, `PASS` → ✅, `FAIL` → ❌, `TIMEOUT` → ⏱️, `ERROR` → ⚠️.
- `REQ-030`: ALWAYS SHALL the `Experiment.id` and `started_at` be preserved across resumed invocations, even though the persisted `config` is replaced by the current CLI invocation (CLI args are authoritative). <!-- added 2026-05-25 (sdlc-document drift-report-2026-05-25T01-05-34) -->
- `REQ-031`: WHEN a trial cell directory already exists at the start of a trial THEN SHALL the runner wipe it via `shutil.rmtree` before recreating it, so a retry of an interrupted cell starts from a pristine staged workdir. <!-- added 2026-05-25 (sdlc-document drift-report-2026-05-25T01-05-34) -->
- `REQ-032`: WHEN the user invokes `zrb-llm-evaluator list --dir DIR` THEN SHALL the CLI read `DIR/results.json` and print a tabular summary (model, test_case, trial_index, status, duration) for every persisted trial, exiting non-zero if the file is absent. <!-- added 2026-05-25 (sdlc-document drift-report-2026-05-25T01-05-34) -->
- `REQ-033`: WHEN the user invokes `zrb-llm-evaluator report --dir DIR` THEN SHALL the CLI re-render `report.md` from `DIR/experiment.json` without re-running any trials, exiting non-zero if `experiment.json` is absent. <!-- added 2026-05-25 (sdlc-document drift-report-2026-05-25T01-05-34) -->
- `REQ-034`: AS multiple test case directories are loaded, IF one or more are invalid, THEN SHALL `load_test_cases` aggregate every error into a single `ValueError` rather than failing on the first, so the user sees all problems at once. <!-- added 2026-05-25 (sdlc-document drift-report-2026-05-25T01-05-34) -->

## Non-Functional Requirements

| ID | Requirement | Target | Validated By |
|----|-------------|--------|--------------|
| NFR-001 | Per-trial overhead (setup + parsing + validation) shall not exceed 2 seconds when no LLM call is made | < 2s | test (benchmark) |
| NFR-002 | The runner shall handle at least 100 model × test case cells without OOM | 100 cells | test (stress) |

## NFRs Validated Outside Code

None.

## API Surface

The primary interface is a CLI with subcommands:

| Method | Path | Request | Response | Auth |
|--------|------|---------|----------|------|
| CLI | `zrb-llm-evaluator run` | `--models`, `--test-cases`, `--trials`, `--parallelism`, `--timeout`, `--cli-name`, `--env-prefix`, `--output-dir` | stdout progress + filesystem results | None |
| CLI | `zrb-llm-evaluator list [dir]` | `--dir` (optional, default CWD) | Table of previously-run experiments | None |
| CLI | `zrb-llm-evaluator report [dir]` | `--dir` (optional, default CWD) | Re-generated report to stdout | None |

## Error Handling

| Condition | Status | Body |
|-----------|--------|------|
| Test case validator not found or invalid (`INVALID_CASE`) | Runner exits non-zero before any trial | User fixes validator module |
| zrb chat subprocess not found (`CLI_NOT_FOUND`) | Trial: ERROR, continue to next cell | User installs zrb or corrects --cli-name |
| Subprocess timeout (`TIMEOUT`) | Trial: TIMEOUT, partial log preserved; the entire descendant process group is killed via `os.killpg(SIGKILL)` so `zrb chat` workers cannot outlive the timeout (REQ-005) | Retry with higher timeout |
| Subprocess non-zero exit (`EXIT_ERROR`) | Trial: ERROR (unless overridden by verification marker) | Debug via preserved log |
| Validator raised exception (`VALIDATOR_ERROR`) | Trial: ERROR with exception message | Fix validator, resume |
| results.json write failure (`WRITE_ERROR`) | Runner exits with partial results | Fix filesystem, resume (skips completed cells) |
| Ctrl+C / SIGINT | In-progress trials are killed; results.json is consistent (mid-write cell may be partial) | Resume skips completed cells, retries in-progress ones |

## Correctness

### Round-Trip
All result models (`TrialResult`, `ValidationResult`, `ValidationCheck`) are Pydantic v2 models. Serialization uses `.model_dump(mode="json")`; deserialization uses `.model_validate()`. The `results.json` file is a list of `TrialResult` dicts. Token fields default to 0 when absent (timeout/aborted runs). The uuid field ensures every result round-trips to a unique identity.

### Uniqueness
Each trial cell is identified by the triple `(model, test_case, trial_index)`. This triple must be unique within an experiment. The output directory hierarchy enforces this: `{output_dir}/{model_safe}/{test_case}/trial-{N}` maps exactly to one cell. On resume, cells are deduplicated by this triple using a dictionary key.

### Atomicity
Each trial result is appended to `results.json` atomically: write to a temp file, then `os.rename()` — which is atomic on the same filesystem. If the process crashes mid-trial, the partial `results.json` (missing only the in-flight trial) is valid JSON. Unused cell directories from interrupted trials are removed and recreated on retry — including their nested `workdir/` — so the retry starts from a pristine staged workdir rather than overlaying onto stale LLM artifacts.

### Validation
`ExperimentConfig` is a Pydantic model validated at CLI entry:
- `models`: list of strings matching `provider:name` pattern, min 1
- `test_case_dirs`: existing directory paths, min 1
- `trials`: int >= 1
- `parallelism`: int >= 1
- `timeout`: int >= 30
- `cli_name`: non-empty string
- `env_prefix`: non-empty string, default `"ZRB"`

Test case modules are dynamically imported and checked against `ValidatorProtocol` at load time. A test case that fails protocol conformance is rejected with a clear error before any trial begins.

### Idempotency
The runner is idempotent when pointed at an existing output directory. On startup, it loads `results.json` and skips any cell whose triple `(model, test_case, trial_index)` already has a terminal status (EXCELLENT/PASS/FAIL/TIMEOUT/ERROR). Re-running the same command produces the same results without duplication. Non-terminal cells (from a prior interrupted run) are retried.

## Per-Trial Filesystem Layout

Each trial cell uses this layout to keep evaluation artifacts out of the
LLM's view (per ADR-7):

```
{output_dir}/{model_safe}/{test_case}/trial-{N}/
├── workdir/         ← subprocess cwd (LLM-visible)
│   └── (staged test-case workdir files only)
├── stdout.log       ← LLM-invisible (sibling of workdir)
├── history/         ← LLM-invisible (sibling of workdir)
│   └── {session_name}.json
└── notes/           ← LLM-invisible (sibling of workdir)
    └── (journal/activity-log entries written by the LLM)
```

Invariants enforced by REQ-020 / REQ-021 / REQ-022 / REQ-023 / REQ-024:
- The subprocess `cwd` is always `trial-{N}/workdir/`, even when the test
  case has no files to stage (an empty `workdir/` is created).
- `stdout.log`, `history/`, `experiment.json`, and any future evaluation
  artifacts are siblings of `workdir/`, never children.
- Test-case metadata (`validator.py`, `instruction.txt`) is never copied
  into `workdir/`. Only the test case's own `workdir/` contents are staged.

`..` traversal from inside `workdir/` reaches the evaluation files —
this is accepted per ADR-7's threat model (honest LLM, not adversarial).

The `{env_prefix}_LLM_HISTORY_DIR` env var (default `ZRB_LLM_HISTORY_DIR`)
is set to the trial's `history/` directory (a sibling of `workdir/`), so
zrb writes the conversation history outside the LLM's `cwd`. Similarly,
`{env_prefix}_LLM_JOURNAL_DIR` (default `ZRB_LLM_JOURNAL_DIR`) is set to
the trial's `notes/` directory (a sibling of `workdir/`), so
journal/activity-log entries written by the LLM during the experiment are
captured per-trial and never leak into the user's real `~/.zrb/llm-notes/`.
The env prefix is configurable via `--env-prefix` (default `"ZRB"`),
supporting white-label zrb forks with a different `ENV_PREFIX`.

## Report Rendering (per ADR-8)

`MarkdownReporter` builds `report.md` from the in-memory list of `TrialResult` after the experiment completes (or on demand via `zrb-llm-evaluator report`):

1. **Sort** — Sort trials by `(model, test_case, trial_index)` ascending. The sort is stable; deterministic input produces a byte-identical report.
2. **Bold-best computation** — For each test case, filter the trials whose status is `PASS` or `EXCELLENT`. Within that filtered group compute four extrema: `min(duration)`, `max(score)`, `min(total_tokens)`, `min(tool_call_count)`. For each trial row, the cell rendering a metric whose value equals the corresponding extremum (within that test case's filtered group) is wrapped in `**…**`. Ties produce multiple bold cells. Trials excluded from the filter never receive bold formatting.
3. **Status icon** — Each rendered status cell is the concatenation of the icon for that status plus a space plus the status name (e.g. `✅ PASS`). Mapping is fixed: `EXCELLENT`→👍, `PASS`→✅, `FAIL`→❌, `TIMEOUT`→⏱️, `ERROR`→⚠️.
4. **Output format** — Pure Markdown only. No `<b>`, `<span>`, or other HTML. Emoji are inserted as literal Unicode codepoints.

Determinism: given the same `results.json`, repeated runs of `MarkdownReporter` produce byte-identical `report.md`.

## Entities

See `.sdlc/requirements/entity-dictionary.md`. Fields this feature reads/writes:

| Entity | Fields Used | Notes |
|--------|-------------|-------|
| ExperimentConfig | models, test_case_dirs, trials, parallelism, timeout, cli_name, env_prefix | Input to the runner; env_prefix controls the `{prefix}_LLM_*` env var names |
| TestCase | name, instruction, workdir, validator | Discovered from disk per test case directory |
| TrialResult | model, test_case, trial_index, status, duration, tool_calls, tool_call_count, exit_code, log_path, stdout_log_path, verification_result, total_tokens, input_tokens, output_tokens, cache_read_tokens | Written to results.json after each cell |
| Experiment | id, config, results, started_at, completed_at | Envelope persisted as experiment.json; id + started_at survive across resumed invocations |
| ValidationResult | status, score, details | Returned by the validator protocol |
| ValidationCheck | name, passed, message | Per-check breakdown within ValidationResult |
| Report | experiment_id, markdown_path, json_path, generated_at | Manifest returned by report generators; describes the artifacts they produced |

### Entity Modifications
- `TrialResult.stdout_log_path` is added so the result references both the zrb history JSON (`log_path`) and the raw subprocess stdout/stderr log (`stdout_log_path`, written to `stdout.log`).
- `TrialResult.tool_calls` (list of tool names) and `TrialResult.tool_call_count` are added so the report can summarize tool usage per cell.
- `Experiment` envelopes the run (config + results + timing) and is persisted as `experiment.json` alongside the per-trial-streamed `results.json`.
- `Report` is the return type of `generate_markdown_report` / `generate_json_report`; it carries the experiment id and the paths of the artifacts produced.

---
*Merged from `requirements.md` + `design.md` into the single-file spec format on 2026-06-04. Originally documented from code at 2026-05-25T01-05-34. Scope: experiment-runner. Source commit: 5eaf52d.*
