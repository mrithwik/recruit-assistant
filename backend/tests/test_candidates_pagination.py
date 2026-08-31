"""Pins candidates_page() — server-side filtering/search/sort/pagination that
replaced loading every candidate into Python and slicing there (see
project-log: All Candidates was slow at real volume because of this)."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select

from app.models.db import Candidate, Job, Match, ResumeSource
from app.routes.candidates import _batch_email_links


def _make_candidate(
    name_first,
    name_last,
    email,
    skills,
    days_ago,
    origin="folder",
    employment_status="unknown",
    work_visa_status="us_citizen",
    experience_years=0.0,
):
    candidate = Candidate(
        id=str(uuid.uuid4()),
        identity_fingerprint=f"email:{email}",
        legal_first_name=name_first,
        legal_last_name=name_last,
        email=email,
        employment_status=employment_status,
        work_visa_status=work_visa_status,
        skills=skills,
        experience_years=experience_years,
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
            _make_candidate(
                "Ada", "Lovelace", "ada@example.com", ["python", "fastapi"], days_ago=0, origin="email",
                employment_status="actively_looking", experience_years=3.0,
            ),
            _make_candidate(
                "Grace", "Hopper", "grace@example.com", ["python", "sql"], days_ago=2, origin="folder",
                employment_status="employed", experience_years=8.0,
            ),
            _make_candidate(
                "Alan", "Turing", "alan@example.com", ["rust", "cryptography"], days_ago=1, origin="folder",
                employment_status="employed", work_visa_status="h1b", experience_years=12.0,
            ),
        ]
        for candidate, source in rows:
            session.add(candidate)
            session.add(source)
        session.commit()


def test_needs_attention_filter_matches_red_flag_or_missing_info(storage):
    _seed(storage)
    with storage.session() as session:
        candidates = {c.email: c.id for c in session.execute(select(Candidate)).scalars()}
        job = Job(id=str(uuid.uuid4()), title="Engineer", raw_text="...")
        session.add(job)
        session.add(
            Match(
                id=str(uuid.uuid4()),
                job_id=job.id,
                candidate_id=candidates["ada@example.com"],
                score=10.0,
                tier="red_flagged",
            )
        )
        session.add(
            Match(
                id=str(uuid.uuid4()),
                job_id=job.id,
                candidate_id=candidates["grace@example.com"],
                score=70.0,
                tier="good_match",
                missing_info=["work authorization"],
            )
        )
        session.add(
            Match(
                id=str(uuid.uuid4()),
                job_id=job.id,
                candidate_id=candidates["alan@example.com"],
                score=90.0,
                tier="great_match",
            )
        )
        session.commit()

    with storage.session() as session:
        results, total = storage.candidates_page(
            session, None, None, None, None, "recent", limit=10, offset=0, needs_attention=True
        )
        assert total == 2
        assert {c.email for c in results} == {"ada@example.com", "grace@example.com"}

        unfiltered, unfiltered_total = storage.candidates_page(
            session, None, None, None, None, "recent", limit=10, offset=0, needs_attention=False
        )
        assert unfiltered_total == 3


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


def test_skills_filter_matches_any_selected_skill(storage):
    _seed(storage)
    with storage.session() as session:
        results, total = storage.candidates_page(
            session, None, None, None, None, "recent", limit=10, offset=0, skills=["sql", "cryptography"]
        )
        assert total == 2
        assert {c.legal_first_name for c in results} == {"Grace", "Alan"}


def test_skills_filter_excludes_substring_false_positives(storage):
    # "sql" shouldn't match a candidate whose only skill is "postgresql" via
    # a naive substring match on the raw JSON — the quoted-value match in
    # candidates_page guards against this.
    _seed(storage)
    with storage.session() as session:
        extra, source = _make_candidate("Nia", "Extra", "nia@example.com", ["postgresql"], days_ago=0)
        session.add(extra)
        session.add(source)
        session.commit()

        results, total = storage.candidates_page(
            session, None, None, None, None, "recent", limit=10, offset=0, skills=["sql"]
        )
        assert total == 1
        assert results[0].legal_first_name == "Grace"


def test_employment_status_filter(storage):
    _seed(storage)
    with storage.session() as session:
        results, total = storage.candidates_page(
            session, None, None, None, None, "recent", limit=10, offset=0, employment_statuses=["employed"]
        )
        assert total == 2
        assert {c.legal_first_name for c in results} == {"Grace", "Alan"}


def test_work_visa_status_filter(storage):
    _seed(storage)
    with storage.session() as session:
        results, total = storage.candidates_page(
            session, None, None, None, None, "recent", limit=10, offset=0, work_visa_statuses=["h1b"]
        )
        assert total == 1
        assert results[0].legal_first_name == "Alan"


def test_experience_range_filter(storage):
    _seed(storage)
    with storage.session() as session:
        results, total = storage.candidates_page(
            session, None, None, None, None, "recent", limit=10, offset=0,
            experience_min=5.0, experience_max=10.0,
        )
        assert total == 1
        assert results[0].legal_first_name == "Grace"


def test_filters_combine_as_and(storage):
    _seed(storage)
    with storage.session() as session:
        results, total = storage.candidates_page(
            session, None, None, None, None, "recent", limit=10, offset=0,
            skills=["python"], employment_statuses=["employed"],
        )
        assert total == 1
        assert results[0].legal_first_name == "Grace"


def test_candidate_facets_returns_distinct_skills_and_max_experience(storage):
    _seed(storage)
    with storage.session() as session:
        skills, max_experience = storage.candidate_facets(session)
        assert set(skills) == {"python", "fastapi", "sql", "rust", "cryptography"}
        assert max_experience == 12.0


def test_batch_email_links_picks_most_recent_per_candidate(storage):
    with storage.session() as session:
        candidate, _ = _make_candidate("Ada", "Lovelace", "ada@example.com", ["python"], days_ago=0, origin="email")
        session.add(candidate)
        # Two email sources for the same candidate — older then newer — plus
        # a folder source with no link, which should be ignored entirely.
        session.add(ResumeSource(
            id=str(uuid.uuid4()), candidate_id=candidate.id, origin="email", source_ref="ref:old",
            content_hash="h1", file_path="/tmp/old", date_submitted=datetime.utcnow() - timedelta(days=5),
            email_link="https://mail.google.com/mail/u/0/#all/old-msg",
        ))
        session.add(ResumeSource(
            id=str(uuid.uuid4()), candidate_id=candidate.id, origin="email", source_ref="ref:new",
            content_hash="h2", file_path="/tmp/new", date_submitted=datetime.utcnow() - timedelta(days=1),
            email_link="https://mail.google.com/mail/u/0/#all/new-msg",
        ))
        session.add(ResumeSource(
            id=str(uuid.uuid4()), candidate_id=candidate.id, origin="folder", source_ref="/resumes/ada.pdf",
            content_hash="h3", file_path="/tmp/folder", date_submitted=datetime.utcnow(),
        ))
        session.commit()

        links = _batch_email_links(session, [candidate.id])
        assert links[candidate.id] == "https://mail.google.com/mail/u/0/#all/new-msg"


def test_batch_email_links_omits_candidates_with_no_email_source(storage):
    _seed(storage)  # every seeded candidate is folder/email origin with no email_link set
    with storage.session() as session:
        candidate_ids = [c.id for c in session.execute(select(Candidate)).scalars()]
        links = _batch_email_links(session, candidate_ids)
        assert links == {}
