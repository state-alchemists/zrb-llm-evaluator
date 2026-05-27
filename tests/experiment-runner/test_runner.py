# COVERS: REQ-001, REQ-002, REQ-003, REQ-004, REQ-005, REQ-007, REQ-008, REQ-009,
#   REQ-010, REQ-011, REQ-012, REQ-016, REQ-017, REQ-018, REQ-019, NFR-001,
#   UT-003, UT-004, UT-005, UT-007, UT-008, UT-009, UT-010, UT-011,
#   UT-013, UT-014, UT-019, UT-020, UT-021, UT-024, UT-043,
#   UT-048, UT-051, UT-052, UT-056

"""Tests for the runner module."""

from __future__ import annotations

import asyncio
import json
import os
import signal
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

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
    WorkSteward,
    _extract_verification_marker,
    _load_or_init_experiment,
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

        # Mock proc.wait to raise asyncio.TimeoutError so the runner's
        # `except asyncio.TimeoutError` branch fires (matches the runner's
        # `await asyncio.wait_for(proc.wait(), ...)` control flow).
        mock_proc = AsyncMock()
        # First wait() raises TimeoutError (drives the timeout branch);
        # second wait() (called after the group kill to reap) returns cleanly.
        mock_proc.wait = AsyncMock(side_effect=[asyncio.TimeoutError, 0])
        mock_proc.kill = Mock()
        mock_proc.pid = 12345

        async def mock_create_subprocess_exec(*args: object, **kwargs: object) -> AsyncMock:
            return mock_proc

        with patch.object(asyncio, "create_subprocess_exec", mock_create_subprocess_exec), \
                patch.object(os, "getpgid", return_value=12345), \
                patch.object(os, "killpg", Mock()):
            runner = TrialRunner(config, sample_test_case, output_dir)
            result = await runner.run("openai:gpt-4o", 1)

        assert result.status == "TIMEOUT"
        # @sdlc REQ-008: log_path references a file
        assert result.log_path != ""

    # COVERS: REQ-005 (UT-043)
    @pytest.mark.asyncio
    async def test_timeout_kills_whole_process_group(
        self, tmp_path: Path, sample_test_case
    ) -> None:
        """UT-043: on timeout, the runner SIGKILLs the entire descendant group.

        Asserts:
        - create_subprocess_exec is invoked with start_new_session=True so the
          child becomes its own process-group leader.
        - os.killpg is called once with that leader's pgid and SIGKILL.
        - The resulting TrialResult.status == "TIMEOUT".
        """
        # Use model_construct to bypass Pydantic validation (min timeout is 30)
        config = ExperimentConfig.model_construct(
            models=["openai:gpt-4o"],
            test_case_dirs=[tmp_path],
            trials=1,
            parallelism=1,
            timeout=1,
        )
        output_dir = tmp_path / "out"

        # Mock proc.wait to raise asyncio.TimeoutError on the first call (drives
        # the timeout branch) and return 0 on the post-kill reap.
        mock_proc = AsyncMock()
        mock_proc.wait = AsyncMock(side_effect=[asyncio.TimeoutError, 0])
        mock_proc.kill = Mock()
        mock_proc.pid = 12345

        captured_kwargs: dict[str, object] = {}

        async def mock_create_subprocess_exec(
            *args: object, **kwargs: object,
        ) -> AsyncMock:
            captured_kwargs.update(kwargs)
            return mock_proc

        mock_killpg = Mock()
        with patch.object(asyncio, "create_subprocess_exec", mock_create_subprocess_exec), \
                patch.object(os, "getpgid", return_value=12345), \
                patch.object(os, "killpg", mock_killpg):
            runner = TrialRunner(config, sample_test_case, output_dir)
            result = await runner.run("openai:gpt-4o", 1)

        # start_new_session=True was passed through to create_subprocess_exec.
        assert captured_kwargs.get("start_new_session") is True
        # killpg was invoked once with the leader's pgid and SIGKILL.
        mock_killpg.assert_called_once_with(12345, signal.SIGKILL)
        assert result.status == "TIMEOUT"

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

        stdout_bytes = b"Some output\nVERIFICATION_RESULT: PASS\nDone.\n"
        mock_proc = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=1)
        mock_proc.returncode = 1

        # Runner streams subprocess stdout directly to disk via `stdout=log_file`;
        # the mock has to write the verification marker into that file so the
        # runner can read it back from log_path.
        async def writing_create(*args: object, **kwargs: object) -> AsyncMock:
            log_file = kwargs.get("stdout")
            if log_file is not None:
                log_file.write(stdout_bytes)
                log_file.flush()
            return mock_proc

        with patch.object(asyncio, "create_subprocess_exec", writing_create):
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
        """UT-019: ZRB_LLM_HISTORY_DIR and ZRB_LLM_JOURNAL_DIR set; --session passed."""
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
        assert "ZRB_LLM_JOURNAL_DIR" in env

        # Check --session was passed
        call_args = mock_exec.call_args
        assert call_args is not None
        args_list = call_args[0]
        assert "--session" in args_list
        # The cell's model identifier must be forwarded to `zrb chat`,
        # otherwise every trial silently runs zrb's default model.
        assert "--model" in args_list
        assert args_list[args_list.index("--model") + 1] == "openai:gpt-4o"

    @pytest.mark.asyncio
    async def test_env_prefix_custom(
        self, tmp_path: Path, sample_test_case
    ) -> None:
        """UT-048: env_prefix="MYAPP" => MYAPP_LLM_HISTORY_DIR, MYAPP_LLM_JOURNAL_DIR."""
        config = ExperimentConfig(
            models=["openai:gpt-4o"],
            test_case_dirs=[tmp_path],
            trials=1,
            parallelism=1,
            timeout=30,
            env_prefix="MYAPP",
        )
        output_dir = tmp_path / "out"

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"Output", b""))
        mock_proc.returncode = 0

        with patch.object(asyncio, "create_subprocess_exec") as mock_exec:
            mock_exec.return_value = mock_proc
            runner = TrialRunner(config, sample_test_case, output_dir)
            await runner.run("openai:gpt-4o", 1)

        call_kwargs = mock_exec.call_args.kwargs or {}
        env = call_kwargs.get("env", {})
        assert "MYAPP_LLM_HISTORY_DIR" in env
        assert "MYAPP_LLM_JOURNAL_DIR" in env
        assert "ZRB_LLM_HISTORY_DIR" not in env
        assert "ZRB_LLM_JOURNAL_DIR" not in env

    @pytest.mark.asyncio
    async def test_journal_env_var_set(
        self, tmp_path: Path, sample_test_case
    ) -> None:
        """UT-046: ZRB_LLM_JOURNAL_DIR set and is a sibling of HISTORY_DIR."""
        config = ExperimentConfig(
            models=["openai:gpt-4o"],
            test_case_dirs=[tmp_path],
            trials=1,
            parallelism=1,
            timeout=30,
        )
        output_dir = tmp_path / "out"

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"Output", b""))
        mock_proc.returncode = 0

        with patch.object(asyncio, "create_subprocess_exec") as mock_exec:
            mock_exec.return_value = mock_proc
            runner = TrialRunner(config, sample_test_case, output_dir)
            await runner.run("openai:gpt-4o", 1)

        call_kwargs = mock_exec.call_args.kwargs or {}
        env = call_kwargs.get("env", {})
        assert "ZRB_LLM_JOURNAL_DIR" in env
        journal_dir = Path(env["ZRB_LLM_JOURNAL_DIR"])
        history_dir = Path(env["ZRB_LLM_HISTORY_DIR"])
        # Path ends with /notes
        assert journal_dir.name == "notes"
        # Sibling of history/ inside the same cell_dir
        assert journal_dir.parent == history_dir.parent

    @pytest.mark.asyncio
    async def test_llm_notes_isolated_per_trial(
        self, tmp_path: Path, sample_test_case
    ) -> None:
        """UT-047: Each trial gets its own ZRB_LLM_JOURNAL_DIR."""
        config = ExperimentConfig(
            models=["openai:gpt-4o"],
            test_case_dirs=[tmp_path],
            trials=2,
            parallelism=1,
            timeout=30,
        )
        output_dir = tmp_path / "out"

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"Output", b""))
        mock_proc.returncode = 0

        captured_envs: list[dict[str, str]] = []

        async def capturing_create(*args: object, **kwargs: object) -> AsyncMock:
            env = kwargs.get("env", {})
            captured_envs.append(dict(env))
            return mock_proc

        with patch.object(asyncio, "create_subprocess_exec", capturing_create):
            runner = TrialRunner(config, sample_test_case, output_dir)
            await runner.run("openai:gpt-4o", 1)
            await runner.run("openai:gpt-4o", 2)

        assert len(captured_envs) == 2
        journal_1 = captured_envs[0]["ZRB_LLM_JOURNAL_DIR"]
        journal_2 = captured_envs[1]["ZRB_LLM_JOURNAL_DIR"]
        assert journal_1 != journal_2
        assert "trial-1" in journal_1
        assert "trial-2" in journal_2

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

    @pytest.mark.asyncio
    async def test_results_json_concurrent_append(
        self, tmp_path: Path, sample_test_case
    ) -> None:
        """UT-052: Concurrent appends => valid JSON with all entries, no corruption."""
        output_dir = tmp_path / "out-concurrent"
        output_dir.mkdir(parents=True)
        results_path = output_dir / "results.json"
        mgr = ResumeManager(results_path)

        async def append_one(i: int) -> None:
            result = TrialResult(
                model="openai:gpt-4o",
                test_case=sample_test_case.name,
                trial_index=i,
                status="PASS",
                duration=0.1,
                exit_code=0,
                log_path=str(tmp_path / f"{i}.log"),
            )
            mgr.append(result)

        await asyncio.gather(*[append_one(i) for i in range(1, 11)])

        assert results_path.exists()
        raw = results_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        assert len(data) == 10

        trial_indices = {entry["trial_index"] for entry in data}
        assert trial_indices == set(range(1, 11))


