# GENERATED FROM SPEC: specs/experiment-runner/requirements.md
# IMPLEMENTS: REQ-001, REQ-002, REQ-003, REQ-004, REQ-005, REQ-006, REQ-007, REQ-008,
#    REQ-009, REQ-010, REQ-011, REQ-012, REQ-016, REQ-017, REQ-018, REQ-019,
#    REQ-020, REQ-021, REQ-022, REQ-023, REQ-024,
#    NFR-001, NFR-002, RULE-005, RULE-012

"""Async experiment runner with subprocess orchestration."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import signal
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from zrb_llm_evaluator.cost_parser import (
    count_tool_calls_from_history,
    parse_cost_summary,
)
from zrb_llm_evaluator.loader import TestCase, make_safe_name, make_session_name
from zrb_llm_evaluator.models import (
    Experiment,
    ExperimentConfig,
    TrialResult,
    ValidationCheck,
    ValidationResult,
)

logger = logging.getLogger(__name__)


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
        self._result_map: dict[tuple[str, str, int], TrialResult] = {}

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
            self._result_map.clear()
            return []

        raw = self._results_path.read_text(encoding="utf-8")
        if not raw.strip():
            self._results = []
            self._completed_keys.clear()
            self._result_map.clear()
            return []

        data: list[dict[str, object]] = json.loads(raw)
        self._results = [TrialResult.model_validate(item) for item in data]
        for r in self._results:
            key = (r.model, r.test_case, r.trial_index)
            self._completed_keys.add(key)
            self._result_map[key] = r
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
        result = self._result_map.get(key)
        if result is None:
            return False
        return result.status in TERMINAL_STATUSES

    # @sdlc REQ-003, REQ-017
    def append(self, result: TrialResult) -> None:
        """Atomically append a trial result to ``results.json``.

        Args:
        ----
            result: The completed trial result.

        """
        self._results.append(result)
        key = (result.model, result.test_case, result.trial_index)
        self._completed_keys.add(key)
        self._result_map[key] = result
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
            os.replace(str(tmp), str(self._results_path))
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

# @sdlc REQ-001, REQ-005, REQ-012, REQ-016, REQ-018, REQ-020, REQ-021, REQ-022, REQ-023, REQ-024
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

    # @sdlc REQ-001, REQ-005, REQ-016, REQ-018, REQ-019, REQ-020, REQ-021, REQ-022, REQ-023, REQ-024
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

        # If cell_dir survived a prior incomplete attempt (interrupted before
        # the result was appended), wipe it so the retry starts from a pristine
        # staged workdir rather than overlaying onto stale LLM artifacts.
        if cell_dir.exists():
            shutil.rmtree(cell_dir)
        cell_dir.mkdir(parents=True, exist_ok=True)

        # Nested workdir is the subprocess cwd; evaluation artifacts
        # (stdout.log, history/) live as siblings in cell_dir and are
        # invisible to the LLM (per ADR-7 / REQ-020 / REQ-021).
        nested_workdir = cell_dir / "workdir"
        nested_workdir.mkdir(parents=True, exist_ok=True)

        # Stage the test case's workdir contents into the nested workdir
        # only when the source directory actually exists. Loader always sets
        # ``self._test_case.workdir`` to ``{test_case_dir}/workdir``; when
        # that's absent we keep nested_workdir empty (REQ-022). The source
        # is by construction never the test_case_dir itself, so validator.py
        # and instruction.txt can never be staged (REQ-024).
        if self._test_case.workdir.is_dir():
            shutil.copytree(
                self._test_case.workdir, nested_workdir, dirs_exist_ok=True,
            )

        session_name = make_session_name(model, self._test_case.name, trial_index)
        history_dir = cell_dir / "history"
        history_dir.mkdir(parents=True, exist_ok=True)
        journal_dir = cell_dir / "notes"
        journal_dir.mkdir(parents=True, exist_ok=True)

        log_path = cell_dir / "stdout.log"
        history_log_path = history_dir / f"{session_name}.json"
        prefix = self._config.env_prefix
        env = os.environ.copy()
        env[f"{prefix}_LLM_HISTORY_DIR"] = str(history_dir)
        env[f"{prefix}_LLM_JOURNAL_DIR"] = str(journal_dir)

        start = time.monotonic()
        # Stream subprocess stdout/stderr directly to disk so partial output
        # survives a timeout (the runner kills the subprocess on timeout, and
        # buffered PIPE bytes would otherwise be lost).
        try:
            with open(log_path, "wb") as log_file:
                proc = await asyncio.create_subprocess_exec(
                    self._config.cli_name,
                    "chat",
                    "--interactive",
                    "false",
                    "--yolo",
                    "true",
                    "--model",
                    model,
                    "--message",
                    self._test_case.instruction,
                    "--session",
                    session_name,
                    cwd=str(nested_workdir),
                    env=env,
                    stdout=log_file,
                    stderr=asyncio.subprocess.STDOUT,
                    start_new_session=True,
                )

                try:
                    await asyncio.wait_for(proc.wait(), timeout=self._config.timeout)
                except asyncio.TimeoutError:
                    # @sdlc REQ-005: kill the entire descendant process group,
                    # not just the direct child. `zrb chat` spawns LLM HTTP
                    # workers that survive a SIGKILL to the leader alone.
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    await proc.wait()
                    log_file.flush()
                    log_file.write(
                        f"\n[TIMEOUT after {self._config.timeout}s]\n".encode(
                            "utf-8",
                        ),
                    )
                    duration = time.monotonic() - start
                    tool_calls, tool_call_count = count_tool_calls_from_history(
                        history_log_path,
                    )
                    return TrialResult(
                        model=model,
                        test_case=self._test_case.name,
                        trial_index=trial_index,
                        status="TIMEOUT",
                        duration=duration,
                        exit_code=-1,
                        log_path=str(history_log_path),
                        stdout_log_path=str(log_path),
                        tool_calls=tool_calls,
                        tool_call_count=tool_call_count,
                    )

            duration = time.monotonic() - start
            full_output = log_path.read_text(encoding="utf-8", errors="replace")
            stdout = full_output  # combined stdout+stderr stream

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
                        output_dir=nested_workdir,
                        log_content=full_output,
                    )
                    # Validator result determines final status for clean exits
                    if verification_marker is None:
                        status = verification_result.status
                except Exception as exc:
                    # @sdlc REQ-011
                    status = "ERROR"
                    verification_result = ValidationResult(
                        status="FAIL",
                        score=0.0,
                        details=[
                            ValidationCheck(
                                name="validator_error",
                                passed=False,
                                message=str(exc),
                            ),
                        ],
                    )

            tool_calls, tool_call_count = count_tool_calls_from_history(
                history_log_path,
            )
            return TrialResult(
                model=model,
                test_case=self._test_case.name,
                trial_index=trial_index,
                status=status,
                duration=duration,
                exit_code=exit_code,
                log_path=str(history_log_path),
                stdout_log_path=str(log_path),
                verification_result=verification_result,
                total_tokens=token_fields["total_tokens"],
                input_tokens=token_fields["input_tokens"],
                output_tokens=token_fields["output_tokens"],
                cache_read_tokens=token_fields["cache_read_tokens"],
                tool_calls=tool_calls,
                tool_call_count=tool_call_count,
            )

        except Exception as exc:
            duration = time.monotonic() - start
            log_path.write_text(f"[ERROR: {exc}]\n", encoding="utf-8")
            tool_calls, tool_call_count = count_tool_calls_from_history(
                history_log_path,
            )
            return TrialResult(
                model=model,
                test_case=self._test_case.name,
                trial_index=trial_index,
                status="ERROR",
                duration=duration,
                exit_code=-1,
                log_path=str(history_log_path),
                stdout_log_path=str(log_path),
                tool_calls=tool_calls,
                tool_call_count=tool_call_count,
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

        total = len(pending_cells)
        skipped = len(cells) - total
        if skipped:
            logger.info(
                "Resuming: %d cell(s) already completed, %d pending", skipped, total,
            )
        else:
            logger.info(
                "Planned: %d trial(s) across %d cell(s)", total, len(cells),
            )

        completed_count = 0
        count_lock = asyncio.Lock()

        async def _run_one(cell: Cell) -> None:
            nonlocal completed_count
            async with self._semaphore:
                logger.info(
                    "START  %s / %s / trial-%d",
                    cell.model, cell.test_case, cell.trial_index,
                )
                test_case = case_map[cell.test_case]
                runner = TrialRunner(self._config, test_case, self._output_dir)
                result = await runner.run(cell.model, cell.trial_index)
                # @sdlc REQ-003, REQ-017
                self._resume_mgr.append(result)
                async with count_lock:
                    completed_count += 1
                    done = completed_count
                logger.info(
                    "DONE   %s / %s / trial-%d status=%s duration=%.1fs (%d/%d)",
                    cell.model,
                    cell.test_case,
                    cell.trial_index,
                    result.status,
                    result.duration,
                    done,
                    total,
                )

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
) -> Experiment:
    """Run a full experiment: all models x test cases x trials.

    Builds (or resumes) an ``Experiment`` envelope persisted as
    ``experiment.json`` in ``output_dir``.  On resume, the existing envelope's
    ``id`` and ``started_at`` are preserved so a single experiment can be
    rerun without losing its identity.

    Args:
    ----
        config: Experiment configuration.
        test_cases: Loaded test cases.
        output_dir: Root output directory for results.

    Returns:
    -------
        The completed ``Experiment`` envelope.

    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "results.json"
    experiment_path = output_dir / "experiment.json"

    resume_mgr = ResumeManager(results_path)
    resume_mgr.load()

    experiment = _load_or_init_experiment(experiment_path, config)

    steward = WorkSteward(config, test_cases, output_dir, resume_mgr)
    results = await steward.run_all()

    experiment.results = results
    experiment.completed_at = datetime.now(timezone.utc)
    _persist_experiment(experiment, experiment_path)

    return experiment


def _load_or_init_experiment(
    experiment_path: Path, config: ExperimentConfig,
) -> Experiment:
    """Load an existing experiment envelope or create a fresh one.

    On resume, ``id`` and ``started_at`` are preserved; ``config`` is taken
    from the current invocation (the most recent caller wins, matching how
    ``ResumeManager`` already treats CLI args as authoritative).
    """
    if experiment_path.is_file():
        try:
            data = json.loads(experiment_path.read_text(encoding="utf-8"))
            existing = Experiment.model_validate(data)
            existing.config = config
            return existing
        except (json.JSONDecodeError, ValueError):
            # Corrupt envelope — fall through to creating a fresh one.
            pass
    return Experiment(
        config=config,
        started_at=datetime.now(timezone.utc),
    )


def _persist_experiment(experiment: Experiment, experiment_path: Path) -> None:
    """Atomically write the experiment envelope to disk."""
    parent = experiment_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp: Path | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(parent),
            prefix=".experiment_tmp_",
            suffix=".json",
        )
        os.close(fd)
        tmp = Path(tmp_path)
        tmp.write_text(
            json.dumps(experiment.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
        os.replace(str(tmp), str(experiment_path))
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink(missing_ok=True)
