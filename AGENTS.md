# zrb-llm-evaluator

## Overview
A reusable framework for running structured LLM experiments against `zrb chat`. Runs N models × M test cases × T trials, captures full LLM history to disk, and validates results through user-defined typed validators.

## Essential Commands
```bash
# Install
poetry install

# Test
poetry run pytest

# Lint
poetry run ruff check

# Run experiment
zrb-llm-evaluator run --models openai:gpt-4o google-gla:gemini-2.5-flash
```

## Architecture
| Directory | Purpose |
|-----------|---------|
| `src/zrb_llm_evaluator/` | Source code (runner, models, report) |
| `.sdlc/docs/product.md` | Product vision |
| `.sdlc/docs/tech.md` | Tech decisions |
| `.sdlc/docs/test-strategy.md` | Testing approach |
| `.sdlc/rules.md` | Project constitution (invariants) |
