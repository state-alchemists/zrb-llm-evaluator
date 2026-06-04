# GENERATED FROM SPEC: .sdlc/specs/experiment-runner/spec.md
# IMPLEMENTS: REQ-009, REQ-011, REQ-013, RULE-001, RULE-004

"""Protocol definitions for pluggable validators."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from zrb_llm_evaluator.models import TrialTrace, ValidationResult


# @sdlc REQ-009, REQ-011, REQ-013, RULE-004
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
