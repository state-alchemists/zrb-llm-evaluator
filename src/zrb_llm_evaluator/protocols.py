# GENERATED FROM SPEC: specs/experiment-runner/requirements.md
# IMPLEMENTS: REQ-009, REQ-011, REQ-013, RULE-001, RULE-004

"""Protocol definitions for pluggable validators."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from zrb_llm_evaluator.models import ValidationResult


# @sdlc REQ-009, REQ-011, REQ-013, RULE-004
@runtime_checkable
class ValidatorProtocol(Protocol):
    """Protocol that all test case validators must implement.

    Implementations must provide a ``validate`` method that accepts
    an output directory and the log content, returning a
    ``ValidationResult``.
    """

    def validate(self, output_dir: Path, log_content: str) -> ValidationResult:
        """Validate the output of a trial.

        Args:
        ----
            output_dir: Path to the per-trial output directory.
            log_content: Full LLM conversation history text.

        Returns:
        -------
            A ValidationResult with status, score, and details.

        """
        ...
