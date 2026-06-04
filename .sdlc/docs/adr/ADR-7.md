# ADR-7: Trial Subprocess Isolation via Nested Workdir

## Status
Accepted

## Context
Each trial invokes `zrb chat` as a subprocess with `cwd` set to the trial's
directory. The current layout (`{output_dir}/{model_safe}/{test_case}/trial-{N}/`)
also holds the trial's `stdout.log` and `history/` directory in that same
directory. The LLM under test can read files in its `cwd` — meaning it can
inspect its own captured stdout log, the conversation history file, the
test case's `validator.py` (if a test-case directory was used as the
workdir source), and any other evaluation artifacts.

This contaminates the experiment in three ways:
1. The LLM can read instructions to itself in the conversation history.
2. The LLM can read the validator and target its checks ("cheating").
3. The LLM can read prior trials' partial outputs left in sibling cells.

ADR-6 mentioned a `workdir/` subdirectory but framed it as post-mortem
storage; it did not require isolation. US-008 / AC-008 / AC-009 (added
in the requirements update on 2026-05-20) make isolation a hard requirement.

## Decision
The per-trial layout is canonicalized as:

```
{output_dir}/{model_safe}/{test_case}/trial-{N}/
├── workdir/         ← subprocess cwd; LLM-visible
│   └── (staged test-case files only)
├── stdout.log       ← LLM-invisible (sibling of workdir)
└── history/         ← LLM-invisible (sibling of workdir)
    └── {session_name}.json
```

Invariants:
- The subprocess `cwd` is **always** `trial-{N}/workdir/`, even when the
  test case has no files to stage (in which case `workdir/` is created
  empty before subprocess launch).
- `stdout.log`, `history/`, and any future evaluation artifacts MUST live
  as siblings of `workdir/`, never inside it.
- `..` traversal from `workdir/` reaches the evaluation files. This is
  accepted: the threat model is an LLM that reads relative paths the test
  case mentions, not a malicious agent that probes parent directories.
  Test cases SHOULD NOT instruct the LLM to read files via `../`.

## Consequences
### Positive
- LLM cannot inadvertently read its own stdout log or conversation history.
- LLM cannot read the test case's `validator.py` (it lives in the test-case
  source directory, never staged into `workdir/`).
- Uniform `cwd` behavior — no special case for "test case has no workdir".

### Negative
- One extra directory level per trial; paths in logs grow slightly longer.
- `..` traversal is still possible. A future ADR could harden this by
  running the subprocess in a chroot/container, but that is out of scope.

## Implements Rules
- None directly — satisfies US-008 / AC-008 / AC-009.

## Verification
- Unit test: assert `asyncio.create_subprocess_exec` is called with `cwd`
  ending in `/workdir`, regardless of whether the test case had files to stage.
- Unit test: after a trial completes, `(trial_dir / "stdout.log").exists()`
  is True AND `(trial_dir / "workdir" / "stdout.log").exists()` is False.
- Code review: `validator.py` and `instruction.txt` never appear under
  any `workdir/` in the output tree.

## References
- ADR-6 (per-cell filesystem layout — refined by this ADR)
- US-008 / AC-008 / AC-009 in `.sdlc/requirements/problem-brief.md`
