# GENERATED FROM SPEC: .sdlc/specs/experiment-runner/spec.md
# IMPLEMENTS: EXPERIMENT-RUNNER:REQ-003, EXPERIMENT-RUNNER:REQ-015, EXPERIMENT-RUNNER:REQ-017, EXPERIMENT-RUNNER:REQ-019, EXPERIMENT-RUNNER:NFR-002, RULE-001, RULE-003

"""Pydantic v2 models for the experiment runner."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# @sdlc EXPERIMENT-RUNNER:REQ-003, EXPERIMENT-RUNNER:REQ-017, RULE-003
class ValidationCheck(BaseModel):
    """A single check within a validation result."""

    name: str
    passed: bool
    message: str = ""


# @sdlc EXPERIMENT-RUNNER:REQ-003, EXPERIMENT-RUNNER:REQ-009, RULE-003
class ValidationResult(BaseModel):
    """Structured result from a test case validator."""

    status: Literal["EXCELLENT", "PASS", "FAIL"]
    score: float = Field(ge=0.0, le=1.0)
    details: list[ValidationCheck] = Field(default_factory=list)


class ToolCallRecord(BaseModel):
    """A single tool invocation observed in the trial history.

    Surfaced to validators via :class:`TrialTrace` so they can assert on
    the agent's trajectory (which tools it used, in what order, with what
    arguments) rather than only on the final filesystem state.
    """

    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class TrialTrace(BaseModel):
    """Structured view of a trial's recorded session history.

    Built by the runner from ``history/<session>.json`` and passed to the
    validator alongside ``output_dir`` and ``log_content``. Defensive by
    construction: when the history file is missing or malformed, the
    trace is empty rather than raising — validators should treat empty
    fields as "no signal" not "agent did nothing".
    """

    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    assistant_text: str = ""
    turn_count: int = 0


# @sdlc EXPERIMENT-RUNNER:REQ-001, EXPERIMENT-RUNNER:REQ-005, EXPERIMENT-RUNNER:REQ-007, EXPERIMENT-RUNNER:REQ-008, EXPERIMENT-RUNNER:REQ-009, EXPERIMENT-RUNNER:REQ-017, EXPERIMENT-RUNNER:REQ-019, RULE-003
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


# @sdlc EXPERIMENT-RUNNER:REQ-004, EXPERIMENT-RUNNER:REQ-010, EXPERIMENT-RUNNER:REQ-012, EXPERIMENT-RUNNER:REQ-014, EXPERIMENT-RUNNER:REQ-015, RULE-003
class ExperimentConfig(BaseModel):
    """Configuration for an experiment run."""

    models: list[str] = Field(min_length=1)
    test_case_dirs: list[Path] = Field(min_length=1)
    trials: int = Field(ge=1, default=3)
    parallelism: int = Field(ge=1, default=4)
    timeout: int = Field(ge=30, default=300)
    cli_name: str = Field(default="zrb", min_length=1)
    cli_version: str = Field(default="")
    env_prefix: str = Field(default="ZRB", min_length=1)

    # @sdlc EXPERIMENT-RUNNER:REQ-015
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
