from collections.abc import Iterator
from datetime import datetime

from app.models.enums import ResumeOrigin
from app.models.schemas import IngestedResume
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

    def scan(self, date_start=None, date_end=None) -> Iterator[IngestedResume]:
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
