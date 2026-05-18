# GENERATED FROM SPEC: specs/experiment-runner/requirements.md
# IMPLEMENTS: REQ-001, REQ-002, REQ-003, REQ-004, REQ-005, REQ-006, REQ-007, REQ-008,
#    REQ-009, REQ-010, REQ-011, REQ-012, REQ-016, REQ-017, REQ-018, REQ-019,
#    NFR-001, NFR-002, RULE-005, RULE-012

"""Async experiment runner with subprocess orchestration."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from zrb_llm_evaluator.cost_parser import parse_cost_summary
from zrb_llm_evaluator.loader import TestCase, make_safe_name, make_session_name
from zrb_llm_evaluator.models import ExperimentConfig, TrialResult, ValidationResult

if TYPE_CHECKING:
    from zrb_llm_evaluator.protocols import ValidatorProtocol  # noqa: F401

# Terminal statuses — cells with these statuses are skipped on resume.
TERMINAL_STATUSES: set[str] = {
    "EXCELLENT",
    "PASS",
    "FAIL",
    "TIMEOUT",
    "ERROR",
}


# ---------------------------------------------------------------------------
# Cell planning
# ---------------------------------------------------------------------------

# @sdlc REQ-004
@dataclass
class Cell:
    """A single cell in the experiment grid: model x test_case x trial."""

    model: str
    test_case: str
    trial_index: int


# @sdlc REQ-004
def build_cell_plan(config: ExperimentConfig) -> list[Cell]:
    """Build the full grid of (model, test_case, trial) combinations.

    Args:
    ----
        config: Validated experiment configuration.

    Returns:
    -------
        List of ``Cell`` instances representing all combinations.

    """
    cells: list[Cell] = []
    for model in config.models:
        for tcd in config.test_case_dirs:
            case_name = tcd.name
            for trial_idx in range(1, config.trials + 1):
                cells.append(Cell(model=model, test_case=case_name, trial_index=trial_idx))
    return cells


# ---------------------------------------------------------------------------
# Results persistence
# ---------------------------------------------------------------------------

# @sdlc REQ-003, REQ-006, REQ-017
class ResumeManager:
    """Manages loading and atomically appending results to ``results.json``."""

    def __init__(self, results_path: Path) -> None:
        """Initialize with path to ``results.json``.

        Args:
        ----
            results_path: Path to the results file.

        """
        self._results_path = results_path
        self._results: list[TrialResult] = []
        self._completed_keys: set[tuple[str, str, int]] = set()

    # @sdlc REQ-006
    def load(self) -> list[TrialResult]:
        """Load existing results if the file exists.

        Returns
        -------
            The list of previously persisted ``TrialResult`` instances.

        """
        if not self._results_path.is_file():
            self._results = []
            self._completed_keys.clear()
            return []

        raw = self._results_path.read_text(encoding="utf-8")
        if not raw.strip():
            self._results = []
            self._completed_keys.clear()
            return []

        data: list[dict] = json.loads(raw)
        self._results = [TrialResult.model_validate(item) for item in data]
        for r in self._results:
            self._completed_keys.add((r.model, r.test_case, r.trial_index))
        return self._results

    # @sdlc REQ-006
    def is_completed(self, model: str, test_case: str, trial_index: int) -> bool:
        """Check whether a cell already has a terminal result.

        Args:
        ----
            model: Model identifier.
            test_case: Test case name.
            trial_index: Trial number.

        Returns:
        -------
            ``True`` if the cell has a terminal status.

        """
        key = (model, test_case, trial_index)
        if key not in self._completed_keys:
            return False
        idx = next(
            i for i, r in enumerate(self._results)
            if r.model == model and r.test_case == test_case and r.trial_index == trial_index
        )
        return self._results[idx].status in TERMINAL_STATUSES

    # @sdlc REQ-003, REQ-017
    def append(self, result: TrialResult) -> None:
        """Atomically append a trial result to ``results.json``.

        Args:
        ----
            result: The completed trial result.

        """
        self._results.append(result)
        self._completed_keys.add((result.model, result.test_case, result.trial_index))
        self._flush()

    def _flush(self) -> None:
        """Atomically write all results to disk."""
        data = [r.model_dump(mode="json") for r in self._results]
        parent = self._results_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        tmp: Path | None = None
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(parent),
                prefix=".results_tmp_",
                suffix=".json",
            )
            os.close(fd)
            tmp = Path(tmp_path)
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            os.rename(str(tmp), str(self._results_path))
        finally:
            if tmp is not None and tmp.exists():
                tmp.unlink(missing_ok=True)

    @property
    def results(self) -> list[TrialResult]:
        """All accumulated results."""
        return list(self._results)


# ---------------------------------------------------------------------------
# Per-trial runner
# ---------------------------------------------------------------------------

# @sdlc REQ-001, REQ-005, REQ-012, REQ-016, REQ-018
class TrialRunner:
    """Executes a single trial as a subprocess."""

    def __init__(
        self,
        config: ExperimentConfig,
        test_case: TestCase,
        output_dir: Path,
    ) -> None:
        """Initialize the trial runner.

        Args:
        ----
            config: Experiment configuration.
            test_case: The test case to run.
            output_dir: Root output directory.

        """
        self._config = config
        self._test_case = test_case
        self._output_dir = output_dir

    # @sdlc REQ-001, REQ-005, REQ-016, REQ-018, REQ-019
    async def run(self, model: str, trial_index: int) -> TrialResult:
        """Run a single trial.

        Args:
        ----
            model: Model identifier (provider:name).
            trial_index: Trial number (1-based).

        Returns:
        -------
            A ``TrialResult`` with the outcome.

        """
        safe_model = make_safe_name(model)
        cell_dir = self._output_dir / safe_model / self._test_case.name / f"trial-{trial_index}"
        cell_dir.mkdir(parents=True, exist_ok=True)

        session_name = make_session_name(model, self._test_case.name, trial_index)
        history_dir = cell_dir / "history"
        history_dir.mkdir(parents=True, exist_ok=True)

        log_path = cell_dir / "chat.log"
        env = os.environ.copy()
        env["ZRB_LLM_HISTORY_DIR"] = str(history_dir)

        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                self._config.cli_name,
                "chat",
                "--interactive",
                "false",
                "--message",
                self._test_case.instruction,
                "--session",
                session_name,
                cwd=str(cell_dir),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self._config.timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                duration = time.monotonic() - start
                log_path.write_text(
                    f"[TIMEOUT after {self._config.timeout}s]\n",
                    encoding="utf-8",
                )
                return TrialResult(
                    model=model,
                    test_case=self._test_case.name,
                    trial_index=trial_index,
                    status="TIMEOUT",
                    duration=duration,
                    exit_code=-1,
                    log_path=str(log_path),
                )

            duration = time.monotonic() - start
            stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
            stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

            full_output = stdout + stderr
            log_path.write_text(full_output, encoding="utf-8")

            exit_code = proc.returncode or 0
            status: Literal["EXCELLENT", "PASS", "FAIL", "TIMEOUT", "ERROR"]
            token_fields = parse_cost_summary(stdout)

            # Determine status based on exit code and verification markers
            # @sdlc REQ-007: verification marker overrides exit code
            verification_marker = _extract_verification_marker(stdout)
            if verification_marker is not None:
                status = verification_marker
            elif exit_code != 0:
                status = "ERROR"
            else:
                # Default: non-ERROR status (will be determined by validator)
                status = "PASS"

            # @sdlc REQ-009: invoke validator if exit was clean
            verification_result: ValidationResult | None = None
            if status not in ("TIMEOUT", "ERROR") and self._test_case.validator is not None:
                try:
                    # @sdlc REQ-009
                    verification_result = self._test_case.validator.validate(
                        output_dir=cell_dir,
                        log_content=full_output,
                    )
                    # Validator result determines final status for clean exits
                    if verification_marker is None:
                        status = verification_result.status
                except Exception:
                    # @sdlc REQ-011
                    status = "ERROR"
                    verification_result = ValidationResult(
                        status="FAIL",
                        score=0.0,
                        details=[],
                    )

            return TrialResult(
                model=model,
                test_case=self._test_case.name,
                trial_index=trial_index,
                status=status,
                duration=duration,
                exit_code=exit_code,
                log_path=str(log_path),
                verification_result=verification_result,
                total_tokens=token_fields["total_tokens"],
                input_tokens=token_fields["input_tokens"],
                output_tokens=token_fields["output_tokens"],
                cache_read_tokens=token_fields["cache_read_tokens"],
            )

        except Exception as exc:
            duration = time.monotonic() - start
            log_path.write_text(f"[ERROR: {exc}]\n", encoding="utf-8")
            return TrialResult(
                model=model,
                test_case=self._test_case.name,
                trial_index=trial_index,
                status="ERROR",
                duration=duration,
                exit_code=-1,
                log_path=str(log_path),
            )


# ---------------------------------------------------------------------------
# Work Steward — orchestrates concurrent trial execution
# ---------------------------------------------------------------------------

# @sdlc REQ-002, REQ-010, RULE-012
class WorkSteward:
    """Schedules trial tasks with a concurrency semaphore."""

    def __init__(
        self,
        config: ExperimentConfig,
        test_cases: list[TestCase],
        output_dir: Path,
        resume_mgr: ResumeManager,
    ) -> None:
        """Initialize the work steward.

        Args:
        ----
            config: Experiment configuration.
            test_cases: Loaded test cases.
            output_dir: Root output directory.
            resume_mgr: Resume manager for persisting results.

        """
        self._config = config
        self._test_cases = test_cases
        self._output_dir = output_dir
        self._resume_mgr = resume_mgr
        self._semaphore = asyncio.Semaphore(config.parallelism)

    # @sdlc REQ-002, REQ-004, REQ-006, REQ-010
    async def run_all(self) -> list[TrialResult]:
        """Run all cells in the experiment grid.

        Returns
        -------
            All ``TrialResult`` instances.

        """
        # Build a lookup from test_case name to TestCase
        case_map = {tc.name: tc for tc in self._test_cases}

        cells = build_cell_plan(self._config)

        # @sdlc REQ-006: filter out completed cells
        pending_cells = [
            c for c in cells
            if not self._resume_mgr.is_completed(c.model, c.test_case, c.trial_index)
        ]

        async def _run_one(cell: Cell) -> None:
            async with self._semaphore:
                test_case = case_map[cell.test_case]
                runner = TrialRunner(self._config, test_case, self._output_dir)
                result = await runner.run(cell.model, cell.trial_index)
                # @sdlc REQ-003, REQ-017
                self._resume_mgr.append(result)

        tasks = [asyncio.create_task(_run_one(c)) for c in pending_cells]
        if tasks:
            await asyncio.gather(*tasks)

        return self._resume_mgr.results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# @sdlc REQ-007
def _extract_verification_marker(stdout: str) -> Literal["EXCELLENT", "PASS", "FAIL"] | None:
    """Check stdout for a ``VERIFICATION_RESULT:`` override marker.

    Args:
    ----
        stdout: Subprocess stdout text.

    Returns:
    -------
        The status if found, else ``None``.

    """
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("VERIFICATION_RESULT:"):
            marker = stripped.split(":", 1)[1].strip().upper()
            if marker in ("EXCELLENT", "PASS", "FAIL"):
                return marker  # type: ignore[return-value]
    return None


# @sdlc REQ-004, REQ-006
async def run_experiment(
    config: ExperimentConfig,
    test_cases: list[TestCase],
    output_dir: Path,
) -> list[TrialResult]:
    """Run a full experiment: all models x test cases x trials.

    Args:
    ----
        config: Experiment configuration.
        test_cases: Loaded test cases.
        output_dir: Root output directory for results.

    Returns:
    -------
        All ``TrialResult`` instances.

    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "results.json"
    resume_mgr = ResumeManager(results_path)
    resume_mgr.load()

    steward = WorkSteward(config, test_cases, output_dir, resume_mgr)
    return await steward.run_all()
