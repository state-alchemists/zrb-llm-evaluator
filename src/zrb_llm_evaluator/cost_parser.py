# GENERATED FROM SPEC: .sdlc/specs/experiment-runner/spec.md
# IMPLEMENTS: EXPERIMENT-RUNNER:REQ-019

"""Parse cost / token summary lines and tool calls from zrb output."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from zrb_llm_evaluator.models import ToolCallRecord, TrialTrace

# @sdlc EXPERIMENT-RUNNER:REQ-019
# Matches a single 💸 token-summary line emitted by zrb
# (`zrb/llm/util/stream_response.py`). Example:
#   💸 (Requests: 4 | Tool Calls: 7 | Total: 1500) Input: 1000 |
#       Audio Input: 0 | Output: 500 | Audio Output: 0 |
#       Cache Read: 200 | Cache Write: 0 | Details: {...}
# Negative lookbehinds on ``Input:`` and ``Output:`` exclude
# ``Audio Input:`` / ``Audio Output:`` from bleeding into the
# ``input``/``output`` groups.
_COST_LINE_PATTERN = re.compile(
    r"💸\s*\([^)]*Total:\s*(?P<total>\d+)[^)]*\)"
    r".*?(?<!Audio\s)Input:\s*(?P<input>\d+)"
    r".*?(?<!Audio\s)Output:\s*(?P<output>\d+)"
    r".*?Cache Read:\s*(?P<cache>\d+)"
)


# @sdlc EXPERIMENT-RUNNER:REQ-019
def parse_cost_summary(stdout: str) -> dict[str, int]:
    """Parse token counts from a zrb 💸 cost summary line in stdout.

    zrb emits one ``💸 (...) Input: A | Audio Input: B | Output: C |
    Audio Output: D | Cache Read: E | Cache Write: F | Details: {...}``
    line per turn; totals are cumulative. When multiple 💸 lines are
    present, only the LAST one is used so we don't double-count.

    Args:
    ----
        stdout: Full subprocess stdout text.

    Returns:
    -------
        Dict with keys ``total_tokens``, ``input_tokens``,
        ``output_tokens``, ``cache_read_tokens``.  Any field that
        cannot be parsed defaults to 0.

    """
    result: dict[str, int] = {
        "total_tokens": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
    }
    matches = list(_COST_LINE_PATTERN.finditer(stdout))
    if matches:
        last = matches[-1]
        result["total_tokens"] = int(last.group("total"))
        result["input_tokens"] = int(last.group("input"))
        result["output_tokens"] = int(last.group("output"))
        result["cache_read_tokens"] = int(last.group("cache"))
    return result


# @sdlc EXPERIMENT-RUNNER:REQ-019
def extract_tool_calls_from_history(history_path: Path) -> list[str]:
    """Extract tool-call names from a zrb history JSON file.

    The zrb history JSON is a list of conversation entries; tool-use entries
    expose a ``tool_name`` (or nested ``tool_call.name``) field. This helper
    is defensive: any parse error or unexpected shape yields an empty list.

    Args:
    ----
        history_path: Path to the ``{session_name}.json`` history file.

    Returns:
    -------
        Ordered list of tool names invoked; empty list on any failure.

    """
    if not history_path.is_file():
        return []
    try:
        raw = history_path.read_text(encoding="utf-8")
        data: Any = json.loads(raw)
    except (OSError, json.JSONDecodeError, ValueError):
        return []

    names: list[str] = []
    try:
        entries = _iter_history_entries(data)
        for entry in entries:
            names.extend(_extract_tool_names(entry))
    except (TypeError, AttributeError, KeyError):
        return []
    return names


# @sdlc EXPERIMENT-RUNNER:REQ-019
def count_tool_calls_from_history(history_path: Path) -> tuple[list[str], int]:
    """Return ``(tool_call_names, count)`` for the given history file.

    Args:
    ----
        history_path: Path to the ``{session_name}.json`` history file.

    Returns:
    -------
        Tuple of the ordered tool-call name list and its length.

    """
    names = extract_tool_calls_from_history(history_path)
    return names, len(names)


def build_trial_trace(history_path: Path) -> TrialTrace:
    """Build a :class:`TrialTrace` from a recorded session history file.

    Tolerant of missing files and malformed JSON — returns an empty
    trace rather than raising so a damaged history never blocks
    validation.

    Args:
    ----
        history_path: Path to the ``{session_name}.json`` history file.

    Returns:
    -------
        A populated ``TrialTrace`` (or an empty one if the file cannot
        be read or parsed).

    """
    if not history_path.is_file():
        return TrialTrace()
    try:
        raw = history_path.read_text(encoding="utf-8")
        data: Any = json.loads(raw)
    except (OSError, json.JSONDecodeError, ValueError):
        return TrialTrace()

    entries = _iter_history_entries(data)
    tool_calls: list[ToolCallRecord] = []
    assistant_chunks: list[str] = []
    turn_count = 0

    for entry in entries:
        # pydantic-ai ModelResponse shape — parts list with mixed kinds.
        parts = entry.get("parts")
        if isinstance(parts, list):
            for part in parts:
                if not isinstance(part, dict):
                    continue
                kind = part.get("part_kind")
                if kind == "tool-call":
                    name = part.get("tool_name")
                    if isinstance(name, str) and name:
                        args = _coerce_tool_args(part.get("args"))
                        tool_calls.append(ToolCallRecord(name=name, args=args))
                elif kind == "text":
                    chunk = part.get("content")
                    if isinstance(chunk, str) and chunk:
                        assistant_chunks.append(chunk)
            if entry.get("kind") == "response" or any(
                isinstance(p, dict) and p.get("part_kind") == "text"
                for p in parts
            ):
                turn_count += 1
            continue

        # Legacy shapes — bare tool_name / tool_call dict / role=tool.
        direct = entry.get("tool_name")
        if isinstance(direct, str) and direct:
            args = _coerce_tool_args(entry.get("args"))
            tool_calls.append(ToolCallRecord(name=direct, args=args))
            continue
        tool_call = entry.get("tool_call")
        if isinstance(tool_call, dict):
            nested = tool_call.get("name")
            if isinstance(nested, str) and nested:
                args = _coerce_tool_args(tool_call.get("arguments") or tool_call.get("args"))
                tool_calls.append(ToolCallRecord(name=nested, args=args))
                continue
        role = entry.get("role")
        if role == "assistant":
            content = entry.get("content")
            if isinstance(content, str) and content:
                assistant_chunks.append(content)
                turn_count += 1
        elif role == "tool":
            name = entry.get("name")
            if isinstance(name, str) and name:
                tool_calls.append(ToolCallRecord(name=name, args={}))

    return TrialTrace(
        tool_calls=tool_calls,
        tool_names=[tc.name for tc in tool_calls],
        assistant_text="\n".join(assistant_chunks),
        turn_count=turn_count,
    )


def _coerce_tool_args(raw: Any) -> dict[str, Any]:
    """Normalize a tool-call ``args`` field to a dict.

    pydantic-ai serializes args as either a JSON-encoded string or an
    already-decoded dict; both shapes are accepted. Anything else
    collapses to an empty dict.
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _iter_history_entries(data: Any) -> list[dict[str, Any]]:
    """Normalize the zrb history JSON into a flat list of dict entries.

    Handles both ``{"history": [...]}`` and bare-list shapes.
    """
    candidates: list[Any]
    if isinstance(data, list):
        candidates = data
    elif isinstance(data, dict):
        history = data.get("history")
        if isinstance(history, list):
            candidates = history
        else:
            candidates = [data]
    else:
        return []
    return [c for c in candidates if isinstance(c, dict)]


