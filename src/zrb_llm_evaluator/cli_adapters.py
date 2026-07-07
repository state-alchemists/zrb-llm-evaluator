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
    * ``claude-code`` — invokes Claude Code's non-interactive "print" mode
      with streamed JSON output (``-p ... --output-format stream-json``);
      usage comes from the final ``result`` event, tool calls from the
      assistant messages' ``tool_use`` content blocks.
    * ``opencode`` — invokes opencode's non-interactive ``run`` mode with
      ``--format json`` (NDJSON events), verified against the opencode
      source (``packages/opencode/src/cli/cmd/run.ts``): usage comes from
      ``step_finish`` events, tool calls from ``tool_use`` events.

Anything else is treated as a dotted Python import path to a custom
``CliAdapter`` implementation (REQ-037), resolved by ``resolve_cli_adapter``.
The module must be importable (installed or on ``PYTHONPATH``) — the
current working directory is not automatically searched.

Each built-in adapter also carries two class attributes consumed by the
CLI layer: ``default_cli_name``, the binary name used when ``--cli-name``
isn't given (so ``--cli-template claude-code`` doesn't silently invoke
``zrb -p ...``), and ``version_args``, the argv suffix that prints the
CLI's version (zrb has a ``version`` subcommand; ``claude version`` would
be read as a prompt, so guessing is not safe there).
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from zrb_llm_evaluator.cost_parser import count_tool_calls_from_history, parse_cost_summary
from zrb_llm_evaluator.models import UsageSummary
from zrb_llm_evaluator.protocols import CliAdapter

if TYPE_CHECKING:
    from collections.abc import Iterator


# @sdlc EXPERIMENT-RUNNER:REQ-036
class ZrbCliAdapter:
    """Default ``CliAdapter``: preserves the exact pre-existing zrb behavior.

    Used when ``cli_template`` is unset or ``"zrb"``. Reproduces the
    subprocess invocation, environment variables, and usage/tool-call
    parsing previously hardcoded in ``TrialRunner`` (REQ-012, REQ-016,
    REQ-019) with no behavior change.
    """

    default_cli_name = "zrb"
    # zrb prints its version via a subcommand, not a --version flag.
    version_args = ("version",)

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


def _iter_json_objects(text: str) -> Iterator[dict[str, Any]]:
    """Yield every top-level JSON object embedded in ``text``, in order.

    Scans forward with ``raw_decode`` so noise before, between, or after
    the JSON payloads is skipped (the runner merges stderr into the same
    stream, so stray log lines around the payload are expected). Nested
    objects are not yielded separately — the scan jumps past each decoded
    document.
    """
    decoder = json.JSONDecoder()
    idx = text.find("{")
    while idx != -1:
        try:
            obj, end = decoder.raw_decode(text, idx)
        except ValueError:
            idx = text.find("{", idx + 1)
            continue
        if isinstance(obj, dict):
            yield obj
        idx = text.find("{", max(end, idx + 1))


def _last_json_object(text: str) -> dict[str, Any] | None:
    """Return the last top-level JSON object in ``text``, or ``None``."""
    last: dict[str, Any] | None = None
    for obj in _iter_json_objects(text):
        last = obj
    return last


