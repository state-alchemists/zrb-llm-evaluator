# zrb-llm-evaluator

Multi-trial experiment runner for testing LLMs against structured test cases via `zrb chat`.

Given a set of models and test cases, it runs every combination across N trials, collects structured results, and generates reports. Supports concurrent execution, timeout handling, resume from partial runs, and pluggable validators.

## Quick Start

```bash
# Install
poetry install

# Create a test case directory
mkdir -p my-cases/hello-world
cat > my-cases/hello-world/instruction.txt << 'EOF'
Write a Python function that returns "hello, world".
EOF

# Run an experiment (requires zrb installed and configured)
zrb-llm-evaluator run \
  --models openai:gpt-4o \
  --test-cases ./my-cases/hello-world/ \
  --trials 1
```

## Features

- Runs N models × M test cases × T trials as a flat experiment grid
- Concurrent trial execution with configurable parallelism (asyncio + semaphore)
- Per-trial timeout kills subprocess and preserves partial output
- Resume support: re-run with the same output directory to skip completed cells
- Pluggable validators: each test case provides a `validator.py` implementing a typed protocol
- Atomic `results.json` writes (temp file + `os.rename`)
- Pluggable CLI adapters: built-in support for `zrb`, `claude-code`, and `opencode`, or bring your own via a dotted import path
- Custom CLI binary name for white-labeled forks

## Installation

