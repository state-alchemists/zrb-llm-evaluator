# COVERS: EXPERIMENT-RUNNER:REQ-038

"""Fixture module that fails at import time with a non-ImportError.

Used to verify ``resolve_cli_adapter`` converts arbitrary import-time
failures into a clean ``ValueError`` instead of leaking a traceback.
"""

msg = "boom at import time"
raise RuntimeError(msg)
