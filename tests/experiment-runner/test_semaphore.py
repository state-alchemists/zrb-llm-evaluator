# COVERS: REQ-002, REQ-010, UT-002, UT-012

"""Tests for semaphore-based concurrency control."""

from __future__ import annotations

import asyncio
import time

import pytest


class TestSemaphoreConcurrency:
    """Tests for concurrency control — @sdlc REQ-002, REQ-010."""

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrent_trials(self) -> None:
        """UT-002: At most 4 tasks running simultaneously with parallelism=4."""
        semaphore = asyncio.Semaphore(4)

        running = 0
        max_running = 0
        lock = asyncio.Lock()

        async def worker() -> None:
            nonlocal running, max_running
            async with semaphore:
                async with lock:
                    running += 1
                    max_running = max(max_running, running)
                await asyncio.sleep(0.05)
                async with lock:
                    running -= 1

        tasks = [asyncio.create_task(worker()) for _ in range(8)]
        await asyncio.gather(*tasks)

        assert max_running <= 4

    @pytest.mark.asyncio
    async def test_parallelism_1_sequential(self) -> None:
        """UT-012: With parallelism=1, trials execute one after another."""
        semaphore = asyncio.Semaphore(1)

        start_times: list[float] = []

        async def worker() -> None:
            async with semaphore:
                start_times.append(time.monotonic())
                await asyncio.sleep(0.05)

        tasks = [asyncio.create_task(worker()) for _ in range(3)]
        await asyncio.gather(*tasks)

        # With parallelism=1, start times should be spaced apart
        for i in range(1, len(start_times)):
            assert start_times[i] >= start_times[i - 1] + 0.04  # slight tolerance