**Prerequisites:** Python ≥ 3.11, [Poetry](https://python-poetry.org/), and an installed `zrb` CLI with API keys configured.

```bash
git clone <repo>
cd zrb-llm-evaluator
poetry install
```

Verify the CLI works:

```bash
poetry run zrb-llm-evaluator --help
```

## Usage

### Test Case Format

Each test case is a directory containing:

```
my-cases/<test-name>/
├── instruction.txt    # Required — the prompt sent to the LLM
├── validator.py       # Required — validation logic (see below)
└── workdir/           # Optional — files copied into the trial's working directory
```

### Writing a Validator

`validator.py` must expose a top-level `validator` object that implements `ValidatorProtocol`:

```python
# my-cases/hello-world/validator.py
from pathlib import Path
from zrb_llm_evaluator.models import TrialTrace, ValidationResult, ValidationCheck
from zrb_llm_evaluator.protocols import ValidatorProtocol

class HelloValidator:
    def validate(
        self,
        output_dir: Path,
        log_content: str,
        trace: TrialTrace | None = None,
    ) -> ValidationResult:
        passed = "hello, world" in log_content.lower()
        return ValidationResult(
            status="PASS" if passed else "FAIL",
            score=1.0 if passed else 0.0,
            details=[
                ValidationCheck(
                    name="contains_greeting",
                    passed=passed,
                    message="Output contains 'hello, world'" if passed
                            else "Missing expected greeting",
                )
            ],
        )

validator = HelloValidator()
```

The framework validates protocol conformance at load time. `validator.py` that doesn't implement `ValidatorProtocol` is rejected before any trial runs.

The `trace` parameter is a `TrialTrace` parsed from the per-trial session history. It exposes:

- `tool_calls: list[ToolCallRecord]` — every tool invocation with `name` and `args` dict
- `tool_names: list[str]` — convenience list of just the names, in order
- `assistant_text: str` — concatenated assistant message text
- `turn_count: int`

Use it to assert *how* the agent succeeded (e.g., "called the right tool", "iterated at least twice", "never invoked an HTTP tool with secret values") rather than only the final filesystem state. Validators that don't need trajectory data can ignore the parameter.

The reporter aggregates trials across `(model, test_case)` cells and surfaces a **Stability** section: a cell with mixed pass/fail across trials is flagged 🟡 FLAKY — a one-off lucky pass is no longer indistinguishable from a deterministic pass. This section is suppressed when every cell has a single trial (stability is undefined with N=1).

### ValidationResult

| Field | Type | Description |
|-------|------|-------------|
| `status` | `"EXCELLENT" \| "PASS" \| "FAIL"` | Overall outcome |
| `score` | `float` (0.0–1.0) | Normalized score |
| `details` | `list[ValidationCheck]` | Per-check breakdown |

## CLI Reference

### `run`

Run a full experiment.

```
zrb-llm-evaluator run \
  --models openai:gpt-4o,google-gla:gemini-2.5-flash \
  --test-cases ./cases/bug-fix,./cases/copywriting \
  --trials 3 \
  --parallelism 4 \
  --timeout 300 \
  --cli-name zrb \
  --output-dir ./out
```

| Option | Default | Description |
|--------|---------|-------------|
| `--models` | required | Comma-separated list in `provider:name` format |
| `--test-cases` | required | Comma-separated list of test case directory paths |
| `--trials` | `3` | Trials per model × test case cell |
| `--parallelism` | `4` | Max concurrent subprocesses |
| `--timeout` | `300` | Per-trial timeout in seconds |
| `--cli-name` | template's own binary | CLI binary to invoke (e.g. `zrb`, `claude`, `opencode`) |
| `--cli-template` | `zrb` | Which `CliAdapter` to use: `zrb`, `claude-code`, `opencode`, or a dotted import path to a custom adapter class |
| `--env-prefix` | `ZRB` | Env var prefix for the `zrb` adapter's history/journal dirs (`{prefix}_LLM_*`) |
| `--honor-verification-marker` | off | Let a `VERIFICATION_RESULT:` line in the agent's own stdout override the validator verdict. Off by default — letting the agent under test grade itself is opt-in |
| `--output-dir` | `./out` | Output directory for results |

Output: `results.json` (structured) + `report.md` (human-readable).

### `list`

List completed trials from a previous experiment.

```
zrb-llm-evaluator list --dir ./out
```

### `report`

Re-generate the Markdown report from existing `results.json`.

```
zrb-llm-evaluator report --dir ./out
```

## Architecture

The runner has four layers:

1. **CLI** (`cli.py`) — Typer entry point, parses args, validates config
2. **Loader** (`loader.py`) — Discovers test cases from directories, imports validators, checks protocol conformance
3. **Runner** (`runner.py`) — Async subprocess orchestration with `asyncio.Semaphore`, `asyncio.wait_for`, and `ResumeManager` for idempotent resumption. Each trial creates an isolated directory `{output}/{model_safe}/{test_case}/trial-{N}/` (colons in the model name are sanitized) with its own history directory
4. **Reporter** (`reporter.py`) — Generates Markdown and JSON output with atomic file writes

Key design decisions are documented in `.sdlc/docs/adr/`.

### CLI Adapters

`--cli-template` selects a `CliAdapter` (`cli_adapters.py`) that owns every CLI-specific decision — the subprocess command line, env vars, and how usage/tool calls are parsed from output. The runner itself never hardcodes a particular CLI's invocation.

| Template | Invokes | Usage parsed from |
|----------|---------|--------------------|
| `zrb` (default) | `zrb chat --interactive false --yolo true ...` | `💸` stdout summary line |
| `claude-code` | `claude -p ... --output-format stream-json --dangerously-skip-permissions` | `usage` block of the final `result` event |
| `opencode` | `opencode run ... --format json --dangerously-skip-permissions` | summed `step_finish` events (NDJSON) |
| custom | your adapter's `build_argv` | your adapter's `parse_usage` |

For a custom CLI, pass a dotted import path (e.g. `--cli-template mypkg.MyAdapter`) to a class implementing the `CliAdapter` protocol in `protocols.py`. Unresolvable templates fail fast before any trial runs.

## Output Structure

```
./out/
├── results.json          # Structured results (list of TrialResult)
├── report.md             # Human-readable report
├── openai_gpt-4o/
│   └── bug-fix/
│       ├── trial-1/
│       │   ├── stdout.log            # Raw subprocess stdout/stderr
│       │   └── history/              # ZRB_LLM_HISTORY_DIR
│       │       └── <session>.json
│       ├── trial-2/
│       └── trial-3/
└── google-gla_gemini-2.5-flash/
    └── ...
```

## Development

```bash
poetry install --with dev
poetry run pytest tests/experiment-runner/
poetry run ruff check
poetry run mypy src/
```

## License

MIT.
