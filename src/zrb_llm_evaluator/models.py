# GENERATED FROM SPEC: specs/experiment-runner/requirements.md
# IMPLEMENTS: REQ-003, REQ-015, REQ-017, REQ-019, NFR-002, RULE-001, RULE-003

"""Pydantic v2 models for the experiment runner."""

from __future__ import annotations

import uuid
from datetime import datetime
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

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    model: str
    test_case: str
    trial_index: int = Field(ge=1)
    status: Literal["EXCELLENT", "PASS", "FAIL", "TIMEOUT", "ERROR"]
    duration: float = Field(ge=0.0)
    exit_code: int
    log_path: str
    stdout_log_path: str = ""
    verification_result: ValidationResult | None = None
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    tool_calls: list[str] = Field(default_factory=list)
    tool_call_count: int = 0


# @sdlc REQ-004, REQ-010, REQ-012, REQ-014, REQ-015, RULE-003
class ExperimentConfig(BaseModel):
    """Configuration for an experiment run."""

    models: list[str] = Field(min_length=1)
    test_case_dirs: list[Path] = Field(min_length=1)
    trials: int = Field(ge=1, default=3)
    parallelism: int = Field(ge=1, default=4)
    timeout: int = Field(ge=30, default=300)
    cli_name: str = Field(default="zrb", min_length=1)
    env_prefix: str = Field(default="ZRB", min_length=1)

    # @sdlc REQ-015
    @field_validator("models")
    @classmethod
    def _validate_model_format(cls, v: list[str]) -> list[str]:
        """Each model must be in provider:name format (provider and name non-empty)."""
        for model in v:
            provider, sep, name = model.partition(":")
            if not sep or not provider or not name:
                msg = f"Model {model!r} must be in 'provider:name' format (e.g. 'openai:gpt-4o')"
                raise ValueError(msg)
        return v


class Experiment(BaseModel):
    """A full experiment run: config + accumulated results + timing.

    Persisted as ``experiment.json`` in the output directory alongside the
    per-trial-streamed ``results.json``.  The same ``id`` and ``started_at``
    survive across resumed invocations.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    config: ExperimentConfig
    results: list[TrialResult] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime | None = None


class Report(BaseModel):
    """Manifest describing the artifacts produced by a report generation pass."""

    experiment_id: str
    markdown_path: str = ""
    json_path: str = ""
    generated_at: datetime
