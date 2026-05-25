# COVERS: REQ-019, UT-026

"""Tests for tool-call extraction from zrb history JSON."""

from __future__ import annotations

import json
from pathlib import Path

from zrb_llm_evaluator.cost_parser import (
    count_tool_calls_from_history,
    extract_tool_calls_from_history,
)


class TestToolCallExtraction:
    """Tests for extracting tool-call names from history JSON — @sdlc REQ-019."""

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """UT-026: Missing history file => empty list, count 0."""
        names, count = count_tool_calls_from_history(tmp_path / "nope.json")
        assert names == []
        assert count == 0

    def test_malformed_json_returns_empty(self, tmp_path: Path) -> None:
        """UT-026: Corrupt JSON => empty list (defensive)."""
        p = tmp_path / "broken.json"
        p.write_text("{not json", encoding="utf-8")
        names, count = count_tool_calls_from_history(p)
        assert names == []
        assert count == 0

    def test_list_with_tool_name(self, tmp_path: Path) -> None:
        """UT-026: Bare-list shape with ``tool_name`` entries."""
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
        """UT-026: ``tool_call.name`` nested form is recognised."""
        p = tmp_path / "h.json"
        data = [
            {"tool_call": {"name": "run_python", "args": {}}},
            {"tool_call": {"name": "shell", "args": {}}},
        ]
        p.write_text(json.dumps(data), encoding="utf-8")
        names = extract_tool_calls_from_history(p)
        assert names == ["run_python", "shell"]

    def test_history_wrapped_in_dict(self, tmp_path: Path) -> None:
        """UT-026: ``{\"history\": [...]}`` wrapper is supported."""
        p = tmp_path / "h.json"
        data = {"history": [{"tool_name": "alpha"}, {"tool_name": "beta"}]}
        p.write_text(json.dumps(data), encoding="utf-8")
        names = extract_tool_calls_from_history(p)
        assert names == ["alpha", "beta"]

    def test_unexpected_shape_returns_empty(self, tmp_path: Path) -> None:
        """UT-026: Top-level scalar JSON => empty."""
        p = tmp_path / "h.json"
        p.write_text(json.dumps("just a string"), encoding="utf-8")
        names = extract_tool_calls_from_history(p)
        assert names == []

    def test_entries_without_tool_name_skipped(self, tmp_path: Path) -> None:
        """UT-026: Non-tool entries are skipped, no error."""
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
        """UT-026: ``role=tool`` with ``name`` field also counted."""
        p = tmp_path / "h.json"
        data = [
            {"role": "tool", "name": "search"},
            {"role": "assistant", "content": "ok"},
        ]
        p.write_text(json.dumps(data), encoding="utf-8")
        names = extract_tool_calls_from_history(p)
        assert names == ["search"]

    def test_pydantic_ai_parts_shape(self, tmp_path: Path) -> None:
        """UT-026: pydantic-ai ``parts[]`` with ``part_kind=tool-call`` is recognised.

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
