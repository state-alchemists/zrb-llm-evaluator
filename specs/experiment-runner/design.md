# Design: experiment-runner

## Correctness Properties

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

## API Surface

The primary interface is a CLI with subcommands:

| Method | Path | Request | Response | Auth |
|--------|------|---------|----------|------|
| CLI | `zrb-llm-evaluator run` | `--models`, `--test-cases`, `--trials`, `--parallelism`, `--timeout`, `--cli-name`, `--env-prefix`, `--output-dir` | stdout progress + filesystem results | None |
| CLI | `zrb-llm-evaluator list [dir]` | `--dir` (optional, default CWD) | Table of previously-run experiments | None |
| CLI | `zrb-llm-evaluator report [dir]` | `--dir` (optional, default CWD) | Re-generated report to stdout | None |

## Error Handling

| Error | Code | Status | Recovery |
|-------|------|--------|----------|
| Test case validator not found or invalid | `INVALID_CASE` | Runner exits non-zero before any trial | User fixes validator module |
| zrb chat subprocess not found | `CLI_NOT_FOUND` | Trial: ERROR, continue to next cell | User installs zrb or corrects --cli-name |
| Subprocess timeout | `TIMEOUT` | Trial: TIMEOUT, partial log preserved; the entire descendant process group is killed via `os.killpg(SIGKILL)` so `zrb chat` workers cannot outlive the timeout (REQ-005) | Retry with higher timeout |
| Subprocess non-zero exit | `EXIT_ERROR` | Trial: ERROR (unless overridden by verification marker) | Debug via preserved log |
| Validator raised exception | `VALIDATOR_ERROR` | Trial: ERROR with exception message | Fix validator, resume |
| results.json write failure | `WRITE_ERROR` | Runner exits with partial results | Fix filesystem, resume (skips completed cells) |
| Ctrl+C / SIGINT | — | In-progress trials are killed; results.json is consistent (mid-write cell may be partial) | Resume skips completed cells, retries in-progress ones |

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

## Data Model

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
*Documented from code at 2026-05-25T01-05-34. Scope: experiment-runner. Source commit: 5eaf52d.*