# @sdlc EXPERIMENT-RUNNER:REQ-041
class ClaudeCodeCliAdapter:
    """``CliAdapter`` for Claude Code's non-interactive "print" mode.

    Invokes ``claude -p <instruction> --output-format stream-json --verbose
    --model <model> --dangerously-skip-permissions``. Stream mode (rather
    than plain ``--output-format json``) is what makes tool calls
    observable: the plain JSON result object carries only ``usage``, while
    the stream emits one JSON object per line including assistant messages
    whose ``content`` arrays contain ``tool_use`` blocks. The skip-
    permissions flag is the counterpart of zrb's ``--yolo true`` — without
    it, print mode denies every tool request and no agentic test case can
    pass. Claude Code manages its own session/history internally (no
    equivalent of zrb's ``{prefix}_LLM_HISTORY_DIR`` env var), so
    ``build_env`` passes the base environment through unchanged; the runner
    snapshots the captured stdout (the full event stream) to
    ``history_log_path`` (REQ-040), and that snapshot is what
    ``extract_tool_calls`` reads back.
    """

    default_cli_name = "claude"
    # Must be --version: ``claude version`` is read as an interactive prompt.
    version_args = ("--version",)

    def build_argv(
        self, cli_name: str, model: str, instruction: str, session_name: str,
    ) -> list[str]:
        """Build the ``{cli_name} -p ... --output-format stream-json ...`` argv."""
        return [
            cli_name,
            "-p",
            instruction,
            "--output-format",
            "stream-json",
            # stream-json in print mode requires --verbose.
            "--verbose",
            "--model",
            model,
            "--dangerously-skip-permissions",
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
        """Parse token usage from the final ``result`` event's ``usage`` block.

        The last top-level object carrying a ``usage`` dict wins — in
        stream mode that is the terminal ``result`` event (cumulative
        usage); with plain ``--output-format json`` output it is the single
        result object, so both shapes parse.
        """
        usage: dict[str, Any] | None = None
        for obj in _iter_json_objects(stdout):
            candidate = obj.get("usage")
            if isinstance(candidate, dict):
                usage = candidate
        if usage is None:
            return UsageSummary()
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        cache_read_tokens = int(usage.get("cache_read_input_tokens", 0) or 0)
        cache_write_tokens = int(usage.get("cache_creation_input_tokens", 0) or 0)
        return UsageSummary(
            total_tokens=(
                input_tokens + output_tokens + cache_read_tokens + cache_write_tokens
            ),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
        )

    def extract_tool_calls(self, history_log_path: Path) -> tuple[list[str], int]:
        """Extract tool names from ``tool_use`` blocks in the event stream.

        Reads the stdout snapshot at ``history_log_path`` and collects
        every assistant message content item with ``type == "tool_use"``.
        Empty on any failure (missing file, no parseable events).
        """
        if not history_log_path.is_file():
            return [], 0
        try:
            text = history_log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return [], 0
        names: list[str] = []
        for obj in _iter_json_objects(text):
            message = obj.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_use":
                    name = item.get("name")
                    if isinstance(name, str) and name:
                        names.append(name)
        return names, len(names)


# @sdlc EXPERIMENT-RUNNER:REQ-042
class OpencodeCliAdapter:
    """``CliAdapter`` for opencode's non-interactive ``run`` mode.

    Verified against the opencode source
    (``packages/opencode/src/cli/cmd/run.ts`` and the SDK event types):

    * ``opencode run <message> --model <provider/model> --format json``
      emits NDJSON events (one JSON object per line): ``tool_use`` events
      carry the tool name at ``part.tool``; ``step_finish`` events carry
      per-step token counts at ``part.tokens`` (``input``, ``output``,
      ``reasoning``, ``cache.read``, ``cache.write``).
    * ``--model`` expects ``provider/model``, so the evaluator's
      ``provider:name`` ids are translated by replacing the first ``:``.
    * ``--session`` continues an *existing* session id and exits non-zero
      for an unknown one, so it is not passed; ``--title`` labels the
      fresh session with the trial's session name instead.
    * ``--dangerously-skip-permissions`` is the counterpart of zrb's
      ``--yolo true``.

    opencode stores history in its XDG data dir, so the runner's stdout
    snapshot (the full NDJSON event stream) serves as the history file
    (REQ-040) and is what ``extract_tool_calls`` reads back.
    """

    default_cli_name = "opencode"
    version_args = ("--version",)

    def build_argv(
        self, cli_name: str, model: str, instruction: str, session_name: str,
    ) -> list[str]:
        """Build the ``{cli_name} run <instruction> --format json ...`` argv."""
        return [
            cli_name,
            "run",
            instruction,
            "--model",
            model.replace(":", "/", 1),
            "--format",
            "json",
            "--title",
            session_name,
            "--dangerously-skip-permissions",
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
        """Sum per-step token counts across all ``step_finish`` events."""
        input_tokens = 0
        output_tokens = 0
        cache_read_tokens = 0
        total_tokens = 0
        for obj in _iter_json_objects(stdout):
            if obj.get("type") != "step_finish":
                continue
            part = obj.get("part")
            if not isinstance(part, dict):
                continue
            tokens = part.get("tokens")
            if not isinstance(tokens, dict):
                continue
            step_input = int(tokens.get("input", 0) or 0)
            step_output = int(tokens.get("output", 0) or 0)
            step_reasoning = int(tokens.get("reasoning", 0) or 0)
            cache = tokens.get("cache")
            cache_read = int(cache.get("read", 0) or 0) if isinstance(cache, dict) else 0
            cache_write = int(cache.get("write", 0) or 0) if isinstance(cache, dict) else 0
            input_tokens += step_input
            output_tokens += step_output
            cache_read_tokens += cache_read
            total_tokens += (
                step_input + step_output + step_reasoning + cache_read + cache_write
            )
        return UsageSummary(
            total_tokens=total_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
        )

    def extract_tool_calls(self, history_log_path: Path) -> tuple[list[str], int]:
        """Extract tool names from ``tool_use`` events in the NDJSON snapshot."""
        if not history_log_path.is_file():
            return [], 0
        try:
            text = history_log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return [], 0
        names: list[str] = []
        for obj in _iter_json_objects(text):
            if obj.get("type") != "tool_use":
                continue
            part = obj.get("part")
            if isinstance(part, dict):
                name = part.get("tool")
                if isinstance(name, str) and name:
                    names.append(name)
        return names, len(names)


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
        # Not just ImportError: a custom module can raise anything at import
        # time (SyntaxError, RuntimeError, ...) and it must still surface as
        # the CLI's clean "CLI template error" path rather than a traceback.
        except Exception as exc:
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
    if missing:
        msg = (
            f"cli_template {cli_template!r} resolves to {cls!r}, which does not "
            f"implement the CliAdapter protocol (missing methods: {missing})"
        )
        raise ValueError(msg)
    return cast("CliAdapter", instance)
