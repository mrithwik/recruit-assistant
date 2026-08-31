"""backfill_email_links — the one-off repair for ResumeSource rows created
before email_link existed (a plain rescan does NOT fix these, see the
module's docstring: dedup skips already-seen sources entirely)."""

import uuid
from datetime import datetime

import pytest

from app.config import Settings
from app.maintenance import email_link_backfill as backfill_module
from app.maintenance.email_link_backfill import backfill_email_links
from app.models.db import Candidate, EmailAccount, ResumeSource


@pytest.fixture
def settings():
    return Settings(secret_key="test-secret")


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json


class _FakeAsyncClient:
    def __init__(self, responses: dict):
        self.responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        return self.responses[url]


def _seed_candidate_and_source(session, account_email: str, message_id: str) -> ResumeSource:
    candidate = Candidate(
        id=str(uuid.uuid4()),
        identity_fingerprint=f"email:{message_id}@example.com",
        legal_first_name="Test",
        legal_last_name="Candidate",
        email=f"{message_id}@example.com",
        date_submitted=datetime.utcnow(),
    )
    session.add(candidate)
    source = ResumeSource(
        id=str(uuid.uuid4()),
        candidate_id=candidate.id,
        origin="email",
        source_ref=f"{account_email}:{message_id}",
        content_hash=f"hash-{message_id}",
        file_path=f"/tmp/{message_id}",
        date_submitted=datetime.utcnow(),
        email_link="",
    )
    session.add(source)
    return source


@pytest.mark.asyncio
async def test_backfill_fills_gmail_thread_links(monkeypatch, storage, settings):
    with storage.session() as session:
        account = EmailAccount(
            id=str(uuid.uuid4()), provider="gmail", email_address="me@example.com", keychain_ref="k1"
        )
        session.add(account)
        source = _seed_candidate_and_source(session, "me@example.com", "msg-1")
        session.commit()
        source_id = source.id

    monkeypatch.setattr(backfill_module, "get_valid_access_token", lambda *a, **k: "fake-token")
    fake_client = _FakeAsyncClient({"/messages/msg-1": _FakeResponse({"threadId": "thread-1"})})
    monkeypatch.setattr(backfill_module.httpx, "AsyncClient", lambda **kwargs: fake_client)

    with storage.session() as session:
        result = await backfill_email_links(session, settings)
        session.commit()

    assert result.resumes_found == 1
    assert result.candidates_created == 1  # links filled
    assert result.errors == []

    with storage.session() as session:
        refreshed = session.get(ResumeSource, source_id)
        assert refreshed.email_link == "https://mail.google.com/mail/u/0/#all/thread-1"


@pytest.mark.asyncio
async def test_backfill_fills_outlook_weblinks(monkeypatch, storage, settings):
    with storage.session() as session:
        account = EmailAccount(
            id=str(uuid.uuid4()), provider="outlook", email_address="me@outlook.com", keychain_ref="k2"
        )
        session.add(account)
        source = _seed_candidate_and_source(session, "me@outlook.com", "msg-2")
        session.commit()
        source_id = source.id

    monkeypatch.setattr(backfill_module, "get_valid_access_token", lambda *a, **k: "fake-token")
    fake_client = _FakeAsyncClient(
        {"/messages/msg-2": _FakeResponse({"webLink": "https://outlook.office.com/mail/msg-2"})}
    )
    monkeypatch.setattr(backfill_module.httpx, "AsyncClient", lambda **kwargs: fake_client)

    with storage.session() as session:
        result = await backfill_email_links(session, settings)
        session.commit()

    assert result.candidates_created == 1
    with storage.session() as session:
        refreshed = session.get(ResumeSource, source_id)
        assert refreshed.email_link == "https://outlook.office.com/mail/msg-2"


@pytest.mark.asyncio
async def test_backfill_skips_sources_with_no_matching_connected_account(storage, settings):
    with storage.session() as session:
        # No EmailAccount row for this address at all — e.g. a mock fixture
        # source, or an account that's since been disconnected.
        _seed_candidate_and_source(session, "mock-demo-mailbox", "msg-3")
        session.commit()

    with storage.session() as session:
        result = await backfill_email_links(session, settings)

    assert result.resumes_found == 1
    assert result.candidates_created == 0
    assert result.duplicates_skipped == 1  # skipped_no_account


@pytest.mark.asyncio
async def test_backfill_ignores_sources_that_already_have_a_link(storage, settings):
    with storage.session() as session:
        account = EmailAccount(
            id=str(uuid.uuid4()), provider="gmail", email_address="me@example.com", keychain_ref="k3"
        )
        session.add(account)
        source = _seed_candidate_and_source(session, "me@example.com", "msg-4")
        source.email_link = "https://mail.google.com/mail/u/0/#all/already-set"
        session.commit()

    with storage.session() as session:
        result = await backfill_email_links(session, settings)

    assert result.resumes_found == 0  # already-linked rows are excluded from the query entirely
