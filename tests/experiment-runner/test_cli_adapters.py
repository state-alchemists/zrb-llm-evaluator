# COVERS: EXPERIMENT-RUNNER:REQ-035, EXPERIMENT-RUNNER:REQ-036, EXPERIMENT-RUNNER:REQ-037,
# COVERS: EXPERIMENT-RUNNER:REQ-038, EXPERIMENT-RUNNER:REQ-039, EXPERIMENT-RUNNER:REQ-040,
# COVERS: EXPERIMENT-RUNNER:REQ-041, EXPERIMENT-RUNNER:REQ-042,
# COVERS: EXPERIMENT-RUNNER:UT-060, EXPERIMENT-RUNNER:UT-061, EXPERIMENT-RUNNER:UT-062,
# COVERS: EXPERIMENT-RUNNER:UT-063, EXPERIMENT-RUNNER:UT-064, EXPERIMENT-RUNNER:UT-065,
# COVERS: EXPERIMENT-RUNNER:UT-066, EXPERIMENT-RUNNER:UT-067, EXPERIMENT-RUNNER:UT-068,
# COVERS: EXPERIMENT-RUNNER:UT-069, EXPERIMENT-RUNNER:UT-070, EXPERIMENT-RUNNER:UT-071,
# COVERS: EXPERIMENT-RUNNER:UT-072

