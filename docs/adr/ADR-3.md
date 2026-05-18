# ADR-3: Leverage zrb's Built-in History for History Capture

## Status
Accepted

## Context
Each trial runs `zrb chat --interactive false --message <instruction> --session <name>`. zrb's `FileHistoryManager` automatically saves the full conversation history as structured JSON (`pydantic_ai` ModelMessage format) to the directory configured by `ZRB_LLM_HISTORY_DIR`. The file is written after each turn, so partial output survives timeout. There is no need to manually stream subprocess stdout to a log file.

## Decision
Before each trial, set `ZRB_LLM_HISTORY_DIR` to the experiment's per-cell output directory. Pass a deterministic session name via `--session eval-{model_safe}-{test_case}-trial-{N}`. After the subprocess finishes (or is killed on timeout), the conversation history is available as `{history_dir}/{session_name}.json`. The validator receives the path to this file and can read it using `FileHistoryManager.load()` or raw JSON parsing.

The subprocess stdout is still captured for cost-summary line parsing (token counts, exit code), but the authoritative conversation history is the JSON file written by zrb itself.

## Consequences
### Positive
- No custom streaming or log-writing code — zrb handles persistence natively
- Structured JSON (pydantic_ai messages) is richer than raw text
- Survives timeout: zrb writes history incrementally per turn
- Works with any white-labeled zrb fork (all use FileHistoryManager)

### Negative
- Requires setting `ZRB_LLM_HISTORY_DIR` env var before each trial
- The JSON format is pydantic_ai-specific (not a general-purpose format)
- Must pass a unique `--session` name per trial to avoid filename collisions

## Implements Rules
- None directly — satisfies AC-003 (timeout survival) and product requirement

## Verification
- Each trial sets `ZRB_LLM_HISTORY_DIR` to a per-cell subdirectory before invoking zrb
- The JSON file exists at the expected path after the subprocess exits (even on timeout)
- Unit test: mock a short zrb chat run, verify history JSON is readable

## References
- `FileHistoryManager`: `~/zrb/src/zrb/llm/history_manager/file_history_manager.py`
- Non-interactive session runner: `~/zrb/src/zrb/llm/task/chat/runner_mixin.py:44-58`
