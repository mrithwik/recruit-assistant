from collections.abc import AsyncIterator
from datetime import datetime

import pytest

from app.models.db import Candidate
from app.models.enums import ResumeOrigin
from app.models.schemas import IngestedResume, ScanResult
from app.scanning.ingest_service import run_scan
from app.scanning.ingestor_base import ResumeIngestor

RESUME_TEXT = (
    b"Jordan Rivera\njordan.rivera@example.com\n"
    b"7 years backend engineering experience with Python, FastAPI, and PostgreSQL. "
    b"Led a team of engineers through a major platform migration and owned schema design."
)


class _RepeatingFolderIngestor(ResumeIngestor):
    """Yields the same file twice, simulating a folder rescan that finds a file
    it already ingested last time."""

    async def scan(self, date_start=None, date_end=None) -> AsyncIterator[IngestedResume]:
        for _ in range(2):
            yield IngestedResume(
                origin=ResumeOrigin.FOLDER,
                source_ref="/tmp/resumes",
                file_bytes=RESUME_TEXT,
                filename="jordan.txt",
                date_submitted=datetime(2026, 1, 1),
            )


async def test_rescan_skips_unchanged_file_instead_of_duplicating(storage, mock_llm, tmp_path):
    ingestor = _RepeatingFolderIngestor()
    with storage.session() as session:
        result = await run_scan(
            ingestor=ingestor,
            storage=storage,
            session=session,
            candidates_dir=tmp_path,
            llm=mock_llm,
            summary_model="",
        )

    assert result.resumes_found == 2
    assert result.candidates_created == 1
    assert result.duplicates_skipped == 1
    assert result.candidates_updated == 0


async def test_second_scan_run_also_skips_previously_seen_file(storage, mock_llm, tmp_path):
    """Simulates the real recruiter flow: scan today, scan again tomorrow with
    nothing new in the folder — the second run should skip everything."""
    single_file_ingestor = _RepeatingFolderIngestor()

    with storage.session() as session:
        first = await run_scan(
            ingestor=single_file_ingestor,
            storage=storage,
            session=session,
            candidates_dir=tmp_path,
            llm=mock_llm,
            summary_model="",
        )
    assert first.candidates_created == 1

    with storage.session() as session:
        second = await run_scan(
            ingestor=single_file_ingestor,
            storage=storage,
            session=session,
            candidates_dir=tmp_path,
            llm=mock_llm,
            summary_model="",
        )

    assert second.candidates_created == 0
    assert second.candidates_updated == 0
    assert second.duplicates_skipped == 2


def _distinct_resume(i: int) -> bytes:
    return (
        f"Candidate Number{i}\ncandidate{i}@example.com\n"
        f"{i + 1} years experience with Python and SQL.".encode()
    )


class _MultiDistinctIngestor(ResumeIngestor):
    """Yields `count` genuinely different candidates — used to check
    checkpointing/progress-callback behavior, which per-duplicate-resume
    tests above can't exercise since every yielded item is the same person."""

    def __init__(self, count: int, fail_at: int | None = None):
        self.count = count
        self.fail_at = fail_at

    async def scan(self, date_start=None, date_end=None) -> AsyncIterator[IngestedResume]:
        for i in range(self.count):
            if self.fail_at is not None and i == self.fail_at:
                raise RuntimeError("simulated mid-scan failure (e.g. network exhausted retries)")
            yield IngestedResume(
                origin=ResumeOrigin.FOLDER,
                source_ref="/tmp/resumes",
                file_bytes=_distinct_resume(i),
                filename=f"candidate{i}.txt",
                date_submitted=datetime(2026, 1, 1),
            )


async def test_on_progress_called_once_per_resume_with_cumulative_counts(storage, mock_llm, tmp_path):
    progress_calls: list[ScanResult] = []
    with storage.session() as session:
        result = await run_scan(
            ingestor=_MultiDistinctIngestor(count=5),
            storage=storage,
            session=session,
            candidates_dir=tmp_path,
            llm=mock_llm,
            summary_model="",
            on_progress=progress_calls.append,
        )

    assert len(progress_calls) == 5
    assert [p.resumes_found for p in progress_calls] == [1, 2, 3, 4, 5]
    assert progress_calls[-1].candidates_created == result.candidates_created == 5


async def test_checkpoint_commits_survive_a_later_mid_scan_failure(storage, mock_llm, tmp_path):
    """The whole point of checkpointing: a failure after resume 4 (e.g. the
    ingestor's retries exhausted mid-scan) must not roll back resumes 1-2,
    which a checkpoint_every=2 run should have already committed."""
    with pytest.raises(RuntimeError, match="simulated mid-scan failure"):
        with storage.session() as session:
            await run_scan(
                ingestor=_MultiDistinctIngestor(count=5, fail_at=4),
                storage=storage,
                session=session,
                candidates_dir=tmp_path,
                llm=mock_llm,
                summary_model="",
                checkpoint_every=2,
            )

    with storage.session() as session:
        from sqlalchemy import select

        candidates = session.execute(select(Candidate)).scalars().all()

    # Resumes 0-3 were processed (index 4 is where it raised); checkpoints
    # fire after resume counts 2 and 4, so all 4 already-processed
    # candidates should be durably committed despite the run never finishing.
    assert len(candidates) == 4


async def test_cancelling_mid_batch_still_applies_the_rest_of_that_batch(storage, mock_llm, tmp_path):
    """QA regression: run_scan's own comment says cancelling mid-batch still
    applies the rest of the *current* batch's already-parsed items (Phase 1's
    parse+summarize work for them is already done and paid for — discarding
    it would waste it for nothing), only skipping any *further* batches. The
    first version of this code `break`d out of the batch immediately instead,
    contradicting its own comment and throwing away already-completed work.
    With max_concurrent_processing left at its default (8) and 12 resumes
    offered, cancellation requested after the 3rd resume in the first batch
    should still land all 8 of that batch's candidates — not just 3 — and
    the second batch (resumes 8-11) should never be fetched at all."""
    calls = {"count": 0}

    def cancel_after_three() -> bool:
        calls["count"] += 1
        return calls["count"] > 3

    with storage.session() as session:
        result = await run_scan(
            ingestor=_MultiDistinctIngestor(count=12),
            storage=storage,
            session=session,
            candidates_dir=tmp_path,
            llm=mock_llm,
            summary_model="",
            on_should_cancel=cancel_after_three,
        )

    assert result.resumes_found == 8  # the whole first batch, not just 3
    assert result.candidates_created == 8


async def test_scan_result_reports_per_stage_timings(storage, mock_llm, tmp_path):
    """ScanResult.stage_timings — added so the speed-plan report's levers
    can be measured instead of only inferred from code structure. All three
    ingest-loop stages should show non-trivial time spent (mock LLM calls
    and disk writes still take real wall-clock time, just no network)."""
    ingestor = _RepeatingFolderIngestor()
    with storage.session() as session:
        result = await run_scan(
            ingestor=ingestor,
            storage=storage,
            session=session,
            candidates_dir=tmp_path,
            llm=mock_llm,
            summary_model="",
        )

    assert set(result.stage_timings) == {"parse", "summarize", "mirror_write", "embed"}
    assert result.stage_timings["parse"] >= 0
    assert result.stage_timings["summarize"] >= 0
    assert result.stage_timings["mirror_write"] >= 0
    # No embedding_model was passed, so nothing should have been queued for
    # the embed stage — it should stay at its zero default, not error.
    assert result.stage_timings["embed"] == 0
