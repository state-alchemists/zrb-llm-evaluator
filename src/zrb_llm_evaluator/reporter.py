# GENERATED FROM SPEC: specs/experiment-runner/requirements.md
# IMPLEMENTS: REQ-003, REQ-017

"""Report generation — Markdown and JSON output."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from zrb_llm_evaluator.models import TrialResult


# @sdlc REQ-003, REQ-017
def generate_json_report(results: list[TrialResult], output_path: Path) -> Path:
    """Generate a structured JSON report.

    Args:
    ----
        results: All trial results.
        output_path: Path to write the JSON file.

    Returns:
    -------
        The path to the written file.

    """
    data = [r.model_dump(mode="json") for r in results]
    tmp: Path | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(output_path.parent),
            prefix=".report_tmp_",
            suffix=".json",
        )
        os.close(fd)
        tmp = Path(tmp_path)
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.rename(str(tmp), str(output_path))
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink(missing_ok=True)
    return output_path


# @sdlc REQ-003
def generate_markdown_report(results: list[TrialResult], output_path: Path) -> Path:
    """Generate a human-readable Markdown report.

    Args:
    ----
        results: All trial results.
        output_path: Path to write the Markdown file.

    Returns:
    -------
        The path to the written file.

    """
    lines: list[str] = [
        "# Experiment Report\n",
        f"**Total trials**: {len(results)}\n",
        "**Generated**: ...\n",
        "\n## Summary\n\n",
        "| Model | Test Case | Trial | Status | Duration (s) | Score |\n",
        "|-------|-----------|-------|--------|-------------|-------|\n",
    ]

    for r in results:
        score = ""
        if r.verification_result is not None:
            score = f"{r.verification_result.score:.2f}"
        lines.append(
            f"| {r.model} | {r.test_case} | {r.trial_index} | "
            f"{r.status} | {r.duration:.2f} | {score} |\n"
        )

    lines.append("\n## Per-Trial Details\n\n")
    for r in results:
        lines.append(f"### {r.model} / {r.test_case} / Trial {r.trial_index}\n\n")
        lines.append(f"- **Status**: {r.status}\n")
        lines.append(f"- **Duration**: {r.duration:.2f}s\n")
        lines.append(f"- **Exit code**: {r.exit_code}\n")
        lines.append(f"- **Log path**: {r.log_path}\n")
        if r.verification_result is not None:
            lines.append(f"- **Validation score**: {r.verification_result.score}\n")
            for check in r.verification_result.details:
                lines.append(f"  - {check.name}: {'✓' if check.passed else '✗'} {check.message}\n")
        lines.append("\n")

    output_path.write_text("".join(lines), encoding="utf-8")
    return output_path
