from collections.abc import Iterator
from datetime import datetime

from app.models.enums import ResumeOrigin
from app.models.schemas import IngestedResume
from app.scanning.ingest_service import run_scan
from app.scanning.ingestor_base import ResumeIngestor

FIRST_RESUME = (
    b"Jordan Rivera\njordan.rivera@example.com\n"
    b"3 years backend engineering with Python and PostgreSQL. B.S. Computer Science."
)
UPSKILLED_RESUME = (
    b"Jordan Rivera\njordan.rivera@example.com\n"
    b"6 years backend engineering with Python, PostgreSQL, and Kubernetes. Now leading a small team."
)


class _TwoSubmissionIngestor(ResumeIngestor):
    """Same person, two submissions years apart with an upskilled resume —
    what a real long-lived candidate history looks like."""

    def scan(self, date_start=None, date_end=None) -> Iterator[IngestedResume]:
        yield IngestedResume(
            origin=ResumeOrigin.FOLDER,
            source_ref="/tmp/resumes",
            file_bytes=FIRST_RESUME,
            filename="jordan_2019.txt",
            date_submitted=datetime(2019, 3, 1),
        )
        yield IngestedResume(
            origin=ResumeOrigin.EMAIL,
            source_ref="acct:msg-2022",
            file_bytes=UPSKILLED_RESUME,
            filename="jordan_2022.txt",
            date_submitted=datetime(2022, 6, 15),
            sender_email="jordan.rivera@example.com",
        )


async def test_history_records_a_dated_entry_per_submission(storage, mock_llm, tmp_path):
    with storage.session() as session:
        await run_scan(
            ingestor=_TwoSubmissionIngestor(),
            storage=storage,
            session=session,
            candidates_dir=tmp_path,
            llm=mock_llm,
            summary_model="",
        )

        from sqlalchemy import select

        from app.models.db import Candidate

        candidate = session.execute(select(Candidate)).scalars().one()

    assert len(candidate.history) == 2
    assert candidate.history[0]["date"].startswith("2019-03-01")
    assert candidate.history[1]["date"].startswith("2022-06-15")
    assert "Initial application" in candidate.history[0]["note"]
    assert "Updated" in candidate.history[1]["note"]


async def test_history_stays_sorted_even_when_ingested_out_of_order(storage, mock_llm, tmp_path):
    class _ReversedOrderIngestor(ResumeIngestor):
        def scan(self, date_start=None, date_end=None):
            # Later submission ingested FIRST — simulates a folder walk or
            # email scan that doesn't happen to visit items chronologically.
            yield IngestedResume(
                origin=ResumeOrigin.EMAIL,
                source_ref="acct:msg-2022",
                file_bytes=UPSKILLED_RESUME,
                filename="jordan_2022.txt",
                date_submitted=datetime(2022, 6, 15),
                sender_email="jordan.rivera@example.com",
            )
            yield IngestedResume(
                origin=ResumeOrigin.FOLDER,
                source_ref="/tmp/resumes",
                file_bytes=FIRST_RESUME,
                filename="jordan_2019.txt",
                date_submitted=datetime(2019, 3, 1),
            )

    with storage.session() as session:
        await run_scan(
            ingestor=_ReversedOrderIngestor(),
            storage=storage,
            session=session,
            candidates_dir=tmp_path,
            llm=mock_llm,
            summary_model="",
        )

        from sqlalchemy import select

        from app.models.db import Candidate

        candidate = session.execute(select(Candidate)).scalars().one()

    dates = [h["date"] for h in candidate.history]
    assert dates == sorted(dates)

    # The 2022 resume was ingested FIRST (is_new=True at that point in
    # processing), but the 2019 one is chronologically earlier — the label
    # must reflect date order, not ingestion order.
    assert "Initial application" in candidate.history[0]["note"]
    assert candidate.history[0]["date"].startswith("2019")
    assert "Updated" in candidate.history[1]["note"]
