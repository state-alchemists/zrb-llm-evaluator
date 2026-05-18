# ADR-1: CLI Framework — Typer

## Status
Accepted

## Context
The framework needs a CLI with subcommands (`run`, `list`, `report`) and configurable options (`--models`, `--trials`, `--parallelism`, `--timeout`, `--cli-name`). The existing zrb runner uses `argparse` which is verbose for nested subcommands and does not compose well with OOP patterns. White-label forks need to register custom CLI entry points.

## Decision
Use **Typer** (built on Click) for the CLI layer. Typer's decorator-based approach maps well to OOP classes (RULE-001), auto-generates `--help`, and supports subcommands natively. The CLI entry point is a function that a white-label fork can re-export under a different binary name.

## Consequences
### Positive
- Minimal boilerplate for subcommands and option parsing
- Type annotations map to CLI help automatically (RULE-002)
- Easy for forks to rebrand by importing and re-wrapping the same app

### Negative
- Additional dependency vs argparse's stdlib availability
- Typer v0.x API differences across minor versions (pin the version)

## Implements Rules
- RULE-001 — OOP-first: Typer works naturally with class-based command groups
- RULE-002 — Type annotations: Typer uses type hints for CLI option parsing
- RULE-012 — Async: Typer supports async commands natively

## Verification
- All CLI subcommands are defined via `@app.command()` with typed parameters
- The app object is importable and re-exportable from a public module

## References
- https://typer.tiangolo.com/
