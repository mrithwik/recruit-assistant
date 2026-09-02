"""FanInIngestor — proves it actually interleaves multiple ingestors'
scan() streams concurrently (not one exhausted before the next starts),
isolates a failing source's error to that source alone (doesn't cancel or
truncate healthy siblings — see the QA finding this file's isolation tests
guard against), and doesn't drop items from a source that finishes quickly
while another is still going."""

import asyncio
import time
from collections.abc import AsyncIterator
from datetime import datetime

import pytest

from app.models.enums import ResumeOrigin
from app.models.schemas import IngestedResume
from app.scanning.fan_in_ingestor import FanInIngestor
from app.scanning.ingestor_base import ResumeIngestor


class _SlowIngestor(ResumeIngestor):
    """Yields `count` items, each after a fixed delay — simulates network-
    bound fetches (a real mailbox API call per page/message)."""

    def __init__(self, label: str, count: int, delay: float):
        self.label = label
        self.count = count
        self.delay = delay

    async def scan(self, date_start=None, date_end=None) -> AsyncIterator[IngestedResume]:
        for i in range(self.count):
            await asyncio.sleep(self.delay)
            yield IngestedResume(
                origin=ResumeOrigin.EMAIL,
                source_ref=f"{self.label}:{i}",
                file_bytes=f"resume {self.label} {i}".encode(),
                filename=f"{self.label}-{i}.txt",
                date_submitted=datetime(2026, 1, 1),
            )


class _FailingIngestor(ResumeIngestor):
    def __init__(self, fail_after: float = 0.0):
        self.fail_after = fail_after

    async def scan(self, date_start=None, date_end=None) -> AsyncIterator[IngestedResume]:
        yield IngestedResume(
            origin=ResumeOrigin.EMAIL,
            source_ref="failing:0",
            file_bytes=b"one item before failure",
            filename="failing-0.txt",
            date_submitted=datetime(2026, 1, 1),
        )
        await asyncio.sleep(self.fail_after)
        raise RuntimeError("simulated mailbox API failure")


@pytest.mark.asyncio
async def test_two_sources_are_interleaved_not_run_one_after_the_other():
    # Two sources, each 5 items at 0.02s apart = 0.1s if sequential.
    # Interleaved, total wall-clock should track the slower single source
    # (~0.1s), not the sum of both (~0.2s).
    sources = [("a", _SlowIngestor("a", count=5, delay=0.02)), ("b", _SlowIngestor("b", count=5, delay=0.02))]
    fan_in = FanInIngestor(sources)

    start = time.monotonic()
    items = [item async for item in fan_in.scan()]
    elapsed = time.monotonic() - start

    assert len(items) == 10
    assert {item.source_ref for item in items} == {f"a:{i}" for i in range(5)} | {f"b:{i}" for i in range(5)}
    # Generous slack for CI/scheduling jitter — the point is "closer to one
    # source's total than to the sum of both," not a tight bound.
    assert elapsed < 0.15, f"expected overlap (~0.1s), took {elapsed:.3f}s — looks sequential"
    assert fan_in.errors == []


@pytest.mark.asyncio
async def test_a_failing_source_does_not_truncate_a_healthy_sibling():
    """QA regression: an earlier version treated any source's exception as
    a poison pill that cancelled every other still-producing source
    immediately — a healthy 100-item source only got 4 items out before a
    sibling's failure (at 0.05s) cut off the whole combined stream. The
    fix: a source's failure only stops *that* source; every other source
    must still run to completion."""
    healthy = _SlowIngestor("healthy", count=100, delay=0.001)
    failing = _FailingIngestor(fail_after=0.05)
    fan_in = FanInIngestor([("healthy", healthy), ("failing", failing)])

    items = [item async for item in fan_in.scan()]

    healthy_items = [item for item in items if item.source_ref.startswith("healthy:")]
    assert len(healthy_items) == 100, "the healthy source must run to completion, unaffected by its sibling's failure"
    assert any(item.source_ref == "failing:0" for item in items)
    assert fan_in.errors == ["failing: simulated mailbox API failure"]
    assert fan_in.failed_labels == {"failing"}


@pytest.mark.asyncio
async def test_a_failing_source_never_raises_out_of_scan():
    """The whole point of isolating a source's failure: scan() itself must
    complete normally (no exception propagating to the caller) even when
    one of its sources failed — callers read fan_in.errors afterward
    instead, the same way the old per-account loop's
    combined.errors.append(...) worked."""
    fan_in = FanInIngestor([("failing", _FailingIngestor())])
    items = [item async for item in fan_in.scan()]  # must not raise
    assert len(items) == 1
    assert fan_in.errors == ["failing: simulated mailbox API failure"]


@pytest.mark.asyncio
async def test_empty_source_list_yields_nothing():
    fan_in = FanInIngestor([])
    items = [item async for item in fan_in.scan()]
    assert items == []
    assert fan_in.errors == []
