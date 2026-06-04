# GENERATED FROM SPEC: .sdlc/specs/experiment-runner/spec.md
# IMPLEMENTS: REQ-004, REQ-014, REQ-015, REQ-016, RULE-011, RULE-012

"""Typer CLI entry point for the experiment runner."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import typer

from zrb_llm_evaluator.loader import load_test_cases
from zrb_llm_evaluator.models import ExperimentConfig
from zrb_llm_evaluator.reporter import generate_json_report, generate_markdown_report
from zrb_llm_evaluator.runner import run_experiment

app = typer.Typer(
    name="zrb-llm-evaluator",
    help="Multi-trial experiment runner for zrb chat",
)


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


# @sdlc REQ-004, REQ-014, REQ-015, REQ-016
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
    cli_name: str = typer.Option("zrb", "--cli-name", help="CLI binary name"),
    env_prefix: str = typer.Option(
        "ZRB", "--env-prefix", help="Env var prefix (default ZRB → ZRB_LLM_*)",
    ),
    output_dir: str = typer.Option(
        "./out", "--output-dir", help="Output directory for results",
    ),
) -> None:
    """Run a full experiment: N models x M test cases x T trials."""
    _setup_logging()
    # Parse models
    model_list = [m.strip() for m in models.split(",") if m.strip()]
    case_paths = [Path(p.strip()) for p in test_cases.split(",") if p.strip()]

    # Validate & build config
    try:
        config = ExperimentConfig(
            models=model_list,
            test_case_dirs=case_paths,
            trials=trials,
            parallelism=parallelism,
            timeout=timeout,
            cli_name=cli_name,
            env_prefix=env_prefix,
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

    experiment = asyncio.run(run_experiment(config, loaded_cases, out_path))

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


# @sdlc REQ-017
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


# @sdlc REQ-017
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
