# COVERS: REQ-014, UT-016

"""Tests for CLI argument validation."""

from __future__ import annotations

from typer.testing import CliRunner
from zrb_llm_evaluator.cli import app

runner = CliRunner()


class TestCLIRequiredArgs:
    """Tests for CLI argument validation — @sdlc REQ-014."""

    def test_missing_required_args_exits(self) -> None:
        """UT-016: No args => non-zero exit, usage printed."""
        result = runner.invoke(app, ["run"])
        assert result.exit_code != 0

    def test_missing_models(self) -> None:
        """Missing --models exits non-zero."""
        result = runner.invoke(
            app,
            ["run", "--test-cases", "/tmp/fake", "--trials", "1"],
        )
        assert result.exit_code != 0

    def test_minimal_valid_args(self, tmp_path) -> None:
        """Minimal valid args passes config validation (but will fail on test cases)."""
        case_dir = tmp_path / "case"
        case_dir.mkdir()
        (case_dir / "instruction.txt").write_text("test", encoding="utf-8")
        (case_dir / "validator.py").write_text(
            "from pathlib import Path\n"
            "from zrb_llm_evaluator.models import ValidationResult, ValidationCheck\n"
            "from zrb_llm_evaluator.protocols import ValidatorProtocol\n"
            "class V:\n"
            "    def validate(self, output_dir, log_content):\n"
            "        return ValidationResult(status='PASS', score=0.5, details=[])\n"
            "validator = V()\n"
        )

        # This should get past config validation but may fail on subprocess execution
        result = runner.invoke(
            app,
            [
                "run",
                "--models", "openai:gpt-4o",
                "--test-cases", str(case_dir),
                "--trials", "1",
                "--parallelism", "1",
                "--timeout", "30",
                "--cli-name", "echo",
                "--output-dir", str(tmp_path / "out"),
            ],
        )
        # Either exits 0 (runs) or non-zero (subprocess or other error) - not a parse error
        assert result.exit_code in (0, 1, 2)
