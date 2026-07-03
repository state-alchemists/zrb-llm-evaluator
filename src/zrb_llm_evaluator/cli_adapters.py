# GENERATED FROM SPEC: .sdlc/specs/experiment-runner/spec.md
# IMPLEMENTS: EXPERIMENT-RUNNER:REQ-035, EXPERIMENT-RUNNER:REQ-036, EXPERIMENT-RUNNER:REQ-037,
# IMPLEMENTS: EXPERIMENT-RUNNER:REQ-038, EXPERIMENT-RUNNER:REQ-039, EXPERIMENT-RUNNER:REQ-040,
# IMPLEMENTS: EXPERIMENT-RUNNER:REQ-041, EXPERIMENT-RUNNER:REQ-042, RULE-001, RULE-004, RULE-005

"""Built-in ``CliAdapter`` implementations and ``cli_template`` resolution.

Per RULE-005, the runner must invoke the CLI under test via subprocess and
must never import that CLI's internal Python APIs. This module defines the
CLI-specific plumbing (argv construction, env vars, and output parsing) for
each supported template, entirely behind the ``CliAdapter`` protocol
(see ``protocols.py``), so ``runner.py`` stays CLI-agnostic.

Built-in templates:
    * ``zrb`` (default) — preserves the exact pre-existing ``zrb chat``
      invocation, env vars, and 💸-line parsing (REQ-012 / REQ-016 / REQ-019).
    * ``claude-code`` — invokes Claude Code's documented non-interactive
      "print" mode with structured JSON output (``-p ... --output-format
      json``) and parses token usage from the JSON's ``usage`` block.
    * ``opencode`` — invokes opencode's non-interactive ``run`` mode.
      **The exact flags and usage-reporting format are not verified against
      a real opencode installation** (see spec.md's "CLI Templates"
      section) — this is a best-effort implementation that should be
      validated (and adjusted if needed) against a real opencode build.

Anything else is treated as a dotted Python import path to a custom
``CliAdapter`` implementation (REQ-037), resolved by ``resolve_cli_adapter``.
"""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from typing import Any

from zrb_llm_evaluator.cost_parser import count_tool_calls_from_history, parse_cost_summary
from zrb_llm_evaluator.models import UsageSummary
from zrb_llm_evaluator.protocols import CliAdapter


# @sdlc EXPERIMENT-RUNNER:REQ-036
class ZrbCliAdapter:
    """Default ``CliAdapter``: preserves the exact pre-existing zrb behavior.

    Used when ``cli_template`` is unset or ``"zrb"``. Reproduces the
    subprocess invocation, environment variables, and usage/tool-call
    parsing previously hardcoded in ``TrialRunner`` (REQ-012, REQ-016,
    REQ-019) with no behavior change.
    """

    def build_argv(
        self, cli_name: str, model: str, instruction: str, session_name: str,
    ) -> list[str]:
        """Build the ``{cli_name} chat --interactive false --yolo true ...`` argv."""
        return [
            cli_name,
            "chat",
            "--interactive",
            "false",
            "--yolo",
            "true",
            "--model",
            model,
            "--message",
            instruction,
            "--session",
            session_name,
        ]

    def build_env(
        self,
        base_env: dict[str, str],
        history_dir: Path,
        journal_dir: Path,
        env_prefix: str,
    ) -> dict[str, str]:
        """Overlay ``{env_prefix}_LLM_HISTORY_DIR``/``{env_prefix}_LLM_JOURNAL_DIR``."""
        env = dict(base_env)
        env[f"{env_prefix}_LLM_HISTORY_DIR"] = str(history_dir)
        env[f"{env_prefix}_LLM_JOURNAL_DIR"] = str(journal_dir)
        return env

    def history_log_path(self, history_dir: Path, session_name: str) -> Path:
        """Return the path zrb itself writes the session history JSON to."""
        return history_dir / f"{session_name}.json"

    def parse_usage(self, stdout: str) -> UsageSummary:
        """Parse zrb's ``💸`` usage summary line (REQ-019)."""
        fields = parse_cost_summary(stdout)
        return UsageSummary(**fields)

    def extract_tool_calls(self, history_log_path: Path) -> tuple[list[str], int]:
        """Extract tool-call names from the zrb history JSON (REQ-019)."""
        return count_tool_calls_from_history(history_log_path)


