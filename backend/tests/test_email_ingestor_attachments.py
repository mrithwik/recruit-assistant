"""Confirms a message with multiple qualifying attachments (resume + cover
letter, say) collapses into one IngestedResume with the rest recorded as
metadata, instead of each attachment being ingested as its own equally-
weighted "resume" (the previous behavior — see project-log). Also pins the
existing/common single-attachment case as a regression check."""

import base64
from unittest.mock import MagicMock

from app.scanning.email_ingestor import GmailIngestor, OutlookIngestor


def _fake_response(json_data):
    resp = MagicMock()
    resp.raise_for_status = lambda: None
    resp.json = lambda: json_data
    return resp


def test_gmail_multiple_attachments_picks_first_as_primary(monkeypatch):
    ingestor = GmailIngestor(access_token="token", account_email="me@example.com")

    message_detail = {
        "payload": {
            "headers": [{"name": "Date", "value": "Mon, 1 Jan 2024 00:00:00 +0000"}, {"name": "From", "value": "Jane <jane@example.com>"}],
            "parts": [
                {"filename": "resume.pdf", "body": {"attachmentId": "att-1"}},
                {"filename": "cover_letter.pdf", "body": {"attachmentId": "att-2"}},
            ],
        }
    }
    attachment_payload = base64.urlsafe_b64encode(b"pdf bytes").decode()

    def fake_get(url, params=None):
        if url == "/messages/msg-1":
            return _fake_response(message_detail)
        if url == "/messages/msg-1/attachments/att-1":
            return _fake_response({"data": attachment_payload})
        raise AssertionError(f"unexpected call: {url}")

    monkeypatch.setattr(ingestor._client, "get", fake_get)

    results = list(ingestor._extract_attachments("msg-1"))

    assert len(results) == 1
    assert results[0].filename == "resume.pdf"
    assert results[0].additional_attachments == ["cover_letter.pdf"]


def test_gmail_single_attachment_has_no_additional_attachments(monkeypatch):
    ingestor = GmailIngestor(access_token="token", account_email="me@example.com")

    message_detail = {
        "payload": {
            "headers": [{"name": "Date", "value": "Mon, 1 Jan 2024 00:00:00 +0000"}, {"name": "From", "value": "Jane <jane@example.com>"}],
            "parts": [{"filename": "resume.pdf", "body": {"attachmentId": "att-1"}}],
        }
    }
    attachment_payload = base64.urlsafe_b64encode(b"pdf bytes").decode()

    def fake_get(url, params=None):
        if url == "/messages/msg-1":
            return _fake_response(message_detail)
        if url == "/messages/msg-1/attachments/att-1":
            return _fake_response({"data": attachment_payload})
        raise AssertionError(f"unexpected call: {url}")

    monkeypatch.setattr(ingestor._client, "get", fake_get)

    results = list(ingestor._extract_attachments("msg-1"))

    assert len(results) == 1
    assert results[0].filename == "resume.pdf"
    assert results[0].additional_attachments == []


def test_outlook_multiple_attachments_picks_first_as_primary(monkeypatch):
    ingestor = OutlookIngestor(access_token="token", account_email="me@example.com")

    msg = {
        "id": "msg-1",
        "receivedDateTime": "2024-01-01T00:00:00Z",
        "from": {"emailAddress": {"address": "jane@example.com", "name": "Jane"}},
    }
    attachments_payload = {
        "value": [
            {"name": "resume.docx", "contentBytes": base64.b64encode(b"docx bytes").decode()},
            {"name": "portfolio.pdf", "contentBytes": base64.b64encode(b"pdf bytes").decode()},
        ]
    }

    def fake_get(url, params=None):
        assert url == "/messages/msg-1/attachments"
        return _fake_response(attachments_payload)

    monkeypatch.setattr(ingestor._client, "get", fake_get)

    results = list(ingestor._extract_attachments(msg))

    assert len(results) == 1
    assert results[0].filename == "resume.docx"
    assert results[0].additional_attachments == ["portfolio.pdf"]
