# COVERS: EXPERIMENT-RUNNER:REQ-015, EXPERIMENT-RUNNER:REQ-019, EXPERIMENT-RUNNER:UT-017, EXPERIMENT-RUNNER:UT-018, EXPERIMENT-RUNNER:UT-022, EXPERIMENT-RUNNER:UT-023, EXPERIMENT-RUNNER:UT-049

"""Tests for Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from zrb_llm_evaluator.models import (
    ExperimentConfig,
    TrialResult,
    ValidationCheck,
    ValidationResult,
)


class TestExperimentConfig:
    """Tests for ExperimentConfig model — @sdlc EXPERIMENT-RUNNER:REQ-015."""

    def test_model_format_provider_colon_name(self) -> None:
        """EXPERIMENT-RUNNER:UT-017: 'openai:gpt-4o' is accepted."""
        config = ExperimentConfig(
            models=["openai:gpt-4o"],
            test_case_dirs=["/tmp/case"],
            trials=1,
        )
        assert config.models == ["openai:gpt-4o"]

    def test_model_format_rejects_bare_name(self) -> None:
        """EXPERIMENT-RUNNER:UT-018: 'gpt-4o' (no colon) is rejected."""
        with pytest.raises(ValidationError) as exc:
            ExperimentConfig(
                models=["gpt-4o"],
                test_case_dirs=["/tmp/case"],
                trials=1,
            )
        assert "provider:name" in str(exc.value)

    def test_min_trials_enforced(self) -> None:
        """Trials must be >= 1."""
        with pytest.raises(ValidationError):
            ExperimentConfig(
                models=["openai:gpt-4o"],
                test_case_dirs=["/tmp/case"],
                trials=0,
            )

    def test_min_parallelism_enforced(self) -> None:
        """Parallelism must be >= 1."""
        with pytest.raises(ValidationError):
            ExperimentConfig(
                models=["openai:gpt-4o"],
                test_case_dirs=["/tmp/case"],
                trials=1,
                parallelism=0,
            )

    def test_min_timeout_enforced(self) -> None:
        """Timeout must be >= 30."""
        with pytest.raises(ValidationError):
            ExperimentConfig(
                models=["openai:gpt-4o"],
                test_case_dirs=["/tmp/case"],
                trials=1,
                timeout=10,
            )

    def test_cli_name_empty_rejected(self) -> None:
        """EXPERIMENT-RUNNER:UT-049: Empty cli_name is rejected."""
        with pytest.raises(ValidationError):
            ExperimentConfig(
                models=["openai:gpt-4o"],
                test_case_dirs=["/tmp/case"],
                trials=1,
                cli_name="",
            )


class TestTrialResult:
    """Tests for TrialResult model — @sdlc EXPERIMENT-RUNNER:REQ-017, EXPERIMENT-RUNNER:REQ-019."""

    def test_token_fields_default_zero(self) -> None:
        """EXPERIMENT-RUNNER:UT-023: Token fields default to 0 when absent."""
        result = TrialResult(
            model="openai:gpt-4o",
            test_case="case-a",
            trial_index=1,
            status="PASS",
            duration=1.0,
            exit_code=0,
            log_path="/tmp/log.log",
        )
        assert result.total_tokens == 0
        assert result.input_tokens == 0
        assert result.output_tokens == 0
        assert result.cache_read_tokens == 0

    def test_round_trip_serialization(self) -> None:
        """TrialResult round-trips via model_dump/model_validate."""
        original = TrialResult(
            model="openai:gpt-4o",
            test_case="case-a",
            trial_index=1,
            status="PASS",
            duration=1.0,
            exit_code=0,
            log_path="/tmp/log.log",
            total_tokens=150,
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=0,
        )
        data = original.model_dump(mode="json")
        restored = TrialResult.model_validate(data)
        assert restored.model == original.model
        assert restored.total_tokens == 150
        assert restored.input_tokens == 100
        assert restored.output_tokens == 50

    def test_with_verification_result(self) -> None:
        """TrialResult holds an optional VerificationResult."""
        vr = ValidationResult(
            status="EXCELLENT",
            score=0.95,
            details=[ValidationCheck(name="style", passed=True, message="Good")],
        )
        result = TrialResult(
            model="openai:gpt-4o",
            test_case="case-a",
            trial_index=1,
            status="EXCELLENT",
            duration=1.0,
            exit_code=0,
            log_path="/tmp/log.log",
            verification_result=vr,
        )
        assert result.verification_result is not None
        assert result.verification_result.score == 0.95