def _last_json_object(text: str) -> dict[str, Any] | None:
    """Best-effort extraction of the last top-level JSON object in ``text``.

    Tries a straight ``json.loads`` first (the common case where stdout is
    exactly one JSON document); falls back to scanning backwards for a
    ``{`` that starts a parseable object, tolerating incidental log noise
    before/after the JSON payload.
    """
    stripped = text.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        parsed = None
    else:
        return parsed if isinstance(parsed, dict) else None

    start = stripped.rfind("{")
    while start != -1:
        candidate = stripped[start:]
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            start = stripped.rfind("{", 0, start)
            continue
        return parsed if isinstance(parsed, dict) else None
    return None


# @sdlc EXPERIMENT-RUNNER:REQ-041
class ClaudeCodeCliAdapter:
    """``CliAdapter`` for Claude Code's non-interactive "print" mode.

    Invokes ``claude -p <instruction> --output-format json --model
    <model>``, per Claude Code's documented non-interactive/print mode, and
    parses token usage from the JSON payload's ``usage`` block. Claude Code
    manages its own session/history internally (no equivalent of zrb's
    ``{prefix}_LLM_HISTORY_DIR`` env var), so ``build_env`` passes the base
    environment through unchanged; the runner itself snapshots the captured
    stdout to ``history_log_path`` so partial history still survives a
    timeout (REQ-040), and that same JSON snapshot is what
    ``extract_tool_calls`` reads back.
    """

    def build_argv(
        self, cli_name: str, model: str, instruction: str, session_name: str,
    ) -> list[str]:
        """Build the ``{cli_name} -p ... --output-format json ...`` argv."""
        return [
            cli_name,
            "-p",
            instruction,
            "--output-format",
            "json",
            "--model",
            model,
        ]

    def build_env(
        self,
        base_env: dict[str, str],
        history_dir: Path,
        journal_dir: Path,
        env_prefix: str,
    ) -> dict[str, str]:
        """Pass the base environment through unchanged (no zrb-style env vars)."""
        return dict(base_env)

    def history_log_path(self, history_dir: Path, session_name: str) -> Path:
        """Return where the runner should snapshot Claude Code's JSON output."""
        return history_dir / f"{session_name}.json"

    def parse_usage(self, stdout: str) -> UsageSummary:
        """Parse token usage from Claude Code's JSON ``usage`` block."""
        data = _last_json_object(stdout)
        usage = data.get("usage") if isinstance(data, dict) else None
        if not isinstance(usage, dict):
            return UsageSummary()
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        cache_read_tokens = int(usage.get("cache_read_input_tokens", 0) or 0)
        return UsageSummary(
            total_tokens=input_tokens + output_tokens + cache_read_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
        )

    def extract_tool_calls(self, history_log_path: Path) -> tuple[list[str], int]:
        """Extract tool-call names from a ``tool_uses`` array, if present."""
        if not history_log_path.is_file():
            return [], 0
        try:
            data: Any = json.loads(history_log_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            return [], 0
        names: list[str] = []
        if isinstance(data, dict):
            tool_uses = data.get("tool_uses")
            if isinstance(tool_uses, list):
                for item in tool_uses:
                    if isinstance(item, dict):
                        name = item.get("name")
                        if isinstance(name, str) and name:
                            names.append(name)
        return names, len(names)


# @sdlc EXPERIMENT-RUNNER:REQ-042
class OpencodeCliAdapter:
    """``CliAdapter`` for opencode's non-interactive ``run`` mode.

    .. warning::
        opencode's exact CLI flags and usage-reporting format are **not
        verified against a real opencode installation** — this is a
        best-effort implementation per spec.md's "CLI Templates" section.
        Confirm ``build_argv``/``parse_usage`` against a real opencode
        build and adjust if they differ; that's a normal code change, not
        a spec/requirement change (REQ-042 only commits to "non-interactive
        invocation + structured usage parsing").

    Assumes a plain-text usage summary of the form
    ``Tokens: <input> in / <output> out / <cache> cached / <total>
    total`` may appear in stdout; absent that, usage defaults to zero
    (matching REQ-039's "default when the adapter cannot determine a
    value" semantics). Tool-call extraction best-effort reuses the zrb
    history JSON shape, since opencode's own history format is unverified.
    """

    _USAGE_PATTERN = re.compile(
        r"Tokens:\s*(?P<input>\d+)\s*in\s*/\s*(?P<output>\d+)\s*out\s*/\s*"
        r"(?P<cache>\d+)\s*cached\s*/\s*(?P<total>\d+)\s*total",
        re.IGNORECASE,
    )

    def build_argv(
        self, cli_name: str, model: str, instruction: str, session_name: str,
    ) -> list[str]:
        """Build the ``{cli_name} run <instruction> --model <model> ...`` argv."""
        return [
            cli_name,
            "run",
            instruction,
            "--model",
            model,
            "--session",
            session_name,
        ]

    def build_env(
        self,
        base_env: dict[str, str],
        history_dir: Path,
        journal_dir: Path,
        env_prefix: str,
    ) -> dict[str, str]:
        """Pass the base environment through unchanged (no zrb-style env vars)."""
        return dict(base_env)

    def history_log_path(self, history_dir: Path, session_name: str) -> Path:
        """Return where the runner should snapshot opencode's captured output."""
        return history_dir / f"{session_name}.json"

    def parse_usage(self, stdout: str) -> UsageSummary:
        """Best-effort parse of an opencode usage summary line."""
        match = self._USAGE_PATTERN.search(stdout)
        if not match:
            return UsageSummary()
        return UsageSummary(
            total_tokens=int(match.group("total")),
            input_tokens=int(match.group("input")),
            output_tokens=int(match.group("output")),
            cache_read_tokens=int(match.group("cache")),
        )

    def extract_tool_calls(self, history_log_path: Path) -> tuple[list[str], int]:
        """Best-effort tool-call extraction, reusing the zrb history JSON parser."""
        return count_tool_calls_from_history(history_log_path)


_BUILTIN_ADAPTERS: dict[str, type[CliAdapter]] = {
    "zrb": ZrbCliAdapter,
    "claude-code": ClaudeCodeCliAdapter,
    "opencode": OpencodeCliAdapter,
}

_REQUIRED_METHODS: tuple[str, ...] = (
    "build_argv",
    "build_env",
    "history_log_path",
    "parse_usage",
    "extract_tool_calls",
)


# @sdlc EXPERIMENT-RUNNER:REQ-035, EXPERIMENT-RUNNER:REQ-037, EXPERIMENT-RUNNER:REQ-038,
# @sdlc RULE-004, RULE-005
def resolve_cli_adapter(cli_template: str) -> CliAdapter:
    """Resolve ``ExperimentConfig.cli_template`` to a ``CliAdapter`` instance.

    Looks up one of the built-in names first (``zrb``, ``claude-code``,
    ``opencode``); anything else is treated as a dotted Python import path
    (``"pkg.module.ClassName"``) and dynamically imported (REQ-037).

    This is called once per experiment, before any trial begins, so a bad
    template name or a custom adapter missing required methods fails fast
    (REQ-038) rather than mid-experiment.

    Args:
    ----
        cli_template: One of the built-in names, or a dotted import path.

    Returns:
    -------
        An instantiated ``CliAdapter``.

    Raises:
    ------
        ValueError: If ``cli_template`` cannot be resolved to a class
            implementing ``CliAdapter`` (unknown name, unimportable module,
            missing class, construction failure, or missing methods).

    """
    cls: type[Any] | None = _BUILTIN_ADAPTERS.get(cli_template)
    if cls is None:
        if "." not in cli_template:
            msg = (
                f"Unknown cli_template {cli_template!r}: must be one of "
                f"{sorted(_BUILTIN_ADAPTERS)} or a dotted import path to a "
                "class implementing CliAdapter"
            )
            raise ValueError(msg)
        module_path, _, class_name = cli_template.rpartition(".")
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            msg = (
                f"Cannot import module {module_path!r} for cli_template "
                f"{cli_template!r}: {exc}"
            )
            raise ValueError(msg) from exc
        cls = getattr(module, class_name, None)
        if cls is None:
            msg = (
                f"Module {module_path!r} has no attribute {class_name!r} "
                f"(cli_template={cli_template!r})"
            )
            raise ValueError(msg)

    try:
        instance = cls()
    except Exception as exc:
        msg = f"Cannot instantiate CliAdapter for cli_template {cli_template!r}: {exc}"
        raise ValueError(msg) from exc

    missing = [
        name for name in _REQUIRED_METHODS if not callable(getattr(instance, name, None))
    ]
    if missing or not isinstance(instance, CliAdapter):
        msg = (
            f"cli_template {cli_template!r} resolves to {cls!r}, which does not "
            f"implement the CliAdapter protocol (missing methods: {missing})"
        )
        raise ValueError(msg)
    # The isinstance check above narrows `instance` to CliAdapter for mypy.
    return instance
