# GENERATED FROM SPEC: specs/experiment-runner/requirements.md
# IMPLEMENTS: REQ-003, REQ-017

"""Report generation — Markdown and JSON output."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from zrb_llm_evaluator.models import Experiment, Report


# @sdlc REQ-003, REQ-017
def generate_json_report(experiment: Experiment, output_path: Path) -> Report:
    """Generate a structured JSON report of an experiment.

    Writes the full ``Experiment`` envelope (config + results + timing) to
    ``output_path`` atomically.

    Args:
    ----
        experiment: The experiment to serialize.
        output_path: Path to write the JSON file.

    Returns:
    -------
        A ``Report`` manifest describing the produced artifact.

    """
    data = experiment.model_dump(mode="json")
    parent = output_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp: Path | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(parent),
            prefix=".report_tmp_",
            suffix=".json",
        )
        os.close(fd)
        tmp = Path(tmp_path)
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(output_path))
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink(missing_ok=True)
    return Report(
        experiment_id=experiment.id,
        json_path=str(output_path),
        generated_at=datetime.now(timezone.utc),
    )


# @sdlc REQ-003
def generate_markdown_report(experiment: Experiment, output_path: Path) -> Report:
    """Generate a human-readable Markdown report.

    Args:
    ----
        experiment: The experiment to render.
        output_path: Path to write the Markdown file.

    Returns:
    -------
        A ``Report`` manifest describing the produced artifact.

    """
    generated_at = datetime.now(timezone.utc)
    results = experiment.results
    started_str = experiment.started_at.isoformat() if experiment.started_at else "—"
    completed_str = (
        experiment.completed_at.isoformat() if experiment.completed_at else "—"
    )
    lines: list[str] = [
        "# Experiment Report\n",
        f"**Experiment ID**: {experiment.id}\n",
        f"**Total trials**: {len(results)}\n",
        f"**Started**: {started_str}\n",
        f"**Completed**: {completed_str}\n",
        f"**Generated**: {generated_at.isoformat()}\n",
        "\n## Summary\n\n",
        "| Model | Test Case | Trial | Status | Duration (s) | Score | "
        "Total Tokens | Input | Output | Cache | Tool Calls |\n",
        "|-------|-----------|-------|--------|-------------|-------|"
        "--------------|-------|--------|-------|------------|\n",
    ]

    for r in results:
        score = ""
        if r.verification_result is not None:
            score = f"{r.verification_result.score:.2f}"
        lines.append(
            f"| {r.model} | {r.test_case} | {r.trial_index} | "
            f"{r.status} | {r.duration:.2f} | {score} | "
            f"{r.total_tokens} | {r.input_tokens} | "
            f"{r.output_tokens} | {r.cache_read_tokens} | "
            f"{r.tool_call_count} |\n"
        )

    lines.append("\n## Per-Trial Details\n\n")
    for r in results:
        lines.append(f"### {r.model} / {r.test_case} / Trial {r.trial_index}\n\n")
        lines.append(f"- **Status**: {r.status}\n")
        lines.append(f"- **Duration**: {r.duration:.2f}s\n")
        lines.append(f"- **Exit code**: {r.exit_code}\n")
        lines.append(f"- **History path**: {r.log_path}\n")
        if r.stdout_log_path:
            lines.append(f"- **Stdout log path**: {r.stdout_log_path}\n")
        lines.append(
            f"- **Tokens**: total={r.total_tokens}, input={r.input_tokens}, "
            f"output={r.output_tokens}, cache={r.cache_read_tokens}\n"
        )
        if r.tool_call_count > 0:
            lines.append(
                f"- **Tool calls** ({r.tool_call_count}): "
                f"{', '.join(r.tool_calls)}\n"
            )
        if r.verification_result is not None:
            lines.append(f"- **Validation score**: {r.verification_result.score}\n")
            for check in r.verification_result.details:
                lines.append(f"  - {check.name}: {'✓' if check.passed else '✗'} {check.message}\n")
        lines.append("\n")

    output_path.write_text("".join(lines), encoding="utf-8")
    return Report(
        experiment_id=experiment.id,
        markdown_path=str(output_path),
        generated_at=generated_at,
    )
