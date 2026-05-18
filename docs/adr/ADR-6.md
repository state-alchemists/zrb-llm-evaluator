# ADR-6: Filesystem-Based Experiment State with JSON Resume

## Status
Accepted

## Context
Experiments may run for hours across many cells (N models × M cases × T trials). If the process is interrupted (network issue, Ctrl+C), the user should not lose completed work. The existing zrb runner handles this by loading `results.json` at startup and skipping terminal-status entries. This pattern works and should be preserved.

## Decision
Experiment state is stored entirely on the filesystem. One output directory per experiment containing:
- `results.json` — accumulated list of `TrialResult` objects, atomically rewritten after each cell completes
- `report.md` — regenerated from `results.json` at the end
- Per-cell directories: `{output_dir}/{model_safe}/{test_case}/` each containing:
  - `{session_name}.json` — the LLM conversation history saved by zrb's `FileHistoryManager` (see ADR-3)
  - `workdir/` — the trial's working directory (preserved for post-mortem)
  - `stdout.log` — captured subprocess stdout (for cost-summary parsing)

On startup, if `results.json` exists, it is loaded and cells with terminal status are skipped.

## Consequences
### Positive
- No database needed — pure filesystem persistence
- Resume is trivial: load JSON, skip completed cells
- Every trial's working directory is preserved for debugging

### Negative
- Not suitable for multi-user concurrent experiments (directory conflicts)
- Results directory can grow large (each trial keeps a full workdir copy)

## Implements Rules
- None directly — satisfies AC-007 (resume) and AC-005 (structured report)

## Verification
- After each cell completes, `results.json` is atomically rewritten
- On restart with the same output directory, the runner loads `results.json` and skips terminal-status cells
- Unit test: run 2 cells, simulate interrupt, restart, verify cell 2 is executed but cell 1 is skipped

## References
- Existing runner: `llm-challenges/runner.py` (load/resume logic and per-cell directory layout)
