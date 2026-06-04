# GENERATED FROM SPEC: .sdlc/specs/experiment-runner/spec.md
# IMPLEMENTS: REQ-013, REQ-015, REQ-024, RULE-001, RULE-004

"""Test case discovery, loading, and validation."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from zrb_llm_evaluator.protocols import ValidatorProtocol


# @sdlc REQ-013, REQ-024, RULE-001, RULE-003
class TestCase(BaseModel):
    """A loaded test case with instruction, workdir, and validator.

    ``workdir`` is the path the runner stages into the trial's nested
    workdir. It always points to ``{test_case_dir}/workdir`` — whether or
    not that directory exists. When it doesn't exist, the runner stages
    nothing and the LLM sees an empty workdir (per REQ-022 / REQ-024,
    test-case metadata like ``validator.py`` and ``instruction.txt`` must
    never reach the subprocess cwd).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    instruction: str
    workdir: Path
    validator: ValidatorProtocol


# @sdlc REQ-013, RULE-004
def load_test_case(test_case_dir: Path) -> TestCase:
    """Load a single test case from a directory.

    The directory must contain an ``instruction.txt`` and a
    ``validator.py`` module that implements ``ValidatorProtocol``.

    Args:
    ----
        test_case_dir: Path to the test case directory.

    Returns:
    -------
        A ``TestCase`` instance.

    Raises:
    ------
        ValueError: If the directory lacks required files or the
            validator does not conform to ``ValidatorProtocol``.

    """
    if not test_case_dir.is_dir():
        msg = f"Test case directory does not exist: {test_case_dir}"
        raise ValueError(msg)

    name = test_case_dir.name

    # Load instruction
    instruction_path = test_case_dir / "instruction.txt"
    if not instruction_path.is_file():
        msg = f"Test case {name!r} missing instruction.txt in {test_case_dir}"
        raise ValueError(msg)
    instruction = instruction_path.read_text(encoding="utf-8")

    # workdir is the staging source — always {test_case_dir}/workdir.
    # If it doesn't exist, the runner creates an empty nested workdir
    # instead of staging anything (REQ-022). Never falls back to
    # test_case_dir itself, which would expose validator.py /
    # instruction.txt to the LLM (REQ-024).
    workdir: Path = test_case_dir / "workdir"

    # Load and validate validator module
    validator_path = test_case_dir / "validator.py"
    if not validator_path.is_file():
        msg = f"Test case {name!r} missing validator.py in {test_case_dir}"
        raise ValueError(msg)

    validator = _import_validator(validator_path)

    return TestCase(
        name=name,
        instruction=instruction,
        workdir=workdir,
        validator=validator,
    )


# @sdlc REQ-013, RULE-004
def load_test_cases(test_case_dirs: list[Path]) -> list[TestCase]:
    """Load all test cases from the given directories.

    Each directory is expected to be a single test case.

    Args:
    ----
        test_case_dirs: List of paths to test case directories.

    Returns:
    -------
        List of loaded ``TestCase`` instances.

    Raises:
    ------
        ValueError: If any test case is invalid (missing files,
            bad validator).

    """
    test_cases: list[TestCase] = []
    errors: list[str] = []
    for tcd in test_case_dirs:
        try:
            test_cases.append(load_test_case(tcd))
        except ValueError as exc:
            errors.append(str(exc))
    if errors:
        msg = "Test case loading failed:\n  " + "\n  ".join(errors)
        raise ValueError(msg)
    return test_cases


# @sdlc REQ-015
def make_safe_name(model: str) -> str:
    """Convert a model name to a filesystem-safe directory name.

    Replaces colons and non-alphanumeric characters with underscores.

    Args:
    ----
        model: Model name in ``provider:name`` format.

    Returns:
    -------
        A safe string for use in directory paths.

    """
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", model)


# @sdlc REQ-001
def make_session_name(model: str, test_case: str, trial_index: int) -> str:
    """Generate a unique session name for a trial.

    Args:
    ----
        model: Model identifier.
        test_case: Test case name.
        trial_index: Trial number (1-based).

    Returns:
    -------
        A unique session name string.

    """
    safe_model = make_safe_name(model)
    return f"{safe_model}-{test_case}-trial-{trial_index}"


def _import_validator(validator_path: Path) -> ValidatorProtocol:
    """Dynamically import a validator module and check conformance.

    Args:
    ----
        validator_path: Path to ``validator.py``.

    Returns:
    -------
        An instance of the validator.

    Raises:
    ------
        ValueError: If the module lacks a ``validator`` object or
            it does not implement ``ValidatorProtocol``.

    """
    # Unique module name per test case so multiple validator.py files don't
    # collide in sys.modules and overwrite each other.
    case_slug = re.sub(r"[^a-zA-Z0-9_]", "_", validator_path.parent.name)
    module_name = f"zrb_llm_evaluator_validator__{case_slug}__{validator_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, validator_path)
    if spec is None or spec.loader is None:
        msg = f"Cannot load validator module: {validator_path}"
        raise ValueError(msg)

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    if not hasattr(module, "validator"):
        msg = f"Validator module {validator_path} must expose a 'validator' object"
        raise ValueError(msg)

    validator = module.validator
    if not isinstance(validator, ValidatorProtocol):
        msg = (
            f"Validator in {validator_path} does not implement "
            f"ValidatorProtocol (got {type(validator).__name__})"
        )
        raise ValueError(msg)

    return validator
