# COVERS: EXPERIMENT-RUNNER:REQ-038, EXPERIMENT-RUNNER:UT-064

"""A CliAdapter-shaped class deliberately missing required methods.

Used by ``tests/experiment-runner/test_cli_adapters.py`` (UT-064) to prove
``resolve_cli_adapter`` rejects a dotted path that resolves to a class not
fully implementing the ``CliAdapter`` protocol.
"""

from __future__ import annotations

from pathlib import Path


class IncompleteAdapter:
    """Missing ``parse_usage`` and ``extract_tool_calls`` — must be rejected."""

    def build_argv(
        self, cli_name: str, model: str, instruction: str, session_name: str,
    ) -> list[str]:
        """Return a trivial argv (present, but not enough on its own)."""
        return [cli_name]

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

    # Deliberately missing: parse_usage, extract_tool_calls.