"""Tests for CliAdapter implementations and cli_template resolution."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from zrb_llm_evaluator.cli_adapters import (
    ClaudeCodeCliAdapter,
    OpencodeCliAdapter,
    ZrbCliAdapter,
    resolve_cli_adapter,
)
from zrb_llm_evaluator.models import ExperimentConfig, UsageSummary
from zrb_llm_evaluator.runner import ResumeManager, TrialRunner, WorkSteward


def _mock_subprocess(mock_proc: AsyncMock):
    """Return an async function that returns the given mock_proc."""

    async def _create(*args: object, **kwargs: object) -> AsyncMock:
        return mock_proc

    return _create


class _StubAdapter:
    """Directly-injectable CliAdapter stub for REQ-039 unit tests."""

    def __init__(self, usage: UsageSummary, tool_calls: tuple[list[str], int]) -> None:
        self._usage = usage
        self._tool_calls = tool_calls

    def build_argv(
        self, cli_name: str, model: str, instruction: str, session_name: str,
    ) -> list[str]:
        """Return a trivial argv."""
        return [cli_name, "stub", instruction, "--model", model]

    def build_env(
        self,
        base_env: dict[str, str],
        history_dir: Path,
        journal_dir: Path,
        env_prefix: str,
    ) -> dict[str, str]:
        """Pass the base environment through unchanged."""
        return dict(base_env)

    def history_log_path(self, history_dir: Path, session_name: str) -> Path:
        """Return a fixed history file path."""
        return history_dir / f"{session_name}.json"

    def parse_usage(self, stdout: str) -> UsageSummary:
        """Return the pre-configured usage summary."""
        return self._usage

    def extract_tool_calls(self, history_log_path: Path) -> tuple[list[str], int]:
        """Return the pre-configured tool-call tuple."""
        return self._tool_calls


class TestResolveBuiltinAdapters:
    """Built-in name resolution — @sdlc EXPERIMENT-RUNNER:REQ-035, EXPERIMENT-RUNNER:REQ-036."""

    def test_resolve_zrb_returns_zrb_adapter(self) -> None:
        """Built-in ``"zrb"`` resolves to ``ZrbCliAdapter``."""
        adapter = resolve_cli_adapter("zrb")
        assert isinstance(adapter, ZrbCliAdapter)

    def test_resolve_claude_code_returns_claude_code_adapter(self) -> None:
        """Built-in ``"claude-code"`` resolves to ``ClaudeCodeCliAdapter``."""
        adapter = resolve_cli_adapter("claude-code")
        assert isinstance(adapter, ClaudeCodeCliAdapter)

    def test_resolve_opencode_returns_opencode_adapter(self) -> None:
        """Built-in ``"opencode"`` resolves to ``OpencodeCliAdapter``."""
        adapter = resolve_cli_adapter("opencode")
        assert isinstance(adapter, OpencodeCliAdapter)


class TestAdapterSelectedByCliTemplate:
    """TrialRunner adapter resolution — @sdlc EXPERIMENT-RUNNER:REQ-035."""

    @pytest.mark.asyncio
    async def test_adapter_selected_by_cli_template(
        self, tmp_path: Path, sample_test_case,
    ) -> None:
        """EXPERIMENT-RUNNER:UT-060: cli_template="zrb" -> TrialRunner uses ZrbCliAdapter."""
        config = ExperimentConfig(
            models=["openai:gpt-4o"],
            test_case_dirs=[tmp_path],
            trials=1,
            parallelism=1,
            timeout=30,
            cli_template="zrb",
        )
        output_dir = tmp_path / "out"
        runner = TrialRunner(config, sample_test_case, output_dir)
        assert isinstance(runner._cli_adapter, ZrbCliAdapter)  # noqa: SLF001

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"Output", b""))
        mock_proc.returncode = 0
        with patch.object(asyncio, "create_subprocess_exec") as mock_exec:
            mock_exec.return_value = mock_proc
            await runner.run("openai:gpt-4o", 1)

        call_args = mock_exec.call_args[0]
        assert call_args[0] == "zrb"
        assert "chat" in call_args


class TestDefaultCliTemplateIsZrb:
    """Default template behavior — @sdlc EXPERIMENT-RUNNER:REQ-036."""

    def test_default_cli_template_field(self) -> None:
        """``ExperimentConfig()`` with no ``cli_template`` defaults to ``"zrb"``."""
        config = ExperimentConfig(
            models=["openai:gpt-4o"], test_case_dirs=[Path("/tmp/fake-case")], trials=1,
        )
        assert config.cli_template == "zrb"

    @pytest.mark.asyncio
    async def test_default_cli_template_matches_pre_feature_behavior(
        self, tmp_path: Path, sample_test_case,
    ) -> None:
        """EXPERIMENT-RUNNER:UT-061: argv/env/parsed usage match the pre-feature runner."""
        config = ExperimentConfig(
            models=["openai:gpt-4o"],
            test_case_dirs=[tmp_path],
            trials=1,
            parallelism=1,
            timeout=30,
        )
        assert config.cli_template == "zrb"
        output_dir = tmp_path / "out"

        stdout_bytes = (
            "💸 (Requests: 1 | Tool Calls: 0 | Total: 150) "
            "Input: 100 | Audio Input: 0 | Output: 50 | Audio Output: 0 | "
            "Cache Read: 0 | Cache Write: 0 | Details: {}\n"
        ).encode("utf-8")

        async def writing_create(*args: object, **kwargs: object) -> AsyncMock:
            log_file = kwargs.get("stdout")
            if log_file is not None:
                log_file.write(stdout_bytes)  # type: ignore[union-attr]
                log_file.flush()  # type: ignore[union-attr]
            proc = AsyncMock()
            proc.wait = AsyncMock(return_value=0)
            proc.returncode = 0
            return proc

        captured: dict[str, object] = {}

        async def capturing_create(*args: object, **kwargs: object) -> AsyncMock:
            captured["args"] = args
            captured["kwargs"] = kwargs
            return await writing_create(*args, **kwargs)

        with patch.object(asyncio, "create_subprocess_exec", capturing_create):
            runner = TrialRunner(config, sample_test_case, output_dir)
            result = await runner.run("openai:gpt-4o", 1)

        # Same argv shape as pre-feature (UT-014/UT-019).
        args = captured["args"]
        assert args[0] == "zrb"  # type: ignore[index]
        assert "chat" in args  # type: ignore[operator]
        assert "--session" in args  # type: ignore[operator]
        env = captured["kwargs"]["env"]  # type: ignore[index]
        assert "ZRB_LLM_HISTORY_DIR" in env  # type: ignore[operator]
        assert "ZRB_LLM_JOURNAL_DIR" in env  # type: ignore[operator]
        # Same usage parsing as pre-feature (UT-022).
        assert result.total_tokens == 150
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.cache_read_tokens == 0


class TestCustomAdapterDottedPath:
    """Dotted-path custom adapters — @sdlc EXPERIMENT-RUNNER:REQ-037."""

    def test_resolve_custom_adapter_from_dotted_path(self) -> None:
        """``resolve_cli_adapter`` imports and instantiates a dotted-path class."""
        from tests.fixtures.custom_adapter import FakeAdapter

        adapter = resolve_cli_adapter("tests.fixtures.custom_adapter.FakeAdapter")
        assert isinstance(adapter, FakeAdapter)

    @pytest.mark.asyncio
    async def test_custom_adapter_loaded_from_dotted_path(
        self, tmp_path: Path, sample_test_case,
    ) -> None:
        """EXPERIMENT-RUNNER:UT-062: dotted-path adapter builds argv/env and parses output."""
        from tests.fixtures import custom_adapter

        custom_adapter.CALLS.clear()
        config = ExperimentConfig(
            models=["openai:gpt-4o"],
            test_case_dirs=[tmp_path],
            trials=1,
            parallelism=1,
            timeout=30,
            cli_template="tests.fixtures.custom_adapter.FakeAdapter",
        )
        output_dir = tmp_path / "out"

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"Output", b""))
        mock_proc.returncode = 0
        with patch.object(asyncio, "create_subprocess_exec") as mock_exec:
            mock_exec.return_value = mock_proc
            runner = TrialRunner(config, sample_test_case, output_dir)
            result = await runner.run("openai:gpt-4o", 1)

        call_args = mock_exec.call_args[0]
        assert call_args[0] == "zrb"  # cli_name, independent of cli_template
        assert "fake-run" in call_args
        assert result.total_tokens == 7
        assert result.input_tokens == 5
        assert result.output_tokens == 2
        assert result.tool_calls == ["fake_tool"]
        assert result.tool_call_count == 1
        assert "build_argv" in custom_adapter.CALLS
        assert "build_env" in custom_adapter.CALLS
        assert "parse_usage" in custom_adapter.CALLS
        assert "extract_tool_calls" in custom_adapter.CALLS


class TestInvalidCliTemplateRejected:
    """Fail-fast on a bad cli_template — @sdlc EXPERIMENT-RUNNER:REQ-038."""

    def test_unknown_cli_template_rejected(self) -> None:
        """EXPERIMENT-RUNNER:UT-063: an unknown, non-dotted name is rejected."""
        with pytest.raises(ValueError, match="Unknown cli_template"):
            resolve_cli_adapter("not-a-real-template")

    @pytest.mark.asyncio
    async def test_unknown_cli_template_rejected_before_any_trial(
        self, tmp_path: Path, sample_test_case,
    ) -> None:
        """EXPERIMENT-RUNNER:UT-063: TrialRunner construction fails before any subprocess runs."""
        config = ExperimentConfig(
            models=["openai:gpt-4o"],
            test_case_dirs=[tmp_path],
            trials=1,
            parallelism=1,
            timeout=30,
            cli_template="not-a-real-template",
        )
        output_dir = tmp_path / "out"
        with patch.object(asyncio, "create_subprocess_exec") as mock_exec:
            with pytest.raises(ValueError):
                TrialRunner(config, sample_test_case, output_dir)
            mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_worksteward_rejects_before_any_cell_runs(
        self, tmp_path: Path, sample_test_case,
    ) -> None:
        """EXPERIMENT-RUNNER:UT-063: WorkSteward resolves (and can fail) before scheduling cells."""
        config = ExperimentConfig(
            models=["openai:gpt-4o"],
            test_case_dirs=[tmp_path],
            trials=2,
            parallelism=2,
            timeout=30,
            cli_template="not-a-real-template",
        )
        output_dir = tmp_path / "out"
        results_path = output_dir / "results.json"
        mgr = ResumeManager(results_path)
        with patch.object(asyncio, "create_subprocess_exec") as mock_exec:
            with pytest.raises(ValueError):
                WorkSteward(config, [sample_test_case], output_dir, mgr)
            mock_exec.assert_not_called()

    def test_dotted_path_not_implementing_protocol_rejected(self) -> None:
        """EXPERIMENT-RUNNER:UT-064: a dotted path missing required methods is rejected."""
        with pytest.raises(ValueError, match="does not implement the CliAdapter protocol"):
            resolve_cli_adapter("tests.fixtures.incomplete_adapter.IncompleteAdapter")

    def test_dotted_path_bad_module_rejected(self) -> None:
        """An unimportable module path is rejected with a clear error."""
        with pytest.raises(ValueError, match="Cannot import module"):
            resolve_cli_adapter("tests.fixtures.does_not_exist.Whatever")

    def test_dotted_path_module_raising_at_import_rejected(self) -> None:
        """A module raising a non-ImportError at import time still yields ValueError."""
        with pytest.raises(ValueError, match="Cannot import module"):
            resolve_cli_adapter("tests.fixtures.broken_adapter.Whatever")

    def test_dotted_path_bad_class_name_rejected(self) -> None:
        """An importable module missing the named class is rejected with a clear error."""
        with pytest.raises(ValueError, match="has no attribute"):
            resolve_cli_adapter("tests.fixtures.custom_adapter.NoSuchClass")


class TestUsageAndToolCallsFromAdapter:
    """TrialResult population from adapter output — @sdlc EXPERIMENT-RUNNER:REQ-039."""

    @pytest.mark.asyncio
    async def test_token_fields_from_adapter_parse_usage(
        self, tmp_path: Path, sample_test_case,
    ) -> None:
        """EXPERIMENT-RUNNER:UT-065: token fields come exclusively from parse_usage."""
        config = ExperimentConfig(
            models=["openai:gpt-4o"], test_case_dirs=[tmp_path], trials=1,
            parallelism=1, timeout=30,
        )
        output_dir = tmp_path / "out"
        adapter = _StubAdapter(
            UsageSummary(total_tokens=42, input_tokens=30, output_tokens=12, cache_read_tokens=0),
            ([], 0),
        )
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0
        with patch.object(asyncio, "create_subprocess_exec", _mock_subprocess(mock_proc)):
            runner = TrialRunner(config, sample_test_case, output_dir, adapter)
            result = await runner.run("openai:gpt-4o", 1)

        assert result.total_tokens == 42
        assert result.input_tokens == 30
        assert result.output_tokens == 12
        assert result.cache_read_tokens == 0

    @pytest.mark.asyncio
    async def test_tool_calls_from_adapter_extract_tool_calls(
        self, tmp_path: Path, sample_test_case,
    ) -> None:
        """EXPERIMENT-RUNNER:UT-066: tool_calls/tool_call_count come from extract_tool_calls."""
        config = ExperimentConfig(
            models=["openai:gpt-4o"], test_case_dirs=[tmp_path], trials=1,
            parallelism=1, timeout=30,
        )
        output_dir = tmp_path / "out"
        adapter = _StubAdapter(UsageSummary(), (["read", "write"], 2))
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0
        with patch.object(asyncio, "create_subprocess_exec", _mock_subprocess(mock_proc)):
            runner = TrialRunner(config, sample_test_case, output_dir, adapter)
            result = await runner.run("openai:gpt-4o", 1)

        assert result.tool_calls == ["read", "write"]
        assert result.tool_call_count == 2

    @pytest.mark.asyncio
    async def test_adapter_usage_defaults_when_unavailable(
        self, tmp_path: Path, sample_test_case,
    ) -> None:
        """EXPERIMENT-RUNNER:UT-067: all-zero/empty adapter output preserves zero/[] defaults."""
        config = ExperimentConfig(
            models=["openai:gpt-4o"], test_case_dirs=[tmp_path], trials=1,
            parallelism=1, timeout=30,
        )
        output_dir = tmp_path / "out"
        adapter = _StubAdapter(UsageSummary(), ([], 0))
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0
        with patch.object(asyncio, "create_subprocess_exec", _mock_subprocess(mock_proc)):
            runner = TrialRunner(config, sample_test_case, output_dir, adapter)
            result = await runner.run("openai:gpt-4o", 1)

        assert result.total_tokens == 0
        assert result.input_tokens == 0
        assert result.output_tokens == 0
        assert result.cache_read_tokens == 0
        assert result.tool_calls == []
        assert result.tool_call_count == 0


class TestClaudeCodeAdapter:
    """ClaudeCodeCliAdapter unit tests.

    @sdlc EXPERIMENT-RUNNER:REQ-040, EXPERIMENT-RUNNER:REQ-041
    """

    def test_claude_code_history_written_under_cell_history_dir(self, tmp_path: Path) -> None:
        """EXPERIMENT-RUNNER:UT-068: history_log_path lives inside cell_dir/history/."""
        adapter = ClaudeCodeCliAdapter()
        history_dir = tmp_path / "cell" / "history"
        path = adapter.history_log_path(history_dir, "session-1")
        assert path.parent == history_dir
        assert path.name == "session-1.json"

    def test_claude_code_argv_uses_print_mode(self) -> None:
        """EXPERIMENT-RUNNER:UT-069: argv contains the print flag and JSON-output flag."""
        adapter = ClaudeCodeCliAdapter()
        argv = adapter.build_argv(
            "claude", "anthropic:claude-3-5-sonnet", "do the thing", "sess-1",
        )
        assert argv[0] == "claude"
        assert "-p" in argv
        assert "--output-format" in argv
        # stream-json (not plain json): tool calls are only observable in
        # the event stream, and stream-json in print mode needs --verbose.
        assert "stream-json" in argv
        assert "--verbose" in argv
        # Counterpart of zrb's --yolo true; without it print mode denies
        # every tool request.
        assert "--dangerously-skip-permissions" in argv
        assert "do the thing" in argv
        assert "anthropic:claude-3-5-sonnet" in argv

    def test_claude_code_parses_usage_from_json_output(self) -> None:
        """EXPERIMENT-RUNNER:UT-070: UsageSummary matches the JSON usage block's counts."""
        adapter = ClaudeCodeCliAdapter()
        stdout = json.dumps({
            "type": "result",
            "subtype": "success",
            "result": "done",
            "session_id": "abc",
            "usage": {
                "input_tokens": 120,
                "output_tokens": 80,
                "cache_read_input_tokens": 10,
            },
        })
        usage = adapter.parse_usage(stdout)
        assert usage.input_tokens == 120
        assert usage.output_tokens == 80
        assert usage.cache_read_tokens == 10
        assert usage.total_tokens == 210

    def test_claude_code_parses_usage_missing_defaults_zero(self) -> None:
        """No usage block in stdout -> UsageSummary defaults to zero."""
        adapter = ClaudeCodeCliAdapter()
        usage = adapter.parse_usage("not json at all")
        assert usage.total_tokens == 0
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.cache_read_tokens == 0

    def test_claude_code_parses_usage_despite_surrounding_noise(self) -> None:
        """Noise before AND after the JSON payload is tolerated.

        The runner merges stderr into the captured stream, so log lines can
        trail the payload; regression test for the parser requiring the
        JSON to end the stream.
        """
        adapter = ClaudeCodeCliAdapter()
        payload = json.dumps({
            "type": "result",
            "usage": {
                "input_tokens": 120,
                "output_tokens": 80,
                "cache_read_input_tokens": 10,
                "cache_creation_input_tokens": 5,
            },
        })
        stdout = f"some startup log line\n{payload}\nWARNING: stderr line at exit\n"
        usage = adapter.parse_usage(stdout)
        assert usage.input_tokens == 120
        assert usage.output_tokens == 80
        assert usage.cache_read_tokens == 10
        # cache_creation counts toward the total.
        assert usage.total_tokens == 215

    def test_claude_code_extracts_tool_uses(self, tmp_path: Path) -> None:
        """tool_use content blocks in the stream-json snapshot become tool names."""
        adapter = ClaudeCodeCliAdapter()
        history_path = tmp_path / "sess.json"
        stream = "\n".join([
            json.dumps({"type": "system", "subtype": "init"}),
            json.dumps({
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "on it"},
                        {"type": "tool_use", "name": "Read", "input": {}},
                    ],
                },
            }),
            json.dumps({
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "name": "Edit", "input": {}}],
                },
            }),
            json.dumps({"type": "result", "usage": {"input_tokens": 1}}),
        ])
        history_path.write_text(stream, encoding="utf-8")
        names, count = adapter.extract_tool_calls(history_path)
        assert names == ["Read", "Edit"]
        assert count == 2

    def test_claude_code_missing_history_file_returns_empty(self, tmp_path: Path) -> None:
        """Missing history snapshot -> empty tool-call list, defensively."""
        adapter = ClaudeCodeCliAdapter()
        names, count = adapter.extract_tool_calls(tmp_path / "nope.json")
        assert names == []
        assert count == 0


