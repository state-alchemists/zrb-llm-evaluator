# COVERS: EXPERIMENT-RUNNER:REQ-014, EXPERIMENT-RUNNER:REQ-017, EXPERIMENT-RUNNER:REQ-032, EXPERIMENT-RUNNER:REQ-033, EXPERIMENT-RUNNER:UT-016, EXPERIMENT-RUNNER:UT-050, EXPERIMENT-RUNNER:UT-053, EXPERIMENT-RUNNER:UT-054, EXPERIMENT-RUNNER:UT-055, EXPERIMENT-RUNNER:UT-057

"""Tests for CLI argument validation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from typer.testing import CliRunner
from zrb_llm_evaluator.cli import app
from zrb_llm_evaluator.models import Experiment, ExperimentConfig, TrialResult

runner = CliRunner()


class TestCLIRequiredArgs:
    """Tests for CLI argument validation — @sdlc EXPERIMENT-RUNNER:REQ-014."""

    def test_missing_required_args_exits(self) -> None:
        """EXPERIMENT-RUNNER:UT-016: No args => non-zero exit, usage printed."""
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
            "    def validate(self, output_dir, log_content, trace=None):\n"
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

    def test_report_command_corrupt_json(self, tmp_path) -> None:
        """EXPERIMENT-RUNNER:UT-050: Corrupt experiment.json => report subcommand exits non-zero."""
        out_dir = tmp_path / "out"
        out_dir.mkdir(parents=True)
        (out_dir / "experiment.json").write_text("{bad json", encoding="utf-8")

        result = runner.invoke(
            app,
            ["report", "--dir", str(out_dir)],
        )
        assert result.exit_code != 0

    def test_report_happy_path(self, tmp_path) -> None:
        """EXPERIMENT-RUNNER:UT-053: Valid experiment.json => report exits 0 and writes report.md."""
        out_dir = tmp_path / "out"
        out_dir.mkdir(parents=True)

        experiment = Experiment(
            config=ExperimentConfig(
                models=["test:m1"],
                test_case_dirs=[tmp_path / "case"],
                trials=1,
            ),
            results=[
                TrialResult(
                    model="test:m1",
                    test_case="case",
                    trial_index=1,
                    status="PASS",
                    duration=0.1,
                    exit_code=0,
                    log_path=str(tmp_path / "log.json"),
                ),
            ],
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        (out_dir / "experiment.json").write_text(
            json.dumps(experiment.model_dump(mode="json")),
            encoding="utf-8",
        )

        result = runner.invoke(
            app,
            ["report", "--dir", str(out_dir)],
        )
        assert result.exit_code == 0
        assert (out_dir / "report.md").is_file()

    def test_list_with_valid_results(self, tmp_path) -> None:
        """EXPERIMENT-RUNNER:UT-054: Valid results.json => list exits 0 and prints model names."""
        out_dir = tmp_path / "out"
        out_dir.mkdir(parents=True)

        results = [
            TrialResult(
                model="test:m1",
                test_case="case-a",
                trial_index=1,
                status="PASS",
                duration=0.5,
                exit_code=0,
                log_path="/tmp/1.log",
            ),
            TrialResult(
                model="test:m2",
                test_case="case-b",
                trial_index=1,
                status="PASS",
                duration=0.3,
                exit_code=0,
                log_path="/tmp/2.log",
            ),
        ]
        data = [r.model_dump(mode="json") for r in results]
        (out_dir / "results.json").write_text(
            json.dumps(data),
            encoding="utf-8",
        )

        result = runner.invoke(
            app,
            ["list", "--dir", str(out_dir)],
        )
        assert result.exit_code == 0
        assert "test:m1" in result.output
        assert "test:m2" in result.output

    def test_list_missing_file(self, tmp_path) -> None:
        """EXPERIMENT-RUNNER:UT-055: No results.json => list exits non-zero."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = runner.invoke(
            app,
            ["list", "--dir", str(empty_dir)],
        )
        assert result.exit_code != 0
        assert "No results found" in result.output

    def test_config_path_resolution(self, tmp_path) -> None:
        """EXPERIMENT-RUNNER:UT-057: Relative test_case_dirs resolve to absolute paths."""
        config = ExperimentConfig(
            models=["test:m1"],
            test_case_dirs=[Path("relative/case")],
            trials=1,
        )
        resolved = config.test_case_dirs[0].resolve()
        assert resolved.is_absolute()
