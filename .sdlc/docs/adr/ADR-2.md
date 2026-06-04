# ADR-2: Async Runner with asyncio

## Status
Accepted

## Context
An experiment launches N subprocesses (zrb chat) concurrently. The existing zrb llm-challenges runner uses `ThreadPoolExecutor` (synchronous subprocess calls). For reliable timeout handling, subprocess streams must be drained while the wall clock is monitored. `asyncio.create_subprocess_exec` with `asyncio.wait_for` provides this natively without threading.

## Decision
Use **asyncio** for the concurrent experiment runner. Each trial runs in an async task. `asyncio.Semaphore` controls parallelism. `asyncio.wait_for` enforces per-trial timeout. The CLI entry point wraps the async entry with `asyncio.run()`.

## Consequences
### Positive
- Native subprocess stream handling — no need for drainer threads
- `wait_for` raises `TimeoutError` cleanly; partial output is already on disk
- Scales better for I/O-bound workloads than threading

### Negative
- Slightly more complex error handling (task cancellation, cleanup)
- Existing `fut.result()` pattern must be replaced with `await asyncio.gather()`

## Implements Rules
- RULE-012 — Async for Concurrent Runs

## Verification
- The runner module has no `threading` or `concurrent.futures` imports
- Parallelism is controlled via `asyncio.Semaphore`
- Timeout uses `asyncio.wait_for`

## References
- Python docs: asyncio-subprocess
- Existing runner: `llm-challenges/runner.py` (thread-based pattern)
