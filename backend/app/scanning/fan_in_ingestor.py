"""FanInIngestor — wraps several ResumeIngestors (e.g. one per connected
mailbox) into a single ingestor whose scan() interleaves all of their
yielded resumes concurrently, instead of one source's entire scan finishing
before the next starts. See the speed-plan report's lever #3.

Feeding the combined stream through *one* run_scan() call — rather than one
run_scan() call per source — is what keeps this safe, not just fast:
identity resolution and mirror-writing stay serialized through run_scan's
own single session/fingerprints dict/seen_sources set, exactly as they are
for a single source today. Running several run_scan() calls concurrently
against the same SQLAlchemy Session instead would risk real corruption
(overlapping session.add()/commit() calls) and duplicate-candidate races
(two sources yielding the same person concurrently, each independently
deciding "new candidate" from their own stale in-memory fingerprint
snapshot) — this design sidesteps both by only parallelizing the network
fetch, never the session-touching part.

One source failing must never take down the others sharing this scan — the
old per-account sequential loop gave every account that isolation for free
(one account's exception only ever affected itself and whatever was queued
after it in that account's own turn); an earlier version of this class
didn't preserve it, treating any one source's exception as a poison pill
that cancelled every other still-producing source immediately (see QA
finding — a healthy 100-item source paired with a source that failed after
0.05s only got 4 of its own items out before the whole combined stream was
cut off). A source's failure is now caught, recorded in `self.errors`
(label-attributed, readable by the caller once scan() is exhausted, the
same way the old loop's `combined.errors.append(...)` worked), and simply
stops that one source from contributing further — every other source keeps
running to completion, exactly as before."""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime

from app.models.schemas import IngestedResume
from app.scanning.ingestor_base import ResumeIngestor

# Sentinel marking one source's stream as exhausted (whether it ran out
# normally or failed) — distinct from a legitimate IngestedResume.
_DONE = object()


class FanInIngestor(ResumeIngestor):
    def __init__(self, sources: list[tuple[str, ResumeIngestor]]):
        """`sources` is (label, ingestor) pairs — the label (an account's
        email address, say) is used only to attribute a mid-scan failure to
        the specific source that raised it."""
        self.sources = sources
        self.errors: list[str] = []
        # Labels of sources that failed mid-scan — lets a caller avoid
        # crediting a failed source with e.g. a fresh "last scanned at"
        # timestamp, without having to parse `self.errors`' formatted
        # strings back apart.
        self.failed_labels: set[str] = set()

    async def scan(
        self,
        date_start: datetime | None = None,
        date_end: datetime | None = None,
    ) -> AsyncIterator[IngestedResume]:
        if not self.sources:
            return

        queue: asyncio.Queue = asyncio.Queue()

        async def _pump(label: str, ingestor: ResumeIngestor) -> None:
            try:
                async for item in ingestor.scan(date_start=date_start, date_end=date_end):
                    await queue.put(item)
            except Exception as exc:  # noqa: BLE001 - isolated to this one source, doesn't stop the others
                self.errors.append(f"{label}: {exc}")
                self.failed_labels.add(label)
            finally:
                await queue.put(_DONE)

        tasks = [asyncio.create_task(_pump(label, ingestor)) for label, ingestor in self.sources]
        remaining = len(tasks)
        try:
            while remaining:
                item = await queue.get()
                if item is _DONE:
                    remaining -= 1
                    continue
                yield item
        finally:
            # Whether we exhausted normally or the caller stopped early
            # (cancellation, an unrelated exception downstream), no pump
            # should keep running unseen in the background — every
            # remaining producer's fetch (real network I/O for email) is
            # cancelled here. A source that already failed on its own has
            # nothing left to cancel; this is a no-op for it.
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