def _extract_tool_names(entry: dict[str, Any]) -> list[str]:
    """Return all tool-call names from a history entry.

    Handles three known shapes:
      * legacy bare-list entries with a top-level ``tool_name`` / ``tool_call``;
      * ``{"role": "tool", "name": ...}`` rows;
      * pydantic-ai ``ModelResponse`` shape, where tool calls are nested under
        ``parts[]`` with ``part_kind == "tool-call"`` and a ``tool_name`` field.
        A single message can contain multiple parallel tool calls — all are
        returned in order.
    """
    names: list[str] = []
    parts = entry.get("parts")
    if isinstance(parts, list):
        for part in parts:
            if not isinstance(part, dict):
                continue
            if part.get("part_kind") == "tool-call":
                name = part.get("tool_name")
                if isinstance(name, str) and name:
                    names.append(name)
    if names:
        return names

    direct = entry.get("tool_name")
    if isinstance(direct, str) and direct:
        names.append(direct)
        return names
    tool_call = entry.get("tool_call")
    if isinstance(tool_call, dict):
        nested = tool_call.get("name")
        if isinstance(nested, str) and nested:
            names.append(nested)
            return names
    role = entry.get("role")
    name = entry.get("name")
    if role == "tool" and isinstance(name, str) and name:
        names.append(name)
    return names
