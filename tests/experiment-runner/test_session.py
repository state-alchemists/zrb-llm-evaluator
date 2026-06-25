# COVERS: EXPERIMENT-RUNNER:REQ-001, EXPERIMENT-RUNNER:UT-001

"""Tests for session name generation."""

from __future__ import annotations

from zrb_llm_evaluator.loader import make_session_name


class TestSessionNameGeneration:
    """Tests for unique session names — @sdlc EXPERIMENT-RUNNER:REQ-001."""

    def test_session_name_generates_unique_per_trial(self) -> None:
        """EXPERIMENT-RUNNER:UT-001: Three unique session strings, each containing model/case/trial."""
        names = set()
        for trial in range(1, 4):
            name = make_session_name("openai:gpt-4o", "py-test", trial)
            names.add(name)
            assert "openai_gpt-4o" in name
            assert "py-test" in name
            assert f"trial-{trial}" in name

        # All three must be unique
        assert len(names) == 3

    def test_session_name_different_models(self) -> None:
        """Different models produce different session names."""
        n1 = make_session_name("openai:gpt-4o", "case-a", 1)
        n2 = make_session_name("anthropic:claude-3", "case-a", 1)
        assert n1 != n2

    def test_session_name_is_filesystem_safe(self) -> None:
        """Session name contains only safe characters."""
        name = make_session_name("openai:gpt-4o", "test-case_123", 1)
        # Should not contain colons
        assert ":" not in name
        # Should be a valid filename component
        assert all(c.isalnum() or c in "_-." for c in name)
