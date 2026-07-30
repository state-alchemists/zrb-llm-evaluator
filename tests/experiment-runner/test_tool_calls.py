# COVERS: EXPERIMENT-RUNNER:REQ-019, EXPERIMENT-RUNNER:REQ-043,
# COVERS: EXPERIMENT-RUNNER:REQ-045, EXPERIMENT-RUNNER:UT-026

"""Tests for tool-call extraction from zrb history JSON."""

from __future__ import annotations

import json
from pathlib import Path

from zrb_llm_evaluator.cost_parser import (
    count_tool_calls_from_history,
    detect_provider_error,
    extract_tool_calls_from_history,
    extract_tool_calls_from_zrb_stdout,
)


class TestToolCallExtraction:
    """Tests for extracting tool-call names from history JSON — @sdlc EXPERIMENT-RUNNER:REQ-019."""

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """EXPERIMENT-RUNNER:UT-026: Missing history file => empty list, count 0."""
        names, count = count_tool_calls_from_history(tmp_path / "nope.json")
        assert names == []
        assert count == 0

    def test_malformed_json_returns_empty(self, tmp_path: Path) -> None:
        """EXPERIMENT-RUNNER:UT-026: Corrupt JSON => empty list (defensive)."""
        p = tmp_path / "broken.json"
        p.write_text("{not json", encoding="utf-8")
        names, count = count_tool_calls_from_history(p)
        assert names == []
        assert count == 0

    def test_list_with_tool_name(self, tmp_path: Path) -> None:
        """EXPERIMENT-RUNNER:UT-026: Bare-list shape with ``tool_name`` entries."""
        p = tmp_path / "h.json"
        data = [
            {"role": "user", "content": "hi"},
            {"tool_name": "read_file"},
            {"tool_name": "write_file"},
            {"role": "assistant", "content": "done"},
        ]
        p.write_text(json.dumps(data), encoding="utf-8")
        names = extract_tool_calls_from_history(p)
        assert names == ["read_file", "write_file"]
        _, count = count_tool_calls_from_history(p)
        assert count == 2

    def test_nested_tool_call(self, tmp_path: Path) -> None:
        """EXPERIMENT-RUNNER:UT-026: ``tool_call.name`` nested form is recognised."""
        p = tmp_path / "h.json"
        data = [
            {"tool_call": {"name": "run_python", "args": {}}},
            {"tool_call": {"name": "shell", "args": {}}},
        ]
        p.write_text(json.dumps(data), encoding="utf-8")
        names = extract_tool_calls_from_history(p)
        assert names == ["run_python", "shell"]

    def test_history_wrapped_in_dict(self, tmp_path: Path) -> None:
        """EXPERIMENT-RUNNER:UT-026: ``{\"history\": [...]}`` wrapper is supported."""
        p = tmp_path / "h.json"
        data = {"history": [{"tool_name": "alpha"}, {"tool_name": "beta"}]}
        p.write_text(json.dumps(data), encoding="utf-8")
        names = extract_tool_calls_from_history(p)
        assert names == ["alpha", "beta"]

    def test_unexpected_shape_returns_empty(self, tmp_path: Path) -> None:
        """EXPERIMENT-RUNNER:UT-026: Top-level scalar JSON => empty."""
        p = tmp_path / "h.json"
        p.write_text(json.dumps("just a string"), encoding="utf-8")
        names = extract_tool_calls_from_history(p)
        assert names == []

    def test_entries_without_tool_name_skipped(self, tmp_path: Path) -> None:
        """EXPERIMENT-RUNNER:UT-026: Non-tool entries are skipped, no error."""
        p = tmp_path / "h.json"
        data = [
            {"role": "user", "content": "x"},
            {"role": "assistant", "content": "y"},
        ]
        p.write_text(json.dumps(data), encoding="utf-8")
        names, count = count_tool_calls_from_history(p)
        assert names == []
        assert count == 0

    def test_role_tool_with_name(self, tmp_path: Path) -> None:
        """EXPERIMENT-RUNNER:UT-026: ``role=tool`` with ``name`` field also counted."""
        p = tmp_path / "h.json"
        data = [
            {"role": "tool", "name": "search"},
            {"role": "assistant", "content": "ok"},
        ]
        p.write_text(json.dumps(data), encoding="utf-8")
        names = extract_tool_calls_from_history(p)
        assert names == ["search"]

    def test_pydantic_ai_parts_shape(self, tmp_path: Path) -> None:
        """EXPERIMENT-RUNNER:UT-026: pydantic-ai ``parts[]`` with ``part_kind=tool-call`` is recognised.

        A single message can hold multiple parallel tool calls; all are returned.
        """
        p = tmp_path / "h.json"
        data = [
            {"parts": [{"part_kind": "user-prompt", "content": "hi"}]},
            {
                "parts": [
                    {"part_kind": "text", "content": "(tool call)"},
                    {"part_kind": "tool-call", "tool_name": "Read", "args": "{}"},
                    {"part_kind": "tool-call", "tool_name": "Grep", "args": "{}"},
                ],
            },
            {
                "parts": [
                    {"part_kind": "tool-return", "tool_name": "Read", "content": "..."},
                ],
            },
            {
                "parts": [
                    {"part_kind": "tool-call", "tool_name": "Edit", "args": "{}"},
                ],
            },
        ]
        p.write_text(json.dumps(data), encoding="utf-8")
        names, count = count_tool_calls_from_history(p)
        assert names == ["Read", "Grep", "Edit"]
        assert count == 3


