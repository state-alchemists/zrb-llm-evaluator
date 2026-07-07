# GENERATED FROM SPEC: .sdlc/specs/experiment-runner/spec.md
# IMPLEMENTS: EXPERIMENT-RUNNER:REQ-009, EXPERIMENT-RUNNER:REQ-011, EXPERIMENT-RUNNER:REQ-013,
# IMPLEMENTS: RULE-001, RULE-004
# IMPLEMENTS: EXPERIMENT-RUNNER:REQ-035, EXPERIMENT-RUNNER:REQ-039, EXPERIMENT-RUNNER:REQ-040

"""Protocol definitions for pluggable validators and CLI adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from zrb_llm_evaluator.models import TrialTrace, UsageSummary, ValidationResult


# @sdlc EXPERIMENT-RUNNER:REQ-009, EXPERIMENT-RUNNER:REQ-011, EXPERIMENT-RUNNER:REQ-013, RULE-004
@runtime_checkable
class ValidatorProtocol(Protocol):
    """Protocol that all test case validators must implement.

    Implementations must provide a ``validate`` method that accepts the
    trial output directory, the full subprocess log content, and a
    :class:`TrialTrace` parsed from the session history. The ``trace``
    parameter defaults to ``None`` so the protocol still type-checks
    against legacy two-arg validators, but the runner always passes a
    concrete ``TrialTrace`` — validators that want trajectory access
    should declare the parameter explicitly.
    """

    def validate(
        self,
        output_dir: Path,
        log_content: str,
        trace: TrialTrace | None = None,
    ) -> ValidationResult:
        """Validate the output of a trial.

        Args:
        ----
            output_dir: Path to the per-trial output directory.
            log_content: Full LLM conversation history text (stdout+stderr).
            trace: Structured view of the recorded session — tool calls,
                assistant text, and turn count. The runner always passes a
                non-None value; ``None`` only appears in unit-test stubs
                and for backwards compatibility with two-arg validators.

        Returns:
        -------
            A ValidationResult with status, score, and details.

        """
        ...


# @sdlc EXPERIMENT-RUNNER:REQ-035, EXPERIMENT-RUNNER:REQ-039, EXPERIMENT-RUNNER:REQ-040,
# @sdlc RULE-004, RULE-005
@runtime_checkable
class CliAdapter(Protocol):
    """Protocol abstracting how the runner invokes and interprets one CLI-under-test.

    ``TrialRunner`` no longer hardcodes any single CLI's invocation, env
    vars, or output format (RULE-005). Instead it resolves exactly one
    ``CliAdapter`` per experiment from ``ExperimentConfig.cli_template``
    and delegates every CLI-specific decision to it. Built-in
    implementations: ``ZrbCliAdapter`` (default), ``ClaudeCodeCliAdapter``,
    ``OpencodeCliAdapter``. Users may supply a custom implementation via a
    dotted import path on ``ExperimentConfig.cli_template``.

    Implementations may additionally expose two class attributes
    (deliberately not part of this protocol, so existing custom adapters
    remain valid): ``default_cli_name``, the binary name the CLI layer
    falls back to when ``--cli-name`` isn't given (default ``"zrb"``), and
    ``version_args``, the argv suffix that prints the CLI's version
    (default ``("--version",)``).
    """

    def build_argv(
        self,
        cli_name: str,
        model: str,
        instruction: str,
        session_name: str,
    ) -> list[str]:
        """Build the full subprocess argv (program name first).

        Args:
        ----
            cli_name: The CLI binary name (``ExperimentConfig.cli_name``).
            model: Model identifier (``provider:name``).
            instruction: The test case's instruction/prompt text.
            session_name: The trial's unique session name.

        Returns:
        -------
            The full argv list, with the program name as the first element.

        """
        ...

    def build_env(
        self,
        base_env: dict[str, str],
        history_dir: Path,
        journal_dir: Path,
        env_prefix: str,
    ) -> dict[str, str]:
        """Build the subprocess environment.

        Args:
        ----
            base_env: The base environment to overlay onto (typically a
                copy of ``os.environ``).
            history_dir: The trial's per-cell ``history/`` directory.
            journal_dir: The trial's per-cell ``notes/`` directory.
            env_prefix: The configured env-var prefix (``ExperimentConfig.env_prefix``).

        Returns:
        -------
            The complete environment dict to pass to the subprocess. An
            adapter may ignore any of ``history_dir``/``journal_dir``/
            ``env_prefix`` if it manages history capture another way.

        """
        ...

    def history_log_path(self, history_dir: Path, session_name: str) -> Path:
        """Return where this adapter writes/expects the conversation history file.

        Args:
        ----
            history_dir: The trial's per-cell ``history/`` directory.
            session_name: The trial's unique session name.

        Returns:
        -------
            The path this adapter writes to (or expects the CLI to write to).

        """
        ...

    def parse_usage(self, stdout: str) -> UsageSummary:
        """Extract token/cost usage from captured subprocess stdout.

        Args:
        ----
            stdout: The full captured subprocess stdout (and stderr, since
                the runner streams both to the same log).

        Returns:
        -------
            A ``UsageSummary``; fields default to 0 when undeterminable.

        """
        ...

    def extract_tool_calls(self, history_log_path: Path) -> tuple[list[str], int]:
        """Extract tool-call names from the adapter's own history file format.

        Args:
        ----
            history_log_path: Path returned by ``history_log_path``.

        Returns:
        -------
            A tuple of ``(tool_call_names, count)``; empty/0 on any failure.

        """
        ...
