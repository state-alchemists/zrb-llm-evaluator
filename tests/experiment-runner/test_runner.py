# COVERS: REQ-001, REQ-003, REQ-004, REQ-005, REQ-007, REQ-008, REQ-009, REQ-011,
#   REQ-012, REQ-016, REQ-017, REQ-018, REQ-019, NFR-001,
#   UT-003, UT-004, UT-005, UT-007, UT-008, UT-009, UT-010, UT-011,
#   UT-013, UT-014, UT-019, UT-020, UT-021, UT-024

"""Tests for the runner module."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from zrb_llm_evaluator.cost_parser import parse_cost_summary
from zrb_llm_evaluator.models import (
    ExperimentConfig,
    TrialResult,
    ValidationResult,
)
from zrb_llm_evaluator.runner import (
    ResumeManager,
    TrialRunner,
    _extract_verification_marker,
    build_cell_plan,
)


def _mock_subprocess(mock_proc: AsyncMock):
    """Return an async function that returns the given mock_proc."""
    async def _create(*args: object, **kwargs: object) -> AsyncMock:
        return mock_proc
    return _create


class TestCellPlan:
    """Tests for cell plan generation — @sdlc REQ-004."""

    def test_iterates_all_combinations(self) -> None:
        """UT-004: 2 models x 2 cases x 2 trials = 8 cells."""
        config = ExperimentConfig(
            models=["test:m1", "test:m2"],
            test_case_dirs=[Path("/tmp/case1"), Path("/tmp/case2")],
            trials=2,
            parallelism=1,
            timeout=30,
        )
        cells = build_cell_plan(config)
        assert len(cells) == 8

        # Verify all combinations exist
        combinations = {(c.model, c.test_case, c.trial_index) for c in cells}
        expected = {
            ("test:m1", "case1", 1),
            ("test:m1", "case1", 2),
            ("test:m1", "case2", 1),
            ("test:m1", "case2", 2),
            ("test:m2", "case1", 1),
            ("test:m2", "case1", 2),
            ("test:m2", "case2", 1),
            ("test:m2", "case2", 2),
        }
        assert combinations == expected


class TestTrialRunner:
    """Tests for TrialRunner — @sdlc REQ-001, REQ-005, REQ-016, REQ-018."""

    @pytest.mark.asyncio
    async def test_results_written_after_each_trial(
        self, tmp_path: Path, sample_test_case
    ) -> None:
        """UT-003: After each trial, results.json has exactly N entries."""
        output_dir = tmp_path / "out"
        results_path = output_dir / "results.json"
        mgr = ResumeManager(results_path)

        for trial_idx in range(1, 4):
            # Mock TrialRunner.run to avoid actual subprocess calls
            result = TrialResult(
                model="openai:gpt-4o",
                test_case=sample_test_case.name,
                trial_index=trial_idx,
                status="PASS",
                duration=0.1,
                exit_code=0,
                log_path=str(tmp_path / f"{trial_idx}.log"),
            )
            mgr.append(result)

            assert results_path.exists()
            data = json.loads(results_path.read_text(encoding="utf-8"))
            assert len(data) == trial_idx

    @pytest.mark.asyncio
    async def test_timeout_kills_subprocess_and_records(
        self, tmp_path: Path, sample_test_case
    ) -> None:
        """UT-005: Mock subprocess that sleeps 60s, timeout=1s => TIMEOUT."""
        # Use model_construct to bypass Pydantic validation (min timeout is 30)
        config = ExperimentConfig.model_construct(
            models=["openai:gpt-4o"],
            test_case_dirs=[tmp_path],
            trials=1,
            parallelism=1,
            timeout=1,
        )
        output_dir = tmp_path / "out"

        # Monkey-patch create_subprocess_exec to return a slow mock
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=0)

        async def mock_create_subprocess_exec(*args: object, **kwargs: object) -> AsyncMock:
            return mock_proc

        with patch.object(asyncio, "create_subprocess_exec", mock_create_subprocess_exec):
            runner = TrialRunner(config, sample_test_case, output_dir)
            result = await runner.run("openai:gpt-4o", 1)

        assert result.status == "TIMEOUT"
        # @sdlc REQ-008: log_path references a file
        assert result.log_path != ""

    @pytest.mark.asyncio
    async def test_nonzero_exit_records_error(
        self, tmp_path: Path, sample_test_case
    ) -> None:
        """UT-007: Non-zero exit code => ERROR status."""
        config = ExperimentConfig(
            models=["openai:gpt-4o"],
            test_case_dirs=[tmp_path],
            trials=1,
            parallelism=1,
            timeout=30,
        )
        output_dir = tmp_path / "out"

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"Some output", b"")
        )
        mock_proc.returncode = 1

        with patch.object(asyncio, "create_subprocess_exec", _mock_subprocess(mock_proc)):
            runner = TrialRunner(config, sample_test_case, output_dir)
            result = await runner.run("openai:gpt-4o", 1)

        assert result.status == "ERROR"

    @pytest.mark.asyncio
    async def test_verification_marker_overrides_exit(
        self, tmp_path: Path, sample_test_case
    ) -> None:
        """UT-008: VERIFICATION_RESULT: PASS overrides exit code 1."""
        config = ExperimentConfig(
            models=["openai:gpt-4o"],
            test_case_dirs=[tmp_path],
            trials=1,
            parallelism=1,
            timeout=30,
        )
        output_dir = tmp_path / "out"

        stdout = "Some output\nVERIFICATION_RESULT: PASS\nDone.\n"
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(stdout.encode("utf-8"), b"")
        )
        mock_proc.returncode = 1

        with patch.object(asyncio, "create_subprocess_exec", _mock_subprocess(mock_proc)):
            runner = TrialRunner(config, sample_test_case, output_dir)
            result = await runner.run("openai:gpt-4o", 1)

        assert result.status == "PASS"

    @pytest.mark.asyncio
    async def test_cli_name_custom_binary(
        self, tmp_path: Path, sample_test_case
    ) -> None:
        """UT-014: --cli-name=my-zrb => subprocess invoked with my-zrb."""
        config = ExperimentConfig(
            models=["openai:gpt-4o"],
            test_case_dirs=[tmp_path],
            trials=1,
            parallelism=1,
            timeout=30,
            cli_name="my-zrb",
        )
        output_dir = tmp_path / "out"

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"Output", b"")
        )
        mock_proc.returncode = 0

        with patch.object(asyncio, "create_subprocess_exec") as mock_exec:
            mock_exec.return_value = mock_proc
            runner = TrialRunner(config, sample_test_case, output_dir)
            await runner.run("openai:gpt-4o", 1)

        # Verify the CLI name passed to create_subprocess_exec
        call_args = mock_exec.call_args
        assert call_args is not None
        assert call_args[0][0] == "my-zrb"

    @pytest.mark.asyncio
    async def test_env_var_set_before_invocation(
        self, tmp_path: Path, sample_test_case
    ) -> None:
        """UT-019: ZRB_LLM_HISTORY_DIR set; --session passed."""
        config = ExperimentConfig(
            models=["openai:gpt-4o"],
            test_case_dirs=[tmp_path],
            trials=1,
            parallelism=1,
            timeout=30,
        )
        output_dir = tmp_path / "out"

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"Output", b"")
        )
        mock_proc.returncode = 0

        with patch.object(asyncio, "create_subprocess_exec") as mock_exec:
            mock_exec.return_value = mock_proc
            runner = TrialRunner(config, sample_test_case, output_dir)
            await runner.run("openai:gpt-4o", 1)

        call_kwargs = mock_exec.call_args.kwargs or {}
        env = call_kwargs.get("env", {})
        assert "ZRB_LLM_HISTORY_DIR" in env

        # Check --session was passed
        call_args = mock_exec.call_args
        assert call_args is not None
        args_list = call_args[0]
        assert "--session" in args_list

    @pytest.mark.asyncio
    async def test_output_dir_structure(
        self, tmp_path: Path, sample_test_case
    ) -> None:
        """UT-021: Output dir follows {out}/{model_safe}/{case}/trial-{N}/ pattern."""
        config = ExperimentConfig(
            models=["openai:gpt-4o", "anthropic:claude-3"],
            test_case_dirs=[tmp_path],
            trials=2,
            parallelism=1,
            timeout=30,
        )
        output_dir = tmp_path / "out"

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"Output", b"")
        )
        mock_proc.returncode = 0

        with patch.object(asyncio, "create_subprocess_exec", _mock_subprocess(mock_proc)):
            runner = TrialRunner(config, sample_test_case, output_dir)
            await runner.run("openai:gpt-4o", 1)
            await runner.run("openai:gpt-4o", 2)
            await runner.run("anthropic:claude-3", 1)
            await runner.run("anthropic:claude-3", 2)

        expected_dirs = [
            output_dir / "openai_gpt-4o" / sample_test_case.name / "trial-1",
            output_dir / "openai_gpt-4o" / sample_test_case.name / "trial-2",
            output_dir / "anthropic_claude-3" / sample_test_case.name / "trial-1",
            output_dir / "anthropic_claude-3" / sample_test_case.name / "trial-2",
        ]
        for d in expected_dirs:
            assert d.is_dir(), f"Expected directory {d} does not exist"

    @pytest.mark.asyncio
    async def test_overhead_without_llm(
        self, tmp_path: Path, sample_test_case
    ) -> None:
        """UT-024 / NFR-001: Per-trial overhead < 2s without LLM call."""
        config = ExperimentConfig(
            models=["openai:gpt-4o"],
            test_case_dirs=[tmp_path],
            trials=1,
            parallelism=1,
            timeout=30,
        )
        output_dir = tmp_path / "out"

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"fast output", b"")
        )
        mock_proc.returncode = 0

        import time

        with patch.object(asyncio, "create_subprocess_exec", _mock_subprocess(mock_proc)):
            runner = TrialRunner(config, sample_test_case, output_dir)
            start = time.monotonic()
            await runner.run("openai:gpt-4o", 1)
            elapsed = time.monotonic() - start

        assert elapsed < 2.0, f"Overhead {elapsed:.3f}s exceeds 2s limit"


class TestCostParser:
    """Tests for cost summary parsing — @sdlc REQ-019."""

    def test_cost_summary_parsed(self) -> None:
        """UT-022: Parse cost line with all fields."""
        stdout = (
            "Some text\n"
            "Total tokens: 150 | Input: 100 | Output: 50 | Cache: 0\n"
            "More text\n"
        )
        result = parse_cost_summary(stdout)
        assert result["total_tokens"] == 150
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50
        assert result["cache_read_tokens"] == 0

    def test_cost_summary_missing_defaults_zero(self) -> None:
        """UT-023: No cost line => all zero."""
        stdout = "Just some output without any cost info.\n"
        result = parse_cost_summary(stdout)
        assert result["total_tokens"] == 0
        assert result["input_tokens"] == 0
        assert result["output_tokens"] == 0
        assert result["cache_read_tokens"] == 0

    def test_cost_summary_partial_defaults(self) -> None:
        """Partial cost line still returns defaults."""
        stdout = "Total tokens: 100 | Input: 50 | Output: | Cache:\n"
        result = parse_cost_summary(stdout)
        # The pattern won't match because Output/Cache don't have numbers
        assert result["total_tokens"] == 0


class TestVerificationMarker:
    """Tests for VERIFICATION_RESULT marker parsing — @sdlc REQ-007."""

    def test_extract_verification_marker_found(self) -> None:
        """Marker found in stdout."""
        stdout = "Working...\nVERIFICATION_RESULT: PASS\nDone.\n"
        assert _extract_verification_marker(stdout) == "PASS"

    def test_extract_verification_marker_excellent(self) -> None:
        """EXCELLENT marker is extracted."""
        stdout = "VERIFICATION_RESULT: EXCELLENT\n"
        assert _extract_verification_marker(stdout) == "EXCELLENT"

    def test_extract_verification_marker_not_found(self) -> None:
        """No marker => None."""
        stdout = "Just working.\n"
        assert _extract_verification_marker(stdout) is None

    def test_extract_verification_marker_invalid(self) -> None:
        """Invalid marker value is ignored."""
        stdout = "VERIFICATION_RESULT: UNKNOWN\n"
        assert _extract_verification_marker(stdout) is None


class TestRunnerValidatorIntegration:
    """Tests for validator interaction in TrialRunner — @sdlc REQ-009, REQ-011."""

    @pytest.mark.asyncio
    async def test_validator_invoked_on_completion(
        self, tmp_path: Path
    ) -> None:
        """UT-010: Validator called with output_dir and log_content."""
        # Create a proper test case with a tracking validator
        case_dir = tmp_path / "v-case"
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "instruction.txt").write_text("Hello", encoding="utf-8")

        calls = []
        class TrackingValidator:
            def validate(self, output_dir, log_content):
                calls.append((output_dir, log_content))
                return ValidationResult(status="PASS", score=1.0, details=[])

        (case_dir / "validator.py").write_text(
            "from pathlib import Path\n"
            "from zrb_llm_evaluator.models import ValidationResult, ValidationCheck\n"
            "class TV:\n"
            "    def validate(self, output_dir, log_content):\n"
            "        return ValidationResult(status='PASS', score=1.0, details=[])\n"
            "validator = TV()\n"
        )

        from zrb_llm_evaluator.loader import load_test_case
        tc = load_test_case(case_dir)
        # Override with tracking
        tc.validator = TrackingValidator()  # type: ignore[assignment]

        config = ExperimentConfig(
            models=["openai:gpt-4o"],
            test_case_dirs=[case_dir],
            trials=1,
            parallelism=1,
            timeout=30,
            cli_name="echo",  # Use echo as predictable subprocess
        )
        output_dir = tmp_path / "out"

        runner = TrialRunner(config, tc, output_dir)
        result = await runner.run("openai:gpt-4o", 1)

        assert result.status == "PASS", f"Expected PASS, got {result.status}"
        assert len(calls) == 1, f"Validator was called {len(calls)} times, expected 1"

    @pytest.mark.asyncio
    async def test_validator_exception_records_error(
        self, tmp_path: Path, sample_test_case
    ) -> None:
        """UT-013: Validator raises exception => ERROR status."""
        config = ExperimentConfig(
            models=["openai:gpt-4o"],
            test_case_dirs=[tmp_path],
            trials=1,
            parallelism=1,
            timeout=30,
        )
        output_dir = tmp_path / "out"

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"Output", b"")
        )
        mock_proc.returncode = 0

        # Replace validator with one that raises
        original_validator = sample_test_case.validator

        class BrokenValidator:
            def validate(self, output_dir_val, log_content):
                msg = "bad check"
                raise ValueError(msg)

        sample_test_case.validator = BrokenValidator()  # type: ignore[assignment]

        with patch.object(asyncio, "create_subprocess_exec", _mock_subprocess(mock_proc)):
            runner = TrialRunner(config, sample_test_case, output_dir)
            result = await runner.run("openai:gpt-4o", 1)

        assert result.status == "ERROR"

        # Restore
        sample_test_case.validator = original_validator

    @pytest.mark.asyncio
    async def test_timeout_result_references_log_file(
        self, tmp_path: Path, sample_test_case
    ) -> None:
        """UT-009: TIMEOUT result has a non-empty log_path."""
        # Use model_construct to bypass Pydantic validation (min timeout is 30)
        config = ExperimentConfig.model_construct(
            models=["openai:gpt-4o"],
            test_case_dirs=[tmp_path],
            trials=1,
            parallelism=1,
            timeout=1,
        )
        output_dir = tmp_path / "out"

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=0)

        async def mock_create_subprocess_exec(*args: object, **kwargs: object) -> AsyncMock:
            return mock_proc

        with patch.object(asyncio, "create_subprocess_exec", mock_create_subprocess_exec):
            runner = TrialRunner(config, sample_test_case, output_dir)
            result = await runner.run("openai:gpt-4o", 1)

        assert result.status == "TIMEOUT"
        assert result.log_path != ""
        log_file = Path(result.log_path)
        assert log_file.exists()

    @pytest.mark.asyncio
    async def test_results_json_atomic_write(
        self, tmp_path: Path, sample_test_case
    ) -> None:
        """UT-020: results.json is valid JSON with exactly 1 TrialResult entry."""
        output_dir = tmp_path / "out-atomic"
        output_dir.mkdir(parents=True, exist_ok=True)
        results_path = output_dir / "results.json"
        mgr = ResumeManager(results_path)

        result = TrialResult(
            model="openai:gpt-4o",
            test_case=sample_test_case.name,
            trial_index=1,
            status="PASS",
            duration=0.1,
            exit_code=0,
            log_path=str(tmp_path / "test.log"),
        )
        mgr.append(result)

        assert results_path.exists()
        raw = results_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        assert len(data) == 1
        assert data[0]["model"] == "openai:gpt-4o"
