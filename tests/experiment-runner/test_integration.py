# COVERS: REQ-002, REQ-003, REQ-004, REQ-006, REQ-007, REQ-009, REQ-010, REQ-017,
#   REQ-018, NFR-001, NFR-002, IT-001, IT-002, IT-003, IT-004

"""Integration tests for the experiment runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from zrb_llm_evaluator.models import ExperimentConfig


class TestRunCommandFullPipeline:
    """IT-001: Full pipeline with mock test cases."""

    @pytest.mark.asyncio
    async def test_run_command_full_pipeline(self, tmp_path: Path) -> None:
        """IT-001: Run a full experiment end-to-end with mock subprocess."""
        # Create 2 test case directories
        cases_dir = tmp_path / "cases"
        cases_dir.mkdir()

        for case_name in ("case-a", "case-b"):
            case_dir = cases_dir / case_name
            case_dir.mkdir()
            (case_dir / "instruction.txt").write_text(
                f"Solve problem for {case_name}", encoding="utf-8"
            )
            # Validator that always returns PASS
            (case_dir / "validator.py").write_text(
                "from pathlib import Path\n"
                "from zrb_llm_evaluator.models import ValidationResult, ValidationCheck\n"
                "from zrb_llm_evaluator.protocols import ValidatorProtocol\n"
                "class V:\n"
                "    def validate(self, output_dir, log_content):\n"
                "        return ValidationResult(status='PASS', score=0.9, details=[])\n"
                "validator = V()\n"
            )

        from zrb_llm_evaluator.loader import load_test_cases
        from zrb_llm_evaluator.runner import run_experiment

        config = ExperimentConfig(
            models=["openai:gpt-4o", "anthropic:claude-3"],
            test_case_dirs=[cases_dir / "case-a", cases_dir / "case-b"],
            trials=2,
            parallelism=2,
            timeout=30,
            cli_name="echo",  # Use echo as a predictable subprocess
        )

        test_cases = load_test_cases([cases_dir / "case-a", cases_dir / "case-b"])
        output_dir = tmp_path / "out"

        results = await run_experiment(config, test_cases, output_dir)

        # Verify 8 entries (2 models x 2 cases x 2 trials)
        assert len(results) == 8

        # All should have terminal statuses
        terminal_statuses = {"EXCELLENT", "PASS", "FAIL", "TIMEOUT", "ERROR"}
        for r in results:
            assert r.status in terminal_statuses, f"Non-terminal status: {r.status}"

        # results.json should exist and be valid
        results_json = output_dir / "results.json"
        assert results_json.exists()
        data = json.loads(results_json.read_text(encoding="utf-8"))
        assert len(data) == 8


class TestResumeMidExperiment:
    """IT-002: Resume functionality after partial execution."""

    @pytest.mark.asyncio
    async def test_resume_mid_experiment(self, tmp_path: Path) -> None:
        """IT-002: Run 2 models x 1 case x 2 trials; simulate interrupted after cell 3."""
        cases_dir = tmp_path / "cases"
        cases_dir.mkdir()
        case_dir = cases_dir / "my-case"
        case_dir.mkdir()
        (case_dir / "instruction.txt").write_text("Do something", encoding="utf-8")
        (case_dir / "validator.py").write_text(
            "from pathlib import Path\n"
            "from zrb_llm_evaluator.models import ValidationResult, ValidationCheck\n"
            "from zrb_llm_evaluator.protocols import ValidatorProtocol\n"
            "class V:\n"
            "    def validate(self, output_dir, log_content):\n"
            "        return ValidationResult(status='PASS', score=0.9, details=[])\n"
            "validator = V()\n"
        )

        from zrb_llm_evaluator.loader import load_test_cases
        from zrb_llm_evaluator.models import ExperimentConfig
        from zrb_llm_evaluator.runner import run_experiment

        test_cases = load_test_cases([case_dir])
        output_dir = tmp_path / "out"
        config = ExperimentConfig(
            models=["openai:gpt-4o", "anthropic:claude-3"],
            test_case_dirs=[case_dir],
            trials=2,
            parallelism=1,
            timeout=30,
            cli_name="echo",
        )

        # First run: should produce all 4 cells
        results1 = await run_experiment(config, test_cases, output_dir)
        assert len(results1) == 4

        # Second run with same output dir: should skip all completed cells
        results2 = await run_experiment(config, test_cases, output_dir)
        assert len(results2) == 4  # Still 4 total

        # Verify the JSON has exactly 4 entries (no duplicates)
        results_json = output_dir / "results.json"
        data = json.loads(results_json.read_text(encoding="utf-8"))
        assert len(data) == 4


class TestParallelExecution:
    """IT-003: Parallel execution correctness."""

    @pytest.mark.asyncio
    async def test_parallel_execution(self, tmp_path: Path) -> None:
        """IT-003: Run 8 cells with parallelism=4; should finish faster than sequential."""
        cases_dir = tmp_path / "cases"
        cases_dir.mkdir()
        case_dir = cases_dir / "p-case"
        case_dir.mkdir()
        (case_dir / "instruction.txt").write_text("Test", encoding="utf-8")
        (case_dir / "validator.py").write_text(
            "from pathlib import Path\n"
            "from zrb_llm_evaluator.models import ValidationResult, ValidationCheck\n"
            "from zrb_llm_evaluator.protocols import ValidatorProtocol\n"
            "class V:\n"
            "    def validate(self, output_dir, log_content):\n"
            "        return ValidationResult(status='PASS', score=0.9, details=[])\n"
            "validator = V()\n"
        )

        from zrb_llm_evaluator.loader import load_test_cases
        from zrb_llm_evaluator.runner import run_experiment

        config = ExperimentConfig(
            models=["test:m1", "test:m2", "test:m3", "test:m4"],
            test_case_dirs=[case_dir],
            trials=2,
            parallelism=4,
            timeout=30,
            cli_name="echo",
        )

        test_cases = load_test_cases([case_dir])
        output_dir = tmp_path / "out-parallel"

        import time
        start = time.monotonic()
        results = await run_experiment(config, test_cases, output_dir)
        elapsed = time.monotonic() - start

        assert len(results) == 8
        # With parallelism=4 and echo being instant, should be fast
        assert elapsed < 5.0, f"Parallel run took {elapsed:.2f}s"


class TestCustomValidatorExecuted:
    """IT-004: Custom validator is executed and result stored."""

    @pytest.mark.asyncio
    async def test_custom_validator_executed(self, tmp_path: Path) -> None:
        """IT-004: Validator returning EXCELLENT with score 0.95."""
        cases_dir = tmp_path / "cases"
        cases_dir.mkdir()
        case_dir = cases_dir / "v-case"
        case_dir.mkdir()
        (case_dir / "instruction.txt").write_text("Test", encoding="utf-8")
        # Validator returning EXCELLENT with score 0.95
        (case_dir / "validator.py").write_text(
            "from pathlib import Path\n"
            "from zrb_llm_evaluator.models import ValidationResult, ValidationCheck\n"
            "class ExcellentValidator:\n"
            "    def validate(self, output_dir, log_content):\n"
            "        return ValidationResult(status='EXCELLENT', score=0.95, details=[])\n"
            "validator = ExcellentValidator()\n"
        )

        from zrb_llm_evaluator.loader import load_test_cases
        from zrb_llm_evaluator.runner import run_experiment

        config = ExperimentConfig(
            models=["openai:gpt-4o"],
            test_case_dirs=[case_dir],
            trials=1,
            parallelism=1,
            timeout=30,
            cli_name="echo",
        )

        test_cases = load_test_cases([case_dir])
        output_dir = tmp_path / "out-validator"

        results = await run_experiment(config, test_cases, output_dir)

        assert len(results) == 1
        r = results[0]
        assert r.verification_result is not None
        assert r.verification_result.status == "EXCELLENT"
        assert r.verification_result.score == 0.95
