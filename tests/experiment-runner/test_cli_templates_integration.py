# COVERS: EXPERIMENT-RUNNER:REQ-035, EXPERIMENT-RUNNER:REQ-041, EXPERIMENT-RUNNER:REQ-042,
# COVERS: EXPERIMENT-RUNNER:IT-007, EXPERIMENT-RUNNER:IT-008, EXPERIMENT-RUNNER:E2E-005

"""Integration/E2E tests: running the real CLI against mocked non-zrb binaries.

Exercises the `run` command end-to-end (Typer CLI -> ExperimentConfig ->
run_experiment -> WorkSteward -> TrialRunner -> a resolved CliAdapter ->
a real subprocess) against small fake executables that stand in for the
`claude-code` and `opencode` binaries, since neither is assumed to be
installed in the test environment.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner
from zrb_llm_evaluator.cli import app

runner = CliRunner()


def _make_case_dir(tmp_path: Path) -> Path:
    """Create a minimal test case directory with an always-PASS validator."""
    case_dir = tmp_path / "cases" / "case-a"
    case_dir.mkdir(parents=True)
    (case_dir / "instruction.txt").write_text("Do the thing", encoding="utf-8")
    (case_dir / "validator.py").write_text(
        "from zrb_llm_evaluator.models import ValidationResult\n"
        "class V:\n"
        "    def validate(self, output_dir, log_content, trace=None):\n"
        "        return ValidationResult(status='PASS', score=1.0, details=[])\n"
        "validator = V()\n",
        encoding="utf-8",
    )
    return case_dir.parent


def _write_fake_binary(bin_dir: Path, name: str, script_body: str) -> Path:
    """Write an executable shell script named ``name`` into ``bin_dir``."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    path = bin_dir / name
    path.write_text(f"#!/bin/sh\n{script_body}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


@pytest.fixture
def fake_bin_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Prepend a temp dir to PATH so fake CLI binaries are found by name."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return bin_dir


class TestRunCommandWithClaudeCodeTemplate:
    """EXPERIMENT-RUNNER:IT-007 — run --cli-template claude-code against a mocked binary."""

    def test_run_command_with_claude_code_template(
        self, tmp_path: Path, fake_bin_dir: Path,
    ) -> None:
        """results.json is populated via ClaudeCodeCliAdapter; statuses are terminal."""
        cases_dir = _make_case_dir(tmp_path)
        payload = json.dumps({
            "type": "result",
            "subtype": "success",
            "result": "done",
            "session_id": "s1",
            "usage": {
                "input_tokens": 120,
                "output_tokens": 80,
                "cache_read_input_tokens": 10,
            },
        })
        _write_fake_binary(fake_bin_dir, "fake-claude", f"cat <<'JSON'\n{payload}\nJSON\nexit 0")

        out_dir = tmp_path / "out"
        result = runner.invoke(
            app,
            [
                "run",
                "--models", "test:m1",
                "--test-cases", str(cases_dir / "case-a"),
                "--trials", "1",
                "--parallelism", "1",
                "--timeout", "30",
                "--cli-name", "fake-claude",
                "--cli-template", "claude-code",
                "--output-dir", str(out_dir),
            ],
        )
        assert result.exit_code == 0, result.output

        results_path = out_dir / "results.json"
        assert results_path.is_file()
        data = json.loads(results_path.read_text(encoding="utf-8"))
        assert len(data) == 1
        entry = data[0]
        assert entry["status"] in ("EXCELLENT", "PASS", "FAIL", "TIMEOUT", "ERROR")
        # Usage was parsed via ClaudeCodeCliAdapter's JSON `usage` block, not
        # zrb's 💸 line (there is none in this stdout) — proves the right
        # adapter ran.
        assert entry["input_tokens"] == 120
        assert entry["output_tokens"] == 80
        assert entry["cache_read_tokens"] == 10
        assert entry["total_tokens"] == 210


class TestRunCommandWithOpencodeTemplate:
    """EXPERIMENT-RUNNER:IT-008 — run --cli-template opencode against a mocked binary."""

    def test_run_command_with_opencode_template(
        self, tmp_path: Path, fake_bin_dir: Path,
    ) -> None:
        """results.json is populated via OpencodeCliAdapter; statuses are terminal."""
        cases_dir = _make_case_dir(tmp_path)
        _write_fake_binary(
            fake_bin_dir,
            "fake-opencode",
            "echo 'opencode run output'\n"
            "echo 'Tokens: 40 in / 20 out / 5 cached / 65 total'\n"
            "exit 0",
        )

        out_dir = tmp_path / "out"
        result = runner.invoke(
            app,
            [
                "run",
                "--models", "test:m1",
                "--test-cases", str(cases_dir / "case-a"),
                "--trials", "1",
                "--parallelism", "1",
                "--timeout", "30",
                "--cli-name", "fake-opencode",
                "--cli-template", "opencode",
                "--output-dir", str(out_dir),
            ],
        )
        assert result.exit_code == 0, result.output

        results_path = out_dir / "results.json"
        assert results_path.is_file()
        data = json.loads(results_path.read_text(encoding="utf-8"))
        assert len(data) == 1
        entry = data[0]
        assert entry["status"] in ("EXCELLENT", "PASS", "FAIL", "TIMEOUT", "ERROR")
        assert entry["input_tokens"] == 40
        assert entry["output_tokens"] == 20
        assert entry["cache_read_tokens"] == 5
        assert entry["total_tokens"] == 65


class TestEvaluateNonZrbCli:
    """EXPERIMENT-RUNNER:E2E-005 (US-011) — evaluate a non-zrb CLI end-to-end."""

    def test_evaluate_opencode_produces_results_and_report_like_zrb(
        self, tmp_path: Path, fake_bin_dir: Path,
    ) -> None:
        """1 model x 1 case x 2 trials via opencode -> results.json + report.md, same as zrb."""
        cases_dir = _make_case_dir(tmp_path)
        _write_fake_binary(
            fake_bin_dir,
            "fake-opencode",
            "echo 'Tokens: 10 in / 5 out / 0 cached / 15 total'\nexit 0",
        )

        out_dir = tmp_path / "out"
        result = runner.invoke(
            app,
            [
                "run",
                "--models", "test:m1",
                "--test-cases", str(cases_dir / "case-a"),
                "--trials", "2",
                "--parallelism", "1",
                "--timeout", "30",
                "--cli-name", "fake-opencode",
                "--cli-template", "opencode",
                "--output-dir", str(out_dir),
            ],
        )
        assert result.exit_code == 0, result.output

        results_path = out_dir / "results.json"
        report_path = out_dir / "report.md"
        assert results_path.is_file()
        assert report_path.is_file()

        data = json.loads(results_path.read_text(encoding="utf-8"))
        assert len(data) == 2
        terminal_statuses = {"EXCELLENT", "PASS", "FAIL", "TIMEOUT", "ERROR"}
        for entry in data:
            assert entry["status"] in terminal_statuses

        report_text = report_path.read_text(encoding="utf-8")
        assert "test:m1" in report_text
        assert "case-a" in report_text
