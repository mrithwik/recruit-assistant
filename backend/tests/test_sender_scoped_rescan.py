"""sender_email scoping on GmailIngestor/OutlookIngestor/MockEmailIngestor —
backs the per-candidate rescan (see routes/candidate_rescan.py), which needs
to search just one person's messages instead of the whole mailbox to stay
fast against a large inbox."""

from datetime import datetime

import pytest

from app.models.enums import ResumeOrigin
from app.models.schemas import IngestedResume
from app.scanning import email_ingestor as email_ingestor_module
from app.scanning.email_ingestor import GmailIngestor, MockEmailIngestor, OutlookIngestor


class _FakeResponse:
    def __init__(self, json_data):
        self._json = json_data

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


class _QueryCapturingClient:
    """Records the params of every /messages list call, returns zero
    messages — enough to confirm the sender filter reaches the request
    without needing to fake the full message-fetch chain too."""

    def __init__(self):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        self.calls.append((url, params))
        if url == "/messages":
            return _FakeResponse({"messages": []})
        return _FakeResponse({"value": []})


async def test_gmail_scan_adds_from_filter_when_sender_email_set(monkeypatch):
    fake_client = _QueryCapturingClient()
    monkeypatch.setattr(email_ingestor_module.httpx, "AsyncClient", lambda **kwargs: fake_client)

    ingestor = GmailIngestor(access_token="token", account_email="me@example.com", sender_email="candidate@example.com")
    _ = [r async for r in ingestor.scan()]

    list_call = next(c for c in fake_client.calls if c[0] == "/messages")
    assert "from:candidate@example.com" in list_call[1]["q"]


async def test_gmail_scan_omits_from_filter_when_no_sender_email(monkeypatch):
    fake_client = _QueryCapturingClient()
    monkeypatch.setattr(email_ingestor_module.httpx, "AsyncClient", lambda **kwargs: fake_client)

    ingestor = GmailIngestor(access_token="token", account_email="me@example.com")
    _ = [r async for r in ingestor.scan()]

    list_call = next(c for c in fake_client.calls if c[0] == "/messages")
    assert "from:" not in list_call[1]["q"]


async def test_outlook_scan_adds_from_filter_when_sender_email_set(monkeypatch):
    fake_client = _QueryCapturingClient()
    monkeypatch.setattr(email_ingestor_module.httpx, "AsyncClient", lambda **kwargs: fake_client)

    ingestor = OutlookIngestor(access_token="token", account_email="me@example.com", sender_email="candidate@example.com")
    _ = [r async for r in ingestor.scan()]

    list_call = next(c for c in fake_client.calls if c[0] == "/messages")
    assert "candidate@example.com" in list_call[1]["$filter"]


def _fixture(sender_email: str) -> IngestedResume:
    return IngestedResume(
        origin=ResumeOrigin.EMAIL,
        source_ref=f"mailbox:{sender_email}",
        file_bytes=b"resume bytes",
        filename="resume.pdf",
        date_submitted=datetime(2026, 1, 1),
        sender_email=sender_email,
    )


async def test_mock_ingestor_filters_fixtures_by_sender_email():
    fixtures = [_fixture("alice@example.com"), _fixture("bob@example.com")]
    ingestor = MockEmailIngestor(fixtures=fixtures, sender_email="alice@example.com")

    results = [r async for r in ingestor.scan()]

    assert len(results) == 1
    assert results[0].sender_email == "alice@example.com"


async def test_mock_ingestor_sender_filter_is_case_insensitive():
    fixtures = [_fixture("Alice@Example.com")]
    ingestor = MockEmailIngestor(fixtures=fixtures, sender_email="alice@example.com")

    results = [r async for r in ingestor.scan()]

    assert len(results) == 1


async def test_mock_ingestor_yields_everything_when_no_sender_filter():
    fixtures = [_fixture("alice@example.com"), _fixture("bob@example.com")]
    ingestor = MockEmailIngestor(fixtures=fixtures)

    results = [r async for r in ingestor.scan()]

    assert len(results) == 2
