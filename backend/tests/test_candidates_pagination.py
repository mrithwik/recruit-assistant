"""Pins candidates_page() — server-side filtering/search/sort/pagination that
replaced loading every candidate into Python and slicing there (see
project-log: All Candidates was slow at real volume because of this)."""

import uuid
from datetime import datetime, timedelta

from app.models.db import Candidate, ResumeSource


def _make_candidate(name_first, name_last, email, skills, days_ago, origin="folder"):
    candidate = Candidate(
        id=str(uuid.uuid4()),
        identity_fingerprint=f"email:{email}",
        legal_first_name=name_first,
        legal_last_name=name_last,
        email=email,
        work_visa_status="us_citizen",
        skills=skills,
        date_submitted=datetime.utcnow() - timedelta(days=days_ago),
    )
    source = ResumeSource(
        id=str(uuid.uuid4()),
        candidate_id=candidate.id,
        origin=origin,
        source_ref=f"ref:{email}",
        content_hash=f"hash:{email}",
        file_path=f"/tmp/{email}",
        date_submitted=candidate.date_submitted,
    )
    return candidate, source


def _seed(storage):
    with storage.session() as session:
        rows = [
            _make_candidate("Ada", "Lovelace", "ada@example.com", ["python", "fastapi"], days_ago=0, origin="email"),
            _make_candidate("Grace", "Hopper", "grace@example.com", ["python", "sql"], days_ago=2, origin="folder"),
            _make_candidate("Alan", "Turing", "alan@example.com", ["rust", "cryptography"], days_ago=1, origin="folder"),
        ]
        for candidate, source in rows:
            session.add(candidate)
            session.add(source)
        session.commit()


def test_pagination_limit_and_offset(storage):
    _seed(storage)
    with storage.session() as session:
        page1, total = storage.candidates_page(session, None, None, None, None, "recent", limit=2, offset=0)
        page2, total2 = storage.candidates_page(session, None, None, None, None, "recent", limit=2, offset=2)

        assert total == total2 == 3
        assert len(page1) == 2
        assert len(page2) == 1
        assert {c.id for c in page1} & {c.id for c in page2} == set()


def test_sort_recent_orders_newest_first(storage):
    _seed(storage)
    with storage.session() as session:
        results, _ = storage.candidates_page(session, None, None, None, None, "recent", limit=10, offset=0)
        assert [c.legal_first_name for c in results] == ["Ada", "Alan", "Grace"]


def test_sort_name_asc(storage):
    _seed(storage)
    with storage.session() as session:
        results, _ = storage.candidates_page(session, None, None, None, None, "name_asc", limit=10, offset=0)
        assert [c.legal_first_name for c in results] == ["Ada", "Alan", "Grace"]


def test_source_filter(storage):
    _seed(storage)
    with storage.session() as session:
        results, total = storage.candidates_page(session, None, None, "email", None, "recent", limit=10, offset=0)
        assert total == 1
        assert results[0].legal_first_name == "Ada"


def test_query_matches_name_email_and_skill(storage):
    _seed(storage)
    with storage.session() as session:
        by_name, _ = storage.candidates_page(session, None, None, None, "Turing", "recent", limit=10, offset=0)
        assert [c.legal_first_name for c in by_name] == ["Alan"]

        by_skill, _ = storage.candidates_page(session, None, None, None, "cryptography", "recent", limit=10, offset=0)
        assert [c.legal_first_name for c in by_skill] == ["Alan"]

        by_email, _ = storage.candidates_page(session, None, None, None, "grace@", "recent", limit=10, offset=0)
        assert [c.legal_first_name for c in by_email] == ["Grace"]
