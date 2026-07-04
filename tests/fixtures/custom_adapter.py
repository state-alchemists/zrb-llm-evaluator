# COVERS: EXPERIMENT-RUNNER:REQ-037, EXPERIMENT-RUNNER:UT-062

"""A custom ``CliAdapter`` implementation used to test dotted-path loading.

Imported by ``resolve_cli_adapter`` via ``ExperimentConfig.cli_template =
"tests.fixtures.custom_adapter.FakeAdapter"`` in
``tests/experiment-runner/test_cli_adapters.py`` (UT-062).
"""

from __future__ import annotations

from pathlib import Path

from zrb_llm_evaluator.models import UsageSummary

#: Records every ``build_argv``/``build_env`` call for test assertions.
CALLS: list[str] = []


class FakeAdapter:
    """Minimal ``CliAdapter`` implementation for dotted-path resolution tests."""

    def build_argv(
        self, cli_name: str, model: str, instruction: str, session_name: str,
    ) -> list[str]:
        """Record the call and return a trivial argv."""
        CALLS.append("build_argv")
        return [cli_name, "fake-run", instruction, "--model", model]

    def build_env(
        self,
        base_env: dict[str, str],
        history_dir: Path,
        journal_dir: Path,
        env_prefix: str,
    ) -> dict[str, str]:
        """Record the call and pass the base environment through."""
        CALLS.append("build_env")
        return dict(base_env)

    def history_log_path(self, history_dir: Path, session_name: str) -> Path:
        """Return a fixed history file path under ``history_dir``."""
        return history_dir / f"{session_name}.json"

    def parse_usage(self, stdout: str) -> UsageSummary:
        """Return a fixed, recognizable ``UsageSummary``."""
        CALLS.append("parse_usage")
        return UsageSummary(total_tokens=7, input_tokens=5, output_tokens=2)

    def extract_tool_calls(self, history_log_path: Path) -> tuple[list[str], int]:
        """Return a fixed, recognizable tool-call list."""
        CALLS.append("extract_tool_calls")
        return ["fake_tool"], 1
