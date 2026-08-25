"""Bounded concurrency for per-item async LLM calls (matching's deep-score/
judge passes, ingest's per-candidate embedding). A plain asyncio.gather over
hundreds of items would fire them all at once and trip provider rate limits;
running them one at a time (the previous behavior everywhere this is used)
leaves most of the wall-clock time idle waiting on network I/O. A semaphore
caps how many are in flight without serializing them."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


async def bounded_gather(items: list[T], worker: Callable[[T], Awaitable[R]], max_concurrent: int) -> list[R]:
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _run(item: T) -> R:
        async with semaphore:
            return await worker(item)

    return await asyncio.gather(*(_run(item) for item in items))