def _opencode_step_finish(
    input_tokens: int,
    output_tokens: int,
    reasoning: int = 0,
    cache_read: int = 0,
    cache_write: int = 0,
) -> str:
    """Build one opencode ``step_finish`` NDJSON event line."""
    return json.dumps({
        "type": "step_finish",
        "sessionID": "ses_1",
        "part": {
            "type": "step-finish",
            "reason": "stop",
            "cost": 0,
            "tokens": {
                "input": input_tokens,
                "output": output_tokens,
                "reasoning": reasoning,
                "cache": {"read": cache_read, "write": cache_write},
            },
        },
    })


class TestOpencodeAdapter:
    """OpencodeCliAdapter unit tests — @sdlc EXPERIMENT-RUNNER:REQ-042."""

    def test_opencode_argv_uses_run_mode(self) -> None:
        """EXPERIMENT-RUNNER:UT-071: argv starts with cli_name, then the run subcommand."""
        adapter = OpencodeCliAdapter()
        argv = adapter.build_argv("opencode", "openai:gpt-4o", "write a poem", "sess-1")
        assert argv[0] == "opencode"
        assert argv[1] == "run"
        assert "write a poem" in argv
        # opencode's --model expects provider/model, not provider:name.
        assert "openai/gpt-4o" in argv
        assert "--format" in argv
        assert "json" in argv
        # --session continues an EXISTING session id (exits 1 for a fresh
        # one), so the trial's session name goes in --title instead.
        assert "--session" not in argv
        assert "--title" in argv
        assert "sess-1" in argv
        assert "--dangerously-skip-permissions" in argv

    def test_opencode_parses_usage_from_step_finish_events(self) -> None:
        """EXPERIMENT-RUNNER:UT-072: UsageSummary sums step_finish token counts."""
        adapter = OpencodeCliAdapter()
        stdout = "\n".join([
            json.dumps({"type": "text", "part": {"type": "text", "text": "hi"}}),
            _opencode_step_finish(30, 15, cache_read=5),
            _opencode_step_finish(10, 5, reasoning=2, cache_write=3),
        ])
        usage = adapter.parse_usage(stdout)
        assert usage.input_tokens == 40
        assert usage.output_tokens == 20
        assert usage.cache_read_tokens == 5
        # total includes reasoning and cache-write tokens too.
        assert usage.total_tokens == 70

    def test_opencode_parses_usage_missing_defaults_zero(self) -> None:
        """No recognizable usage summary in stdout -> UsageSummary defaults to zero."""
        adapter = OpencodeCliAdapter()
        usage = adapter.parse_usage("no usage info here")
        assert usage.total_tokens == 0
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.cache_read_tokens == 0

    def test_opencode_extracts_tool_calls_from_tool_use_events(
        self, tmp_path: Path,
    ) -> None:
        """tool_use events in the NDJSON snapshot become tool names."""
        adapter = OpencodeCliAdapter()
        history_path = tmp_path / "sess.json"
        stream = "\n".join([
            json.dumps({
                "type": "tool_use",
                "part": {"type": "tool", "tool": "read", "state": {"status": "completed"}},
            }),
            _opencode_step_finish(10, 5),
            json.dumps({
                "type": "tool_use",
                "part": {"type": "tool", "tool": "edit", "state": {"status": "completed"}},
            }),
        ])
        history_path.write_text(stream, encoding="utf-8")
        names, count = adapter.extract_tool_calls(history_path)
        assert names == ["read", "edit"]
        assert count == 2


