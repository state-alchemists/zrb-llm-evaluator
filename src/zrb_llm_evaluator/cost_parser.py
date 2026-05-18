# GENERATED FROM SPEC: specs/experiment-runner/requirements.md
# IMPLEMENTS: REQ-019

"""Parse cost / token summary lines from zrb subprocess stdout."""

from __future__ import annotations

import re

# @sdlc REQ-019
_COST_LINE_PATTERN = re.compile(
    r"Total tokens:\s*(?P<total>\d+)\s*\|\s*"
    r"Input:\s*(?P<input>\d+)\s*\|\s*"
    r"Output:\s*(?P<output>\d+)\s*\|\s*"
    r"Cache:\s*(?P<cache>\d+)"
)


# @sdlc REQ-019
def parse_cost_summary(stdout: str) -> dict[str, int]:
    """Parse token counts from a cost summary line in stdout.

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
    match = _COST_LINE_PATTERN.search(stdout)
    if match:
        result["total_tokens"] = int(match.group("total"))
        result["input_tokens"] = int(match.group("input"))
        result["output_tokens"] = int(match.group("output"))
        result["cache_read_tokens"] = int(match.group("cache"))
    return result
