# Design: evaluator

> Correctness properties reverse-engineered from code at commit `8a52af8`.

## Round-Trip (Serialization Symmetry)

**Enforced.** All structured results (`TrialResult`, `ValidationResult`, `Experiment`, `ExperimentConfig`, `Report`) are Pydantic v2 models. `model_dump(mode="json")` produces JSON-compatible dicts that `model_validate()` can restore. The test suite explicitly validates round-trip fidelity (`test_round_trip_serialization` in `test_models.py`).

**Verified by:** UT-022, IT-001, IT-002.

## Uniqueness

**Partially enforced.**

- **Session names:** `make_session_name()` combines model-safe-name + test-case-name + trial-index, producing distinct session names per cell. Verified by UT-001.
- **Trial result identities:** Each `TrialResult` gets a random UUID `id`. No dedup logic on re-load — duplicate entries from interrupted resume are prevented by `ResumeManager.is_completed()` filtering, not by uniqueness enforcement.
- **Experiment identity:** Each `Experiment` gets a random UUID `id`. On resume, the existing id is preserved, not a new one generated.
- **No DB-level uniqueness constraint since all persistence is file-based.**

## Atomicity

**Enforced at file level.** Three critical write paths all use the same atomic pattern:

1. `ResumeManager._flush()` — writes `results.json` via tempfile + `os.replace` (`runner.py:163-174`).
2. `generate_json_report()` — writes experiment JSON via tempfile + `os.replace` (`reporter.py:398-411`).
3. `_persist_experiment()` — writes `experiment.json` via tempfile + `os.replace` (`runner.py:632-648`).

**Not enforced at subprocess level.** A trial interrupted mid-execution (before `ResumeManager.append()` is called) loses its partial output — the cell directory is cleaned and re-created on retry (`shutil.rmtree(cell_dir)` in `TrialRunner.run()`). This is acceptable since the trial has no side effects outside its cell directory.

## Validation

**Enforced at multiple layers:**

1. **CLI layer (`cli.py:58-69`):** `ExperimentConfig` construction validates model format, field ranges.
2. **Config layer (`models.py:101-110`):** Pydantic field validators enforce:
   - `models`: min_length=1, each entry must be `provider:name` format
   - `test_case_dirs`: min_length=1
   - `trials`: ge=1
   - `parallelism`: ge=1
   - `timeout`: ge=30
3. **Test case loading layer (`loader.py`):**
   - Missing `instruction.txt` raises `ValueError`
   - Missing `validator.py` raises `ValueError`
   - Validator module without `validator` attribute raises `ValueError`
   - Validator not implementing `ValidatorProtocol` raises `ValueError`
   - Batch loading aggregates all errors before raising
4. **Runtime validation in runner:**
   - `_extract_verification_marker()` validates marker values against allowed set (`EXCELLENT`, `PASS`, `FAIL`).
   - Validator exceptions are caught and produce structured error results.

**Not enforced:** No schema validation on subprocess output (stdout parsing uses regex with defaults). No validation that the CLI binary (`cli_name`) actually exists before trial execution.

## Idempotency

**Enforced for re-runs (resume).** `ResumeManager.is_completed()` checks each cell against persisted terminal-status results before scheduling. Re-running the same experiment against the same output directory skips all completed cells and preserves the experiment identity.

**Not enforced at trial level.** Re-running a partially-complete experiment where some cell directories exist but no `results.json` entry was appended will wipe and re-execute those cells (cell directory cleanup via `shutil.rmtree`). This is safe — no persistent side effects outside the cell directory.

## Defensive Design

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

**Gaps:** *(all 5 gaps from the initial assessment resolved by quickfix `quickfix-2026-05-27T06-26-31.md`)*
- ~~No explicit test for the `--env-prefix` customization path.~~ ✅ UT-048
- ~~No test for config validation's `--cli-name` empty-string path (Pydantic `min_length=1`).~~ ✅ UT-049
- ~~No test for the `report` CLI subcommand's error path when `experiment.json` is corrupt.~~ ✅ UT-050
- ~~No test for `_load_or_init_experiment` with corrupt JSON.~~ ✅ UT-051
- ~~No test for concurrent write safety on `results.json` (multiple trials appending near-simultaneously).~~ ✅ UT-052

---
*Documented from code at 2026-05-27T06-16-43. Scope: evaluator module (src/zrb_llm_evaluator/ + tests/experiment-runner/). Source commit: 8a52af8.*
