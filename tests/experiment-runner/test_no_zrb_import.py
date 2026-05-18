# COVERS: RULE-005, UT-025

"""Test that the runner does not import zrb internals."""

from __future__ import annotations

import subprocess
import sys


class TestNoZrbImport:
    """Ensures runner module avoids importing zrb — @sdlc RULE-005."""

    def test_no_zrb_import_in_runner(self) -> None:
        """UT-025: Running 'python -c' that imports the runner should not import zrb."""
        code = """
import sys
# Import all runner-related modules
from zrb_llm_evaluator import models, protocols, cost_parser, loader, runner
# Check that zrb is NOT in sys.modules (excluding our own package)
for mod_name in list(sys.modules.keys()):
    if mod_name.startswith("zrb") and not mod_name.startswith("zrb_llm_evaluator"):
        print(f"UNEXPECTED ZRB IMPORT: {mod_name}")
        sys.exit(1)
print("OK: no zrb internals imported")
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd="/Users/gofrendigunawan/zrb-llm-evaluator",
        )
        assert result.returncode == 0, f"stdout: {result.stdout}, stderr: {result.stderr}"
        assert "OK: no zrb internals imported" in result.stdout