class TestConsoleStreamFallback:
    """Recover tool calls when no history JSON exists — @sdlc EXPERIMENT-RUNNER:REQ-043."""

    # zrb's console format, ANSI escapes included, as streamed to the log.
    _CONSOLE = (
        "\x1b[2m\n  \U0001f504 Prepare tool parameters...\x1b[0m\x1b[2m\n"
        "  \U0001f9f0 dkhjh1nc | LS {}\n\x1b[0m\x1b[2m\n"
        "  \U0001f520 dkhjh1nc Executed\n\x1b[0m\x1b[2m\n"
        "  \U0001f9f0 4104giut | Read {'path': '/tmp/x.py'}\n\x1b[0m\n"
        "  \U0001f9f0 zz11aa22 | ActivateSkill {'skill': 'core-coding'}\n"
    )

    def test_parses_tool_names_from_console_stream(self) -> None:
        """Names come from between the call id and the argument dict."""
        assert extract_tool_calls_from_zrb_stdout(self._CONSOLE) == [
            "LS", "Read", "ActivateSkill",
        ]

    def test_no_tool_calls_yields_empty(self) -> None:
        """Console text without invocations yields nothing, not a spurious name."""
        assert extract_tool_calls_from_zrb_stdout("just some prose\nand a line") == []

    def test_history_falls_back_when_content_is_not_json(self, tmp_path: Path) -> None:
        """A SIGKILLed timeout leaves the console stream at the history path.

        The runner snapshots stdout there when zrb never wrote its JSON, so the
        trial must not be reported as having made zero tool calls.
        """
        p = tmp_path / "history.json"
        p.write_text(self._CONSOLE, encoding="utf-8")

        names, count = count_tool_calls_from_history(p)

        assert names == ["LS", "Read", "ActivateSkill"]
        assert count == 3

    def test_valid_json_history_still_wins(self, tmp_path: Path) -> None:
        """The fallback must not shadow a real history JSON."""
        p = tmp_path / "history.json"
        p.write_text(
            json.dumps([{"parts": [{"part_kind": "tool-call", "tool_name": "Edit"}]}]),
            encoding="utf-8",
        )
        assert count_tool_calls_from_history(p) == (["Edit"], 1)

    def test_empty_history_json_stays_empty(self, tmp_path: Path) -> None:
        """Valid JSON with no tool calls yields nothing — no false positives."""
        p = tmp_path / "history.json"
        p.write_text("[]", encoding="utf-8")
        assert count_tool_calls_from_history(p) == ([], 0)


class TestProviderErrorDetection:
    """Separate infrastructure failures from model failures — @sdlc EXPERIMENT-RUNNER:REQ-045."""

    def test_quota_exhaustion_is_reported(self) -> None:
        """The provider's own phrasing, as emitted through zrb's retry loop."""
        text = (
            "[ERROR] Attempt 1/3 failed: You exceeded your current quota, "
            "please check your plan and billing details."
        )
        assert detect_provider_error(text) == "quota_exceeded"

    def test_resource_exhausted_is_quota(self) -> None:
        """Google's equivalent surfaces as RESOURCE_EXHAUSTED."""
        assert detect_provider_error("429 RESOURCE_EXHAUSTED") == "quota_exceeded"

    def test_rate_limit_and_auth_are_distinguished(self) -> None:
        """Each class carries its own reason so the report can separate them."""
        assert detect_provider_error("openai.RateLimitError: slow down") == "rate_limited"
        assert detect_provider_error("Error code: 401") == "auth_failed"

    def test_bare_429_in_output_is_not_a_provider_error(self) -> None:
        """A status code mentioned in model output must not fake a failure.

        Guards the false positive that would let ordinary agent output about
        HTTP codes mark an otherwise healthy trial as infrastructure-broken.
        """
        assert detect_provider_error("the endpoint returns HTTP 429 on throttle") == ""
        assert detect_provider_error("15 passed; 429 rows returned") == ""

    def test_healthy_output_reports_nothing(self) -> None:
        """No provider failure => empty reason."""
        assert detect_provider_error("All tests passed in 0.02s") == ""
