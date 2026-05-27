# COVERS: REQ-013, UT-015

"""Tests for test case validation (missing/rejected validators)."""

from __future__ import annotations

from pathlib import Path

import pytest
from zrb_llm_evaluator.loader import load_test_case, load_test_cases


class TestValidatorRejection:
    """Tests for test case validator loading — @sdlc REQ-013."""

    def test_missing_validator_rejected(
        self, sample_test_case_dir_no_validator: Path
    ) -> None:
        """UT-015: Missing validator.py raises ValueError."""
        with pytest.raises(ValueError) as exc:
            load_test_case(sample_test_case_dir_no_validator)
        assert "validator.py" in str(exc.value)

    def test_bad_validator_module_rejected(
        self, sample_test_case_dir_with_bad_validator: Path
    ) -> None:
        """Bad validator module (no 'validator' attribute) is rejected."""
        with pytest.raises(ValueError) as exc:
            load_test_case(sample_test_case_dir_with_bad_validator)
        assert "validator" in str(exc.value)

    def test_missing_instruction_rejected(self, tmp_path: Path) -> None:
        """Missing instruction.txt raises ValueError."""
        case_dir = tmp_path / "no-instr"
        case_dir.mkdir(parents=True, exist_ok=True)
        # Create only validator.py
        (case_dir / "validator.py").write_text(
            "from pathlib import Path\n"
            "from zrb_llm_evaluator.models import ValidationResult, ValidationCheck\n"
            "from zrb_llm_evaluator.protocols import ValidatorProtocol\n"
            "class V:\n"
            "    def validate(self, output_dir, log_content, trace=None):\n"
            "        return ValidationResult(status='PASS', score=0.5, details=[])\n"
            "validator = V()\n"
        )

        with pytest.raises(ValueError) as exc:
            load_test_case(case_dir)
        assert "instruction.txt" in str(exc.value)

    def test_valid_case_loads_successfully(
        self, sample_test_case_dir: Path
    ) -> None:
        """A valid test case loads without error."""
        tc = load_test_case(sample_test_case_dir)
        assert tc.name == "sample-case"
        assert "Write a Python function" in tc.instruction
        assert tc.validator is not None

    def test_load_test_cases_batch_rejects(
        self, sample_test_case_dir: Path, sample_test_case_dir_no_validator: Path
    ) -> None:
        """Batch load rejects if any test case is invalid."""
        with pytest.raises(ValueError) as exc:
            load_test_cases([sample_test_case_dir, sample_test_case_dir_no_validator])
        assert "validator.py" in str(exc.value)
