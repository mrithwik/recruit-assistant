"""Confirms GmailIngestor.scan() actually fetches messages concurrently
(not the old one-message-at-a-time sequential blocking loop) while still
respecting the max_concurrent cap — see project-log for the real-mailbox
scan that surfaced the sequential version as an hours-long, event-loop-
freezing bottleneck."""

import asyncio
import base64

import pytest

from app.scanning import email_ingestor as email_ingestor_module
from app.scanning.email_ingestor import GmailIngestor

MESSAGE_COUNT = 20


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")

    def json(self):
        return self._json


class _ConcurrencyTrackingFakeClient:
    """Simulates Gmail's API: one /messages list call, then a full-message
    fetch + an attachment fetch per message id. Tracks how many of those
    per-message fetches were in flight simultaneously."""

    def __init__(self):
        self.in_flight = 0
        self.max_in_flight = 0
        self.lock = asyncio.Lock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        if url == "/messages":
            return _FakeResponse({"messages": [{"id": f"m{i}"} for i in range(MESSAGE_COUNT)]})

        async with self.lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0.02)
        async with self.lock:
            self.in_flight -= 1

        if url.startswith("/messages/") and "/attachments/" in url:
            return _FakeResponse({"data": base64.urlsafe_b64encode(b"pdf bytes").decode()})

        # message detail fetch
        message_id = url.rsplit("/", 1)[-1]
        return _FakeResponse(
            {
                "payload": {
                    "headers": [{"name": "Date", "value": "Mon, 1 Jan 2024 00:00:00 +0000"}, {"name": "From", "value": "Jane <jane@example.com>"}],
                    "parts": [{"filename": "resume.pdf", "body": {"attachmentId": f"att-{message_id}"}}],
                }
            }
        )


@pytest.mark.asyncio
async def test_gmail_scan_fetches_messages_concurrently_within_cap(monkeypatch):
    fake_client = _ConcurrencyTrackingFakeClient()
    monkeypatch.setattr(email_ingestor_module.httpx, "AsyncClient", lambda **kwargs: fake_client)

    max_concurrent = 5
    ingestor = GmailIngestor(access_token="token", account_email="me@example.com", max_concurrent=max_concurrent)

    results = [r async for r in ingestor.scan()]

    assert len(results) == MESSAGE_COUNT
    assert fake_client.max_in_flight > 1, "expected message fetches to overlap, not run one at a time"
    assert fake_client.max_in_flight <= max_concurrent
