# GENERATED FROM SPEC: specs/experiment-runner/requirements.md
# IMPLEMENTS: REQ-003, REQ-015, REQ-017, REQ-019, NFR-002, RULE-001, RULE-003, RULE-010

"""Pydantic v2 models for the experiment runner."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# @sdlc REQ-003, REQ-017, RULE-003
class ValidationCheck(BaseModel):
    """A single check within a validation result."""

    name: str
    passed: bool
    message: str = ""


# @sdlc REQ-003, REQ-009, RULE-003
class ValidationResult(BaseModel):
    """Structured result from a test case validator."""

    status: Literal["EXCELLENT", "PASS", "FAIL"]
    score: float = Field(ge=0.0, le=1.0)
    details: list[ValidationCheck] = Field(default_factory=list)


# @sdlc REQ-001, REQ-005, REQ-007, REQ-008, REQ-009, REQ-017, REQ-019, RULE-003
class TrialResult(BaseModel):
    """Outcome of a single trial."""

    model: str
    test_case: str
    trial_index: int = Field(ge=1)
    status: Literal["EXCELLENT", "PASS", "FAIL", "TIMEOUT", "ERROR"]
    duration: float = Field(ge=0.0)
    exit_code: int
    log_path: str
    tool_calls: list[str] = Field(default_factory=list)
    tool_call_count: int = 0
    verification_result: ValidationResult | None = None
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


# @sdlc REQ-004, REQ-010, REQ-012, REQ-014, REQ-015, RULE-003
class ExperimentConfig(BaseModel):
    """Configuration for an experiment run."""

    models: list[str] = Field(min_length=1)
    test_case_dirs: list[Path] = Field(min_length=1)
    trials: int = Field(ge=1, default=3)
    parallelism: int = Field(ge=1, default=4)
    timeout: int = Field(ge=30, default=300)
    cli_name: str = "zrb"

    # @sdlc REQ-015
    @field_validator("models")
    @classmethod
    def _validate_model_format(cls, v: list[str]) -> list[str]:
        """Each model must be in provider:name format."""
        pattern = re.compile(r"^[a-zA-Z0-9_]+:[a-zA-Z0-9_./-]+$")
        for model in v:
            if not pattern.match(model):
                msg = f"Model {model!r} must be in 'provider:name' format (e.g. 'openai:gpt-4o')"
                raise ValueError(msg)
        return v
