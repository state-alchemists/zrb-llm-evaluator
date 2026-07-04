# GENERATED FROM SPEC: .sdlc/specs/experiment-runner/spec.md
# IMPLEMENTS: EXPERIMENT-RUNNER:REQ-004, EXPERIMENT-RUNNER:REQ-014, EXPERIMENT-RUNNER:REQ-015,
# IMPLEMENTS: EXPERIMENT-RUNNER:REQ-016, EXPERIMENT-RUNNER:REQ-032, EXPERIMENT-RUNNER:REQ-033,
# IMPLEMENTS: RULE-011, RULE-012
# IMPLEMENTS: EXPERIMENT-RUNNER:REQ-035, EXPERIMENT-RUNNER:REQ-038

"""Typer CLI entry point for the experiment runner."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import typer

from zrb_llm_evaluator.cli_adapters import resolve_cli_adapter
from zrb_llm_evaluator.loader import load_test_cases
from zrb_llm_evaluator.models import ExperimentConfig
from zrb_llm_evaluator.reporter import generate_json_report, generate_markdown_report
from zrb_llm_evaluator.runner import run_experiment

app = typer.Typer(
    name="zrb-llm-evaluator",
    help="Multi-trial experiment runner for zrb chat",
)


def _get_cli_version(cli_name: str) -> str:
    """Return the version string for ``cli_name``, or '' on failure.

    Tries the conventional ``--version`` flag first, then zrb's ``version``
    subcommand, accepting the first invocation that exits 0 with output.
    """
    for version_args in (["--version"], ["version"]):
        try:
            result = subprocess.run(
                [cli_name, *version_args],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception:
            return ""
        if result.returncode == 0:
            output = result.stdout.strip() or result.stderr.strip()
            if output:
                return output
    return ""


def _setup_logging() -> None:
    """Configure stderr progress logging for the runner package."""
    pkg_logger = logging.getLogger("zrb_llm_evaluator")
    if pkg_logger.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S"),
    )
    pkg_logger.addHandler(handler)
    pkg_logger.setLevel(logging.INFO)


# @sdlc EXPERIMENT-RUNNER:REQ-004, EXPERIMENT-RUNNER:REQ-014, EXPERIMENT-RUNNER:REQ-015,
# @sdlc EXPERIMENT-RUNNER:REQ-016, EXPERIMENT-RUNNER:REQ-035, EXPERIMENT-RUNNER:REQ-038
@app.command()
def run(
    models: str = typer.Option(
        ...,
        "--models",
        help="Comma-separated list of models (provider:name format)",
    ),
    test_cases: str = typer.Option(
        ...,
        "--test-cases",
        help="Comma-separated list of test case directory paths",
    ),
    trials: int = typer.Option(3, "--trials", help="Number of trials per cell"),
    parallelism: int = typer.Option(
        4, "--parallelism", help="Max concurrent subprocesses",
    ),
    timeout: int = typer.Option(300, "--timeout", help="Per-trial timeout in seconds"),
    cli_name: str = typer.Option(
        "",
        "--cli-name",
        help=(
            "CLI binary name (default: the selected --cli-template's own "
            "binary, e.g. 'zrb', 'claude', 'opencode')"
        ),
    ),
    env_prefix: str = typer.Option(
        "ZRB", "--env-prefix", help="Env var prefix (default ZRB → ZRB_LLM_*)",
    ),
    cli_template: str = typer.Option(
        "zrb",
        "--cli-template",
        help=(
            "CliAdapter to use: 'zrb' (default), 'claude-code', 'opencode', "
            "or a dotted import path to a custom CliAdapter class"
        ),
    ),
    output_dir: str = typer.Option(
        "./out", "--output-dir", help="Output directory for results",
    ),
    honor_verification_marker: bool = typer.Option(
        False,
        "--honor-verification-marker",
        help=(
            "Let a 'VERIFICATION_RESULT:' line in the agent's stdout override "
            "the validator verdict. Off by default because it lets the agent "
            "under test grade itself."
        ),
    ),
) -> None:
    """Run a full experiment: N models x M test cases x T trials."""
    _setup_logging()
    # Parse models
    model_list = [m.strip() for m in models.split(",") if m.strip()]
    case_paths = [Path(p.strip()) for p in test_cases.split(",") if p.strip()]

    # @sdlc EXPERIMENT-RUNNER:REQ-035, EXPERIMENT-RUNNER:REQ-038: resolve the CliAdapter
    # before any trial begins so a bad --cli-template fails fast with a
    # clear error (INVALID_TEMPLATE), same pattern as invalid test cases
    # below. The resolved instance is reused for the whole experiment (a
    # custom adapter is constructed exactly once) and supplies the default
    # binary name when --cli-name isn't given.
    try:
        cli_adapter = resolve_cli_adapter(cli_template)
    except ValueError as exc:
        typer.echo(f"CLI template error: {exc}", err=True)
        raise typer.Exit(code=1)
    if not cli_name:
        cli_name = getattr(cli_adapter, "default_cli_name", "zrb")

    # Validate & build config
    cli_ver = _get_cli_version(cli_name)
    try:
        config = ExperimentConfig(
            models=model_list,
            test_case_dirs=case_paths,
            trials=trials,
            parallelism=parallelism,
            timeout=timeout,
            cli_name=cli_name,
            cli_version=cli_ver,
            env_prefix=env_prefix,
            cli_template=cli_template,
            honor_verification_marker=honor_verification_marker,
        )
    except Exception as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(code=1)

    # Load test cases (validates validator protocol at load time)
    resolved_dirs = [p.resolve() for p in config.test_case_dirs]
    try:
        loaded_cases = load_test_cases(resolved_dirs)
    except ValueError as exc:
        typer.echo(f"Test case error: {exc}", err=True)
        raise typer.Exit(code=1)

    out_path = Path(output_dir).resolve()
    typer.echo(
        f"Running experiment: {len(model_list)} models x "
        f"{len(loaded_cases)} cases x {trials} trials"
    )
    typer.echo(f"Output directory: {out_path}")

    # Run
    import asyncio

    experiment = asyncio.run(
        run_experiment(config, loaded_cases, out_path, cli_adapter),
    )

    # Generate reports
    experiment_path = out_path / "experiment.json"
    generate_json_report(experiment, experiment_path)
    report_path = out_path / "report.md"
    generate_markdown_report(experiment, report_path)

    results_path = out_path / "results.json"
    typer.echo(f"Done. {len(experiment.results)} trials completed.")
    typer.echo(f"Results:    {results_path}")
    typer.echo(f"Experiment: {experiment_path}")
    typer.echo(f"Report:     {report_path}")


# @sdlc EXPERIMENT-RUNNER:REQ-032
@app.command()
def list(
    dir: str = typer.Option("./out", "--dir", help="Output directory to list"),
) -> None:
    """List previously-run experiments."""
    results_path = Path(dir) / "results.json"
    if not results_path.is_file():
        typer.echo(f"No results found at {results_path}", err=True)
        raise typer.Exit(code=1)

    import json

    data = json.loads(results_path.read_text(encoding="utf-8"))
    from zrb_llm_evaluator.models import TrialResult

    results = [TrialResult.model_validate(item) for item in data]
    typer.echo(f"Found {len(results)} trial(s):")
    typer.echo()
    typer.echo(f"{'Model':<30} {'Test Case':<20} {'Trial':<6} {'Status':<12} {'Duration':<10}")
    typer.echo("-" * 80)
    for r in results:
        typer.echo(
            f"{r.model:<30} {r.test_case:<20} {r.trial_index:<6} "
            f"{r.status:<12} {r.duration:<10.2f}"
        )


# @sdlc EXPERIMENT-RUNNER:REQ-033
@app.command()
def report(
    dir: str = typer.Option("./out", "--dir", help="Output directory with results"),
) -> None:
    """Re-generate the Markdown report from an existing experiment envelope."""
    import json

    from zrb_llm_evaluator.models import Experiment

    experiment_path = Path(dir) / "experiment.json"
    if not experiment_path.is_file():
        typer.echo(f"No experiment.json found in {dir}", err=True)
        raise typer.Exit(code=1)

    data = json.loads(experiment_path.read_text(encoding="utf-8"))
    experiment = Experiment.model_validate(data)

    report_path = Path(dir) / "report.md"
    generate_markdown_report(experiment, report_path)
    typer.echo(f"Report generated: {report_path}")
