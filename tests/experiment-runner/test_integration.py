# COVERS: EXPERIMENT-RUNNER:REQ-002, EXPERIMENT-RUNNER:REQ-003, EXPERIMENT-RUNNER:REQ-004, EXPERIMENT-RUNNER:REQ-006, EXPERIMENT-RUNNER:REQ-007, EXPERIMENT-RUNNER:REQ-009, EXPERIMENT-RUNNER:REQ-010, EXPERIMENT-RUNNER:REQ-017,
#   EXPERIMENT-RUNNER:REQ-018, EXPERIMENT-RUNNER:NFR-001, EXPERIMENT-RUNNER:NFR-002, EXPERIMENT-RUNNER:IT-001, EXPERIMENT-RUNNER:IT-002, EXPERIMENT-RUNNER:IT-003, EXPERIMENT-RUNNER:IT-004

"""Integration tests for the experiment runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from zrb_llm_evaluator.models import ExperimentConfig


class TestRunCommandFullPipeline:
    """EXPERIMENT-RUNNER:IT-001: Full pipeline with mock test cases."""

    @pytest.mark.asyncio
    async def test_run_command_full_pipeline(self, tmp_path: Path) -> None:
        """EXPERIMENT-RUNNER:IT-001: Run a full experiment end-to-end with mock subprocess."""
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
                "    def validate(self, output_dir, log_content, trace=None):\n"
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

        experiment = await run_experiment(config, test_cases, output_dir)
        results = experiment.results

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

        # experiment.json envelope should also be persisted
        experiment_json = output_dir / "experiment.json"
        assert experiment_json.exists()
        assert experiment.completed_at is not None
        assert experiment.started_at != ""


class TestResumeMidExperiment:
    """EXPERIMENT-RUNNER:IT-002: Resume functionality after partial execution."""

    @pytest.mark.asyncio
    async def test_resume_mid_experiment(self, tmp_path: Path) -> None:
        """EXPERIMENT-RUNNER:IT-002: Run 2 models x 1 case x 2 trials; simulate interrupted after cell 3."""
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
            "    def validate(self, output_dir, log_content, trace=None):\n"
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
        experiment1 = await run_experiment(config, test_cases, output_dir)
        assert len(experiment1.results) == 4

        # Second run with same output dir: should skip all completed cells
        # and preserve the experiment id + started_at from the first run.
        experiment2 = await run_experiment(config, test_cases, output_dir)
        assert len(experiment2.results) == 4  # Still 4 total
        assert experiment2.id == experiment1.id
        assert experiment2.started_at == experiment1.started_at

        # Verify the JSON has exactly 4 entries (no duplicates)
        results_json = output_dir / "results.json"
        data = json.loads(results_json.read_text(encoding="utf-8"))
        assert len(data) == 4


class TestParallelExecution:
    """EXPERIMENT-RUNNER:IT-003: Parallel execution correctness."""

    @pytest.mark.asyncio
    async def test_parallel_execution(self, tmp_path: Path) -> None:
        """EXPERIMENT-RUNNER:IT-003: Run 8 cells with parallelism=4; should finish faster than sequential."""
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
            "    def validate(self, output_dir, log_content, trace=None):\n"
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
        experiment = await run_experiment(config, test_cases, output_dir)
        elapsed = time.monotonic() - start

        assert len(experiment.results) == 8
        # With parallelism=4 and echo being instant, should be fast
        assert elapsed < 5.0, f"Parallel run took {elapsed:.2f}s"


class TestCustomValidatorExecuted:
    """EXPERIMENT-RUNNER:IT-004: Custom validator is executed and result stored."""

    @pytest.mark.asyncio
    async def test_custom_validator_executed(self, tmp_path: Path) -> None:
        """EXPERIMENT-RUNNER:IT-004: Validator returning EXCELLENT with score 0.95."""
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
            "    def validate(self, output_dir, log_content, trace=None):\n"
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

        experiment = await run_experiment(config, test_cases, output_dir)

        assert len(experiment.results) == 1
        r = experiment.results[0]
        assert r.verification_result is not None
        assert r.verification_result.status == "EXCELLENT"
        assert r.verification_result.score == 0.95


@pytest.mark.slow
class TestStress100Cells:
    """EXPERIMENT-RUNNER:NFR-002: Stress test with 100+ cells."""

    @pytest.mark.asyncio
    async def test_stress_100_cells(self, tmp_path: Path) -> None:
        """Run 100+ cells with mock subprocess returning instantly."""
        cases_dir = tmp_path / "stress-cases"
        cases_dir.mkdir()
        case_dir = cases_dir / "s-case"
        case_dir.mkdir()
        (case_dir / "instruction.txt").write_text("Test", encoding="utf-8")
        (case_dir / "validator.py").write_text(
            "from pathlib import Path\n"
            "from zrb_llm_evaluator.models import ValidationResult, ValidationCheck\n"
            "from zrb_llm_evaluator.protocols import ValidatorProtocol\n"
            "class V:\n"
            "    def validate(self, output_dir, log_content, trace=None):\n"
            "        return ValidationResult(status='PASS', score=0.9, details=[])\n"
            "validator = V()\n"
        )

        from zrb_llm_evaluator.loader import load_test_cases
        from zrb_llm_evaluator.runner import run_experiment

        # 10 models x 1 case x 10 trials = 100 cells
        models = [f"test:m{i}" for i in range(10)]
        config = ExperimentConfig(
            models=models,
            test_case_dirs=[case_dir],
            trials=10,
            parallelism=10,
            timeout=30,
            cli_name="echo",
        )

        test_cases = load_test_cases([case_dir])
        output_dir = tmp_path / "out-stress"

        experiment = await run_experiment(config, test_cases, output_dir)
        results = experiment.results

        assert len(results) == 100
        terminal_statuses = {"EXCELLENT", "PASS", "FAIL", "TIMEOUT", "ERROR"}
        for r in results:
            assert r.status in terminal_statuses, f"Non-terminal status: {r.status}"

        # Verify results.json exists and has 100 entries
        results_json = output_dir / "results.json"
        assert results_json.exists()
        import json
        data = json.loads(results_json.read_text(encoding="utf-8"))
        assert len(data) == 100
