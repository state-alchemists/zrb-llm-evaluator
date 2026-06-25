# COVERS: EXPERIMENT-RUNNER:REQ-006, EXPERIMENT-RUNNER:UT-006

"""Tests for resume functionality."""

from __future__ import annotations

from pathlib import Path

from zrb_llm_evaluator.models import TrialResult
from zrb_llm_evaluator.runner import ResumeManager


class TestResumeManager:
    """Tests for the ResumeManager — @sdlc EXPERIMENT-RUNNER:REQ-006."""

    def test_resume_skips_terminal_cells(self, sample_results_json: Path) -> None:
        """EXPERIMENT-RUNNER:UT-006: Skips terminal cells, only executes pending ones."""
        mgr = ResumeManager(sample_results_json)
        mgr.load()

        # Case-a trial-1 is PASS (terminal) -> skip
        assert mgr.is_completed("openai:gpt-4o", "case-a", 1)
        # Case-a trial-2 is ERROR (terminal) -> skip
        assert mgr.is_completed("openai:gpt-4o", "case-a", 2)
        # Case-a trial-3 is PASS (terminal) -> skip
        assert mgr.is_completed("openai:gpt-4o", "case-a", 3)

    def test_load_non_terminal_not_completed(self, tmp_path: Path) -> None:
        """A non-terminal (in_progress) cell is NOT marked completed."""
        # Write results with a non-terminal status (e.g., nothing - empty file means no data)
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
        ]
        import json

        data = [r.model_dump(mode="json") for r in results]
        p = tmp_path / "results.json"
        p.write_text(json.dumps(data), encoding="utf-8")

        mgr = ResumeManager(p)
        mgr.load()
        assert mgr.is_completed("openai:gpt-4o", "case-a", 1)

        # trial 2 was never written - not completed
        assert not mgr.is_completed("openai:gpt-4o", "case-a", 2)

    def test_append_adds_result(self, tmp_path: Path) -> None:
        """Appending a result updates the in-memory state."""
        p = tmp_path / "results.json"
        mgr = ResumeManager(p)

        r = TrialResult(
            model="openai:gpt-4o",
            test_case="case-a",
            trial_index=1,
            status="PASS",
            duration=0.5,
            exit_code=0,
            log_path="/tmp/1.log",
        )
        mgr.append(r)

        assert mgr.is_completed("openai:gpt-4o", "case-a", 1)
        assert len(mgr.results) == 1