class TestHistorySnapshotFallback:
    """Runner-side history snapshot fallback.

    @sdlc EXPERIMENT-RUNNER:REQ-008, EXPERIMENT-RUNNER:REQ-040
    """

    @pytest.mark.asyncio
    async def test_claude_code_snapshot_written_when_adapter_does_not_write_history(
        self, tmp_path: Path, sample_test_case,
    ) -> None:
        """The runner snapshots captured stdout to history_log_path for claude-code."""
        config = ExperimentConfig(
            models=["anthropic:claude-3-5-sonnet"],
            test_case_dirs=[tmp_path],
            trials=1,
            parallelism=1,
            timeout=30,
            cli_name="claude",
            cli_template="claude-code",
        )
        output_dir = tmp_path / "out"
        payload = "\n".join([
            json.dumps({
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "name": "Read", "input": {}},
                        {"type": "tool_use", "name": "Edit", "input": {}},
                    ],
                },
            }),
            json.dumps({
                "type": "result",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_read_input_tokens": 0,
                },
            }),
        ]).encode("utf-8")

        async def writing_create(*args: object, **kwargs: object) -> AsyncMock:
            log_file = kwargs.get("stdout")
            if log_file is not None:
                log_file.write(payload)  # type: ignore[union-attr]
                log_file.flush()  # type: ignore[union-attr]
            proc = AsyncMock()
            proc.wait = AsyncMock(return_value=0)
            proc.returncode = 0
            return proc

        with patch.object(asyncio, "create_subprocess_exec", writing_create):
            runner = TrialRunner(config, sample_test_case, output_dir)
            result = await runner.run("anthropic:claude-3-5-sonnet", 1)

        history_path = Path(result.log_path)
        assert history_path.is_file()
        assert result.total_tokens == 15
        assert result.tool_calls == ["Read", "Edit"]
        assert result.tool_call_count == 2
