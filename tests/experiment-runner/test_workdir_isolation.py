# COVERS: REQ-020, REQ-021, REQ-022, REQ-023, REQ-024,
#   UT-027, UT-028, UT-029, UT-030, UT-031, IT-005

"""Tests for the per-trial nested workdir isolation (ADR-7)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from zrb_llm_evaluator.loader import load_test_case, make_safe_name
from zrb_llm_evaluator.models import ExperimentConfig
from zrb_llm_evaluator.runner import TrialRunner


def _mock_subprocess(mock_proc: AsyncMock):
    """Return an async function that returns the given mock_proc."""

    async def _create(*args: object, **kwargs: object) -> AsyncMock:
        return mock_proc

    return _create


def _config(tmp_path: Path, case_dir: Path, cli_name: str = "zrb") -> ExperimentConfig:
    return ExperimentConfig(
        models=["openai:gpt-4o"],
        test_case_dirs=[case_dir],
        trials=1,
        parallelism=1,
        timeout=30,
        cli_name=cli_name,
    )


def _make_case(
    tmp_path: Path,
    *,
    with_workdir: bool,
    workdir_files: dict[str, str] | None = None,
) -> Path:
    """Create a test case directory with optional workdir/."""
    case_dir = tmp_path / "case"
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "instruction.txt").write_text("do thing", encoding="utf-8")
    (case_dir / "validator.py").write_text(
        "from zrb_llm_evaluator.models import ValidationResult\n"
        "class V:\n"
        "    def validate(self, output_dir, log_content, trace=None):\n"
        "        return ValidationResult(status='PASS', score=1.0, details=[])\n"
        "validator = V()\n",
        encoding="utf-8",
    )
    if with_workdir:
        wd = case_dir / "workdir"
        wd.mkdir(parents=True, exist_ok=True)
        for rel, contents in (workdir_files or {}).items():
            target = wd / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents, encoding="utf-8")
    return case_dir


# @sdlc REQ-020
class TestSubprocessCwdIsNestedWorkdir:
    """UT-027 / REQ-020 — subprocess cwd is the nested workdir, not the cell dir."""

    @pytest.mark.asyncio
    async def test_subprocess_cwd_is_nested_workdir(self, tmp_path: Path) -> None:
        case_dir = _make_case(tmp_path, with_workdir=True, workdir_files={"seed.txt": "ok"})
        tc = load_test_case(case_dir)
        output_dir = tmp_path / "out"

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch.object(asyncio, "create_subprocess_exec") as mock_exec:
            mock_exec.return_value = mock_proc
            runner = TrialRunner(_config(tmp_path, case_dir), tc, output_dir)
            await runner.run("openai:gpt-4o", 1)

        call_kwargs = mock_exec.call_args.kwargs
        cwd = call_kwargs["cwd"]
        assert cwd.endswith("/workdir"), f"cwd {cwd!r} must end in /workdir"
        # And cwd must NOT equal the cell directory itself.
        safe_model = make_safe_name("openai:gpt-4o")
        cell_dir = output_dir / safe_model / tc.name / "trial-1"
        assert Path(cwd) != cell_dir
        assert Path(cwd) == cell_dir / "workdir"


# @sdlc REQ-021
class TestEvaluationArtifactsOutsideWorkdir:
    """UT-028 / REQ-021 — stdout.log + history/ are siblings of workdir/."""

    @pytest.mark.asyncio
    async def test_evaluation_artifacts_outside_workdir(self, tmp_path: Path) -> None:
        case_dir = _make_case(tmp_path, with_workdir=True, workdir_files={"seed.txt": "ok"})
        tc = load_test_case(case_dir)
        output_dir = tmp_path / "out"

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"some output\n", b""))
        mock_proc.returncode = 0

        with patch.object(asyncio, "create_subprocess_exec", _mock_subprocess(mock_proc)):
            runner = TrialRunner(_config(tmp_path, case_dir), tc, output_dir)
            await runner.run("openai:gpt-4o", 1)

        safe_model = make_safe_name("openai:gpt-4o")
        cell_dir = output_dir / safe_model / tc.name / "trial-1"

        # Evaluation artifacts live in cell_dir.
        assert (cell_dir / "stdout.log").is_file()
        assert (cell_dir / "history").is_dir()
        # And they must NOT be inside the nested workdir.
        assert not (cell_dir / "workdir" / "stdout.log").exists()
        assert not (cell_dir / "workdir" / "history").exists()


# @sdlc REQ-022
class TestEmptyWorkdirCreatedWhenNoSource:
    """UT-029 / REQ-022 — empty workdir created when test case has no workdir/."""

    @pytest.mark.asyncio
    async def test_empty_workdir_created_when_no_source(self, tmp_path: Path) -> None:
        case_dir = _make_case(tmp_path, with_workdir=False)
        tc = load_test_case(case_dir)
        output_dir = tmp_path / "out"

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch.object(asyncio, "create_subprocess_exec", _mock_subprocess(mock_proc)):
            runner = TrialRunner(_config(tmp_path, case_dir), tc, output_dir)
            await runner.run("openai:gpt-4o", 1)

        safe_model = make_safe_name("openai:gpt-4o")
        nested = output_dir / safe_model / tc.name / "trial-1" / "workdir"
        assert nested.is_dir()
        # Empty — no validator.py, no instruction.txt, no LLM-staged seed files.
        assert list(nested.iterdir()) == []


# @sdlc REQ-023
class TestStagedFilesLandInNestedWorkdir:
    """UT-030 / REQ-023 — staged files land in cell_dir/workdir/, not cell_dir."""

    @pytest.mark.asyncio
    async def test_staged_files_land_in_nested_workdir(self, tmp_path: Path) -> None:
        case_dir = _make_case(
            tmp_path,
            with_workdir=True,
            workdir_files={"seed.txt": "seed-content", "data/notes.md": "note-content"},
        )
        tc = load_test_case(case_dir)
        output_dir = tmp_path / "out"

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch.object(asyncio, "create_subprocess_exec", _mock_subprocess(mock_proc)):
            runner = TrialRunner(_config(tmp_path, case_dir), tc, output_dir)
            await runner.run("openai:gpt-4o", 1)

        safe_model = make_safe_name("openai:gpt-4o")
        cell_dir = output_dir / safe_model / tc.name / "trial-1"

        # Files appear inside the nested workdir.
        assert (cell_dir / "workdir" / "seed.txt").read_text() == "seed-content"
        assert (cell_dir / "workdir" / "data" / "notes.md").read_text() == "note-content"
        # Files do NOT appear at the cell_dir root.
        assert not (cell_dir / "seed.txt").exists()
        assert not (cell_dir / "data").exists()


# @sdlc REQ-024
class TestMetadataFilesNeverStaged:
    """UT-031 / REQ-024 — validator.py / instruction.txt never copied into workdir."""

    @pytest.mark.asyncio
    async def test_metadata_files_never_staged(self, tmp_path: Path) -> None:
        case_dir = _make_case(
            tmp_path,
            with_workdir=True,
            workdir_files={"foo.txt": "foo"},
        )
        tc = load_test_case(case_dir)
        output_dir = tmp_path / "out"

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch.object(asyncio, "create_subprocess_exec", _mock_subprocess(mock_proc)):
            runner = TrialRunner(_config(tmp_path, case_dir), tc, output_dir)
            await runner.run("openai:gpt-4o", 1)

        safe_model = make_safe_name("openai:gpt-4o")
        nested = output_dir / safe_model / tc.name / "trial-1" / "workdir"

        assert (nested / "foo.txt").is_file()
        assert not (nested / "validator.py").exists()
        assert not (nested / "instruction.txt").exists()


# @sdlc REQ-020, REQ-021, REQ-024
class TestIsolationEndToEnd:
    """IT-005 / REQ-020 + REQ-021 + REQ-024 — real subprocess sees only staged files."""

    @pytest.mark.asyncio
    async def test_isolation_end_to_end(self, tmp_path: Path) -> None:
        case_dir = _make_case(
            tmp_path,
            with_workdir=True,
            workdir_files={"data.txt": "payload"},
        )
        tc = load_test_case(case_dir)
        output_dir = tmp_path / "out"

        # Assert the structural facts the LLM would observe by listing its cwd.
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch.object(asyncio, "create_subprocess_exec", _mock_subprocess(mock_proc)):
            runner = TrialRunner(_config(tmp_path, case_dir), tc, output_dir)
            await runner.run("openai:gpt-4o", 1)

        safe_model = make_safe_name("openai:gpt-4o")
        nested = output_dir / safe_model / tc.name / "trial-1" / "workdir"

        visible_to_llm = {p.name for p in nested.iterdir()}
        # Only the staged file is visible inside cwd.
        assert visible_to_llm == {"data.txt"}
        # And evaluation artifacts are siblings, not children.
        cell_dir = nested.parent
        sibling_names = {p.name for p in cell_dir.iterdir()}
        assert "workdir" in sibling_names
        assert "stdout.log" in sibling_names
        assert "history" in sibling_names
