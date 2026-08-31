"""Confirms a message with multiple qualifying attachments (resume + cover
letter, say) collapses into one IngestedResume with the rest recorded as
metadata, instead of each attachment being ingested as its own equally-
weighted "resume" (the previous behavior — see project-log). Also pins the
existing/common single-attachment case as a regression check.

_extract_one takes an httpx.AsyncClient — these tests fake just the .get
method (async) rather than spinning up a real client, mirroring the
MagicMock-response pattern the sync version used."""

import base64
from unittest.mock import MagicMock

from app.scanning.email_ingestor import GmailIngestor, OutlookIngestor


def _fake_response(json_data):
    resp = MagicMock()
    resp.raise_for_status = lambda: None
    resp.json = lambda: json_data
    resp.status_code = 200
    return resp


class _FakeAsyncClient:
    def __init__(self, responses: dict):
        self.responses = responses

    async def get(self, url, params=None):
        if url not in self.responses:
            raise AssertionError(f"unexpected call: {url}")
        return self.responses[url]


async def test_gmail_multiple_attachments_picks_first_as_primary():
    ingestor = GmailIngestor(access_token="token", account_email="me@example.com")

    message_detail = {
        "threadId": "thread-1",
        "payload": {
            "headers": [{"name": "Date", "value": "Mon, 1 Jan 2024 00:00:00 +0000"}, {"name": "From", "value": "Jane <jane@example.com>"}],
            "parts": [
                {"filename": "resume.pdf", "body": {"attachmentId": "att-1"}},
                {"filename": "cover_letter.pdf", "body": {"attachmentId": "att-2"}},
            ],
        }
    }
    attachment_payload = base64.urlsafe_b64encode(b"pdf bytes").decode()
    client = _FakeAsyncClient(
        {
            "/messages/msg-1": _fake_response(message_detail),
            "/messages/msg-1/attachments/att-1": _fake_response({"data": attachment_payload}),
        }
    )

    result = await ingestor._extract_one(client, "msg-1")

    assert result is not None
    assert result.filename == "resume.pdf"
    assert result.additional_attachments == ["cover_letter.pdf"]
    # Deliberately the thread id (thread-1), not the message id (msg-1) —
    # see email_ingestor.py's comment on why the message id alone doesn't
    # reliably open the actual conversation in Gmail's web UI.
    assert result.email_link == "https://mail.google.com/mail/u/0/#all/thread-1"


async def test_gmail_email_link_falls_back_to_message_id_if_thread_id_missing():
    # Defensive case only — Gmail always returns threadId in practice, but
    # if it were ever absent, still produce a working link rather than a
    # blank one.
    ingestor = GmailIngestor(access_token="token", account_email="me@example.com")

    message_detail = {
        "payload": {
            "headers": [{"name": "Date", "value": "Mon, 1 Jan 2024 00:00:00 +0000"}, {"name": "From", "value": "Jane <jane@example.com>"}],
            "parts": [{"filename": "resume.pdf", "body": {"attachmentId": "att-1"}}],
        }
    }
    attachment_payload = base64.urlsafe_b64encode(b"pdf bytes").decode()
    client = _FakeAsyncClient(
        {
            "/messages/msg-1": _fake_response(message_detail),
            "/messages/msg-1/attachments/att-1": _fake_response({"data": attachment_payload}),
        }
    )

    result = await ingestor._extract_one(client, "msg-1")

    assert result is not None
    assert result.email_link == "https://mail.google.com/mail/u/0/#all/msg-1"


async def test_gmail_single_attachment_has_no_additional_attachments():
    ingestor = GmailIngestor(access_token="token", account_email="me@example.com")

    message_detail = {
        "payload": {
            "headers": [{"name": "Date", "value": "Mon, 1 Jan 2024 00:00:00 +0000"}, {"name": "From", "value": "Jane <jane@example.com>"}],
            "parts": [{"filename": "resume.pdf", "body": {"attachmentId": "att-1"}}],
        }
    }
    attachment_payload = base64.urlsafe_b64encode(b"pdf bytes").decode()
    client = _FakeAsyncClient(
        {
            "/messages/msg-1": _fake_response(message_detail),
            "/messages/msg-1/attachments/att-1": _fake_response({"data": attachment_payload}),
        }
    )

    result = await ingestor._extract_one(client, "msg-1")

    assert result is not None
    assert result.filename == "resume.pdf"
    assert result.additional_attachments == []


async def test_outlook_multiple_attachments_picks_first_as_primary():
    ingestor = OutlookIngestor(access_token="token", account_email="me@example.com")

    msg = {
        "id": "msg-1",
        "receivedDateTime": "2024-01-01T00:00:00Z",
        "from": {"emailAddress": {"address": "jane@example.com", "name": "Jane"}},
        "webLink": "https://outlook.office.com/mail/msg-1",
    }
    attachments_payload = {
        "value": [
            {"name": "resume.docx", "contentBytes": base64.b64encode(b"docx bytes").decode()},
            {"name": "portfolio.pdf", "contentBytes": base64.b64encode(b"pdf bytes").decode()},
        ]
    }
    client = _FakeAsyncClient({"/messages/msg-1/attachments": _fake_response(attachments_payload)})

    result = await ingestor._extract_one(client, msg)

    assert result is not None
    assert result.filename == "resume.docx"
    assert result.additional_attachments == ["portfolio.pdf"]
    assert result.email_link == "https://outlook.office.com/mail/msg-1"