class TestExperimentLifecycle:
    """Tests for experiment lifecycle — @sdlc REQ-003, REQ-017."""

    def test_load_or_init_experiment_corrupt_json(
        self, tmp_path: Path,
    ) -> None:
        """UT-051: Corrupt experiment.json => fresh experiment created (no crash)."""
        output_dir = tmp_path / "out"
        output_dir.mkdir(parents=True)
        experiment_path = output_dir / "experiment.json"
        experiment_path.write_text("{bad json", encoding="utf-8")

        config = ExperimentConfig(
            models=["openai:gpt-4o"],
            test_case_dirs=["/tmp/case"],
            trials=1,
        )
        experiment = _load_or_init_experiment(experiment_path, config)

        assert experiment.config == config
        assert experiment.results == []
        assert experiment.completed_at is None


class TestCostParser:
    """Tests for cost summary parsing — @sdlc REQ-019."""

    def test_cost_summary_parsed(self) -> None:
        """UT-022: Parse cost line with all fields."""
        stdout = (
            "Some text\n"
            "💸 (Requests: 1 | Tool Calls: 0 | Total: 150) "
            "Input: 100 | Audio Input: 0 | Output: 50 | Audio Output: 0 | "
            "Cache Read: 0 | Cache Write: 0 | Details: {}\n"
            "More text\n"
        )
        result = parse_cost_summary(stdout)
        assert result["total_tokens"] == 150
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50
        assert result["cache_read_tokens"] == 0

    def test_cost_summary_parsed_real_zrb_format(self) -> None:
        """UT-044: Parse the real zrb 💸 cost line; ignore Audio Input/Output."""
        stdout = (
            "Some preamble line\n"
            "💸 (Requests: 4 | Tool Calls: 7 | Total: 1500) "
            "Input: 1000 | Audio Input: 0 | Output: 500 | Audio Output: 0 | "
            "Cache Read: 200 | Cache Write: 0 | Details: {}\n"
            "Trailing text\n"
        )
        result = parse_cost_summary(stdout)
        assert result["total_tokens"] == 1500
        assert result["input_tokens"] == 1000
        assert result["output_tokens"] == 500
        assert result["cache_read_tokens"] == 200

        # Second case: non-zero Audio Input/Output must NOT bleed into
        # Input/Output. This proves the negative lookbehind anchors hold.
        stdout2 = (
            "💸 (Requests: 1 | Tool Calls: 0 | Total: 1500) "
            "Input: 1000 | Audio Input: 999 | Output: 500 | "
            "Audio Output: 888 | Cache Read: 200 | Cache Write: 0 | "
            "Details: {}\n"
        )
        result2 = parse_cost_summary(stdout2)
        assert result2["input_tokens"] == 1000
        assert result2["input_tokens"] != 999
        assert result2["output_tokens"] == 500
        assert result2["output_tokens"] != 888

    def test_cost_summary_uses_last_line_when_multiple(self) -> None:
        """UT-045: When multiple 💸 lines appear, only the LAST is used."""
        stdout = (
            "💸 (Requests: 1 | Tool Calls: 0 | Total: 100) "
            "Input: 60 | Audio Input: 0 | Output: 40 | Audio Output: 0 | "
            "Cache Read: 10 | Cache Write: 0 | Details: {}\n"
            "intermediate output\n"
            "💸 (Requests: 2 | Tool Calls: 1 | Total: 250) "
            "Input: 150 | Audio Input: 0 | Output: 100 | Audio Output: 0 | "
            "Cache Read: 30 | Cache Write: 0 | Details: {}\n"
        )
        result = parse_cost_summary(stdout)
        assert result["total_tokens"] == 250
        assert result["input_tokens"] == 150
        assert result["output_tokens"] == 100
        assert result["cache_read_tokens"] == 30
        # Explicitly NOT the sum of the two lines (would be 350).
        assert result["total_tokens"] != 350

    def test_cost_summary_missing_defaults_zero(self) -> None:
        """UT-023: No cost line => all zero."""
        stdout = "Just some output without any cost info.\n"
        result = parse_cost_summary(stdout)
        assert result["total_tokens"] == 0
        assert result["input_tokens"] == 0
        assert result["output_tokens"] == 0
        assert result["cache_read_tokens"] == 0

    def test_cost_summary_partial_zrb_line_returns_zero(self) -> None:
        """Partial 💸 line missing Cache Read/Write returns all zeros."""
        stdout = (
            "💸 (Requests: 1 | Tool Calls: 0 | Total: 100) "
            "Input: 50 | Audio Input: 0 | Output: 50 | Audio Output: 0\n"
        )
        result = parse_cost_summary(stdout)
        # The pattern won't match because Cache Read is absent.
        assert result["total_tokens"] == 0
        assert result["input_tokens"] == 0
        assert result["output_tokens"] == 0
        assert result["cache_read_tokens"] == 0


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
            def validate(self, output_dir, log_content, trace=None):
                calls.append((output_dir, log_content))
                return ValidationResult(status="PASS", score=1.0, details=[])

        (case_dir / "validator.py").write_text(
            "from pathlib import Path\n"
            "from zrb_llm_evaluator.models import ValidationResult, ValidationCheck\n"
            "class TV:\n"
            "    def validate(self, output_dir, log_content, trace=None):\n"
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
    async def test_validator_receives_log_content(
        self, tmp_path: Path
    ) -> None:
        """UT-011: Validator receives the expected output text in log_content."""
        case_dir = tmp_path / "log-case"
        case_dir.mkdir(parents=True, exist_ok=True)
        expected_output = "Hello"
        (case_dir / "instruction.txt").write_text("Hello", encoding="utf-8")

        captured_log = None
        class LogCapturingValidator:
            def validate(self, output_dir, log_content, trace=None):
                nonlocal captured_log
                captured_log = log_content
                return ValidationResult(status="PASS", score=1.0, details=[])

        (case_dir / "validator.py").write_text(
            "from pathlib import Path\n"
            "from zrb_llm_evaluator.models import ValidationResult, ValidationCheck\n"
            "class LCV:\n"
            "    def validate(self, output_dir, log_content, trace=None):\n"
            "        return ValidationResult(status='PASS', score=1.0, details=[])\n"
            "validator = LCV()\n"
        )

        from zrb_llm_evaluator.loader import load_test_case
        tc = load_test_case(case_dir)
        tc.validator = LogCapturingValidator()  # type: ignore[assignment]

        config = ExperimentConfig(
            models=["openai:gpt-4o"],
            test_case_dirs=[case_dir],
            trials=1,
            parallelism=1,
            timeout=30,
            cli_name="echo",  # echo outputs the arguments
        )
        output_dir = tmp_path / "out"

        runner = TrialRunner(config, tc, output_dir)
        result = await runner.run("openai:gpt-4o", 1)

        assert result.status == "PASS", f"Expected PASS, got {result.status}"
        assert captured_log is not None, "Validator was not called"
        assert expected_output in captured_log, (
            f"Expected {expected_output!r} in log_content, got {captured_log!r}"
        )

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
            def validate(self, output_dir, log_content, trace=None):
                msg = "bad check"
                raise ValueError(msg)

        sample_test_case.validator = BrokenValidator()  # type: ignore[assignment]

        with patch.object(asyncio, "create_subprocess_exec", _mock_subprocess(mock_proc)):
            runner = TrialRunner(config, sample_test_case, output_dir)
            result = await runner.run("openai:gpt-4o", 1)

        assert result.status == "ERROR"
        assert result.verification_result is not None
        assert len(result.verification_result.details) == 1
        assert result.verification_result.details[0].name == "validator_error"
        assert "bad check" in result.verification_result.details[0].message

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

        # Mock proc.wait to raise asyncio.TimeoutError to drive the runner's
        # timeout branch (runner uses `await asyncio.wait_for(proc.wait(), ...)`).
        mock_proc = AsyncMock()
        # First wait() raises TimeoutError (drives the timeout branch);
        # second wait() (called after the group kill to reap) returns cleanly.
        mock_proc.wait = AsyncMock(side_effect=[asyncio.TimeoutError, 0])
        mock_proc.kill = Mock()
        mock_proc.pid = 12345

        async def mock_create_subprocess_exec(*args: object, **kwargs: object) -> AsyncMock:
            return mock_proc

        with patch.object(asyncio, "create_subprocess_exec", mock_create_subprocess_exec), \
                patch.object(os, "getpgid", return_value=12345), \
                patch.object(os, "killpg", Mock()):
            runner = TrialRunner(config, sample_test_case, output_dir)
            result = await runner.run("openai:gpt-4o", 1)

        assert result.status == "TIMEOUT"
        assert result.log_path != ""
        # log_path points to zrb history JSON; on timeout the file may not exist yet
        assert result.log_path.endswith(".json")
        assert "history" in result.log_path

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


class TestWorkStewardParallel:
    """Tests for WorkSteward parallel execution — @sdlc REQ-002, REQ-010."""

    @pytest.mark.asyncio
    async def test_parallel_execution_work_steward(
        self, tmp_path: Path,
    ) -> None:
        """UT-056: 3 models x 1 case x 2 trials = 6 cells, parallelism=3.

        Verifies WorkSteward bounded concurrency: all 6 results have terminal
        statuses and results.json has 6 entries.
        """
        case_dir = tmp_path / "p-case"
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "instruction.txt").write_text("Test", encoding="utf-8")
        (case_dir / "validator.py").write_text(
            "from pathlib import Path\n"
            "from zrb_llm_evaluator.models import ValidationResult, ValidationCheck\n"
            "class V:\n"
            "    def validate(self, output_dir, log_content, trace=None):\n"
            "        return ValidationResult(status='PASS', score=0.9, details=[])\n"
            "validator = V()\n"
        )

        from zrb_llm_evaluator.loader import load_test_case

        tc = load_test_case(case_dir)

        config = ExperimentConfig(
            models=["test:m1", "test:m2", "test:m3"],
            test_case_dirs=[case_dir],
            trials=2,
            parallelism=3,
            timeout=30,
            cli_name="echo",
        )
        output_dir = tmp_path / "out"
        results_path = output_dir / "results.json"
        mgr = ResumeManager(results_path)
        steward = WorkSteward(config, [tc], output_dir, mgr)

        results = await steward.run_all()

        assert len(results) == 6

        terminal_statuses = {"EXCELLENT", "PASS", "FAIL", "TIMEOUT", "ERROR"}
        for r in results:
            assert r.status in terminal_statuses, (
                f"Non-terminal status: {r.status}"
            )

        assert results_path.exists()
        data = json.loads(results_path.read_text(encoding="utf-8"))
        assert len(data) == 6
