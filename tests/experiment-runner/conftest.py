# COVERS: REQ-002, REQ-004, REQ-005, REQ-006, REQ-007, REQ-008, REQ-009, REQ-010,
#   REQ-011, REQ-012, REQ-013, REQ-015, REQ-017, REQ-018, REQ-019,
#   NFR-001, NFR-002, UT-001..025, IT-001..004

"""Shared fixtures for experiment-runner tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import pytest_asyncio
from zrb_llm_evaluator.loader import TestCase
from zrb_llm_evaluator.models import (
    ExperimentConfig,
    TrialResult,
    ValidationCheck,
    ValidationResult,
)

# ---------------------------------------------------------------------------
# Fixtures: Pydantic model factories
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_experiment_config() -> ExperimentConfig:
    """A minimal valid experiment config."""
    return ExperimentConfig(
        models=["openai:gpt-4o"],
        test_case_dirs=[Path("/tmp/fake-case")],
        trials=1,
        parallelism=1,
        timeout=30,
    )


@pytest.fixture
def sample_validation_result() -> ValidationResult:
    """A sample validation result with PASS status."""
    return ValidationResult(
        status="PASS",
        score=0.85,
        details=[
            ValidationCheck(name="test_a", passed=True, message="OK"),
            ValidationCheck(name="test_b", passed=False, message="Failed B"),
        ],
    )


@pytest.fixture
def sample_trial_result() -> TrialResult:
    """A sample completed trial result."""
    return TrialResult(
        model="openai:gpt-4o",
        test_case="py-test",
        trial_index=1,
        status="PASS",
        duration=1.23,
        exit_code=0,
        log_path="/tmp/fake-log.log",
    )


# ---------------------------------------------------------------------------
# Fixtures: temporary directories and test case scaffolding
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_output_dir(tmp_path: Path) -> Path:
    """A temporary output directory."""
    d = tmp_path / "out"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def sample_test_case_dir(tmp_path: Path) -> Path:
    """Create a test case directory with instruction.txt and validator.py."""
    case_dir = tmp_path / "sample-case"
    case_dir.mkdir(parents=True, exist_ok=True)

    # instruction.txt
    (case_dir / "instruction.txt").write_text(
        "Write a Python function that adds two numbers.", encoding="utf-8"
    )

    # validator.py
    validator_code = '''
from pathlib import Path
from zrb_llm_evaluator.models import ValidationResult, ValidationCheck
from zrb_llm_evaluator.protocols import ValidatorProtocol


class SimpleValidator:
    """A test validator that always returns PASS."""

    def validate(self, output_dir: Path, log_content: str) -> ValidationResult:
        return ValidationResult(
            status="PASS",
            score=0.9,
            details=[
                ValidationCheck(name="check_1", passed=True, message="All good"),
            ],
        )


validator = SimpleValidator()
'''
    (case_dir / "validator.py").write_text(validator_code, encoding="utf-8")

    return case_dir


@pytest.fixture
def sample_test_case_dir_with_bad_validator(tmp_path: Path) -> Path:
    """Create a test case dir with a validator that does NOT implement the protocol."""
    case_dir = tmp_path / "bad-validator-case"
    case_dir.mkdir(parents=True, exist_ok=True)

    (case_dir / "instruction.txt").write_text("Do something.", encoding="utf-8")

    # validator.py WITHOUT a validator object
    (case_dir / "validator.py").write_text(
        "# This module has no 'validator' attribute\n",
        encoding="utf-8",
    )

    return case_dir


@pytest.fixture
def sample_test_case_dir_no_validator(tmp_path: Path) -> Path:
    """Create a test case dir without validator.py at all."""
    case_dir = tmp_path / "no-validator-case"
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "instruction.txt").write_text("Do something.", encoding="utf-8")
    return case_dir


@pytest.fixture
def sample_test_case(sample_test_case_dir: Path) -> TestCase:
    """Load a TestCase from the sample directory."""
    from zrb_llm_evaluator.loader import load_test_case

    return load_test_case(sample_test_case_dir)


# ---------------------------------------------------------------------------
# Fixtures: pre-built results.json for resume testing
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_results_json(tmp_path: Path) -> Path:
    """Create a results.json with 2 terminal + 1 non-terminal entry."""
    from zrb_llm_evaluator.models import TrialResult

    results = [
        TrialResult(
            model="openai:gpt-4o",
            test_case="case-a",
            trial_index=1,
            status="PASS",
            duration=0.5,
            exit_code=0,
            log_path="/tmp/1.log",
        ),
        TrialResult(
            model="openai:gpt-4o",
            test_case="case-a",
            trial_index=2,
            status="ERROR",
            duration=0.3,
            exit_code=1,
            log_path="/tmp/2.log",
        ),
        TrialResult(
            model="openai:gpt-4o",
            test_case="case-a",
            trial_index=3,
            status="PASS",
            duration=0.4,
            exit_code=0,
            log_path="/tmp/3.log",
        ),
    ]

    data = [r.model_dump(mode="json") for r in results]
    p = tmp_path / "results.json"
    p.write_text(__import__("json").dumps(data), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Fixtures: async mock subprocess factory
# ---------------------------------------------------------------------------


class MockProcess:
    """Simulates an asyncio subprocess with controllable output."""

    def __init__(
        self,
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
        delay: float = 0.0,
    ) -> None:
        self._stdout = stdout.encode("utf-8")
        self._stderr = stderr.encode("utf-8")
        self._returncode = returncode
        self._delay = delay
        self.stdout: asyncio.StreamReader | None = None
        self.stderr: asyncio.StreamReader | None = None
        self.returncode: int | None = None
        self._killed = False

    async def communicate(self) -> tuple[bytes, bytes]:
        """Simulate subprocess communication with optional delay."""
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        self.returncode = self._returncode
        return self._stdout, self._stderr

    def kill(self) -> None:
        """Simulate killing the process."""
        self._killed = True
        self.returncode = -1


@pytest_asyncio.fixture
async def mock_subprocess_factory():
    """Factory fixture that returns a callable to create MockProcess instances."""

    def _create(
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
        delay: float = 0.0,
    ) -> MockProcess:
        return MockProcess(
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            delay=delay,
        )

    return _create
