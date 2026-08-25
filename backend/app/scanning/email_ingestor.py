"""
EmailIngestor — Gmail API / Microsoft Graph, read-only mail scope, resume
attachments only. Same IngestedResume output shape as FolderIngestor so the
rest of the pipeline (parse -> identity resolution -> mirror -> match) never
branches on source.

Real OAuth wiring lives in app/email_auth/ (token acquisition + OS-keychain
storage). This module only needs a valid access token per account, handed to
it by the /scan/email-accounts route via get_email_token().

MockEmailIngestor below is what USE_MOCK=true runs against — a fixture inbox
so the full email path is exercisable and testable with no live account.
"""

from collections.abc import Iterator
from datetime import datetime

import httpx

from app.models.enums import ResumeOrigin
from app.models.schemas import IngestedResume
from app.scanning.folder_ingestor import SUPPORTED_EXTENSIONS
from app.scanning.ingestor_base import ResumeIngestor

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0/me"


class GmailIngestor(ResumeIngestor):
    """Read-only Gmail scan for messages with resume-like attachments."""

    def __init__(self, access_token: str, account_email: str):
        self.access_token = access_token
        self.account_email = account_email
        self._client = httpx.Client(
            base_url=GMAIL_API_BASE,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )

    def scan(
        self,
        date_start: datetime | None = None,
        date_end: datetime | None = None,
    ) -> Iterator[IngestedResume]:
        query_parts = ["has:attachment"]
        if date_start:
            query_parts.append(f"after:{int(date_start.timestamp())}")
        if date_end:
            query_parts.append(f"before:{int(date_end.timestamp())}")
        query = " ".join(query_parts)

        page_token = None
        while True:
            params = {"q": query, "maxResults": 100}
            if page_token:
                params["pageToken"] = page_token
            resp = self._client.get("/messages", params=params)
            resp.raise_for_status()
            data = resp.json()
            for msg_ref in data.get("messages", []):
                yield from self._extract_attachments(msg_ref["id"])
            page_token = data.get("nextPageToken")
            if not page_token:
                break

    def _extract_attachments(self, message_id: str) -> Iterator[IngestedResume]:
        resp = self._client.get(f"/messages/{message_id}", params={"format": "full"})
        resp.raise_for_status()
        msg = resp.json()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        date_submitted = _parse_email_date(headers.get("Date"))
        sender = headers.get("From", "")

        for part in _walk_parts(msg.get("payload", {})):
            filename = part.get("filename", "")
            if not filename or _ext(filename) not in SUPPORTED_EXTENSIONS:
                continue
            attachment_id = part.get("body", {}).get("attachmentId")
            if not attachment_id:
                continue
            att_resp = self._client.get(f"/messages/{message_id}/attachments/{attachment_id}")
            att_resp.raise_for_status()
            import base64

            file_bytes = base64.urlsafe_b64decode(att_resp.json()["data"])
            yield IngestedResume(
                origin=ResumeOrigin.EMAIL,
                source_ref=f"{self.account_email}:{message_id}",
                file_bytes=file_bytes,
                filename=filename,
                date_submitted=date_submitted,
                sender_email=_extract_email(sender),
                sender_name=_extract_name(sender),
            )


class OutlookIngestor(ResumeIngestor):
    """Read-only Microsoft Graph scan for messages with resume-like attachments."""

    def __init__(self, access_token: str, account_email: str):
        self.access_token = access_token
        self.account_email = account_email
        self._client = httpx.Client(
            base_url=GRAPH_API_BASE,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )

    def scan(
        self,
        date_start: datetime | None = None,
        date_end: datetime | None = None,
    ) -> Iterator[IngestedResume]:
        filters = ["hasAttachments eq true"]
        if date_start:
            filters.append(f"receivedDateTime ge {date_start.isoformat()}Z")
        if date_end:
            filters.append(f"receivedDateTime le {date_end.isoformat()}Z")
        params = {"$filter": " and ".join(filters), "$top": 50}

        url = "/messages"
        while url:
            resp = self._client.get(url, params=params if url == "/messages" else None)
            resp.raise_for_status()
            data = resp.json()
            for msg in data.get("value", []):
                yield from self._extract_attachments(msg)
            url = data.get("@odata.nextLink")
            if url:
                url = url.replace(GRAPH_API_BASE, "")

    def _extract_attachments(self, msg: dict) -> Iterator[IngestedResume]:
        message_id = msg["id"]
        date_submitted = datetime.fromisoformat(msg["receivedDateTime"].replace("Z", "+00:00"))
        sender = msg.get("from", {}).get("emailAddress", {})

        att_resp = self._client.get(f"/messages/{message_id}/attachments")
        att_resp.raise_for_status()
        for att in att_resp.json().get("value", []):
            filename = att.get("name", "")
            if _ext(filename) not in SUPPORTED_EXTENSIONS:
                continue
            import base64

            file_bytes = base64.b64decode(att.get("contentBytes", ""))
            yield IngestedResume(
                origin=ResumeOrigin.EMAIL,
                source_ref=f"{self.account_email}:{message_id}",
                file_bytes=file_bytes,
                filename=filename,
                date_submitted=date_submitted,
                sender_email=sender.get("address", ""),
                sender_name=sender.get("name", ""),
            )


class MockEmailIngestor(ResumeIngestor):
    """Fixture inbox for USE_MOCK=true / offline dev / golden tests."""

    def __init__(self, fixtures: list[IngestedResume] | None = None):
        self.fixtures = fixtures or []

    def scan(
        self,
        date_start: datetime | None = None,
        date_end: datetime | None = None,
    ) -> Iterator[IngestedResume]:
        for r in self.fixtures:
            if date_start and r.date_submitted < date_start:
                continue
            if date_end and r.date_submitted > date_end:
                continue
            yield r


def load_fixtures_from_manifest(manifest_path: str) -> list[IngestedResume]:
    """Loads a MockEmailIngestor fixture set from the JSON manifest produced by
    scripts/generate_sample_data.py — lets the Scan Sources / Email Access
    tabs work against a large synthetic dataset with USE_MOCK=true and no
    OAuth setup. Returns [] if the manifest doesn't exist (not an error —
    mock email scanning just yields nothing until a dataset is generated)."""
    import json
    from pathlib import Path

    manifest_file = Path(manifest_path)
    if not manifest_file.exists():
        return []

    manifest = json.loads(manifest_file.read_text())
    attachments_dir = manifest_file.parent / manifest.get("attachments_dir", "attachments")

    fixtures = []
    for entry in manifest.get("emails", []):
        attachment_path = attachments_dir / entry["attachment_file"]
        if not attachment_path.exists():
            continue
        fixtures.append(
            IngestedResume(
                origin=ResumeOrigin.EMAIL,
                source_ref=f"mock-demo-mailbox:{entry['id']}",
                file_bytes=attachment_path.read_bytes(),
                filename=attachment_path.name,
                date_submitted=datetime.fromisoformat(entry["date"]),
                sender_email=entry.get("from_email", ""),
                sender_name=entry.get("from_name", ""),
            )
        )
    return fixtures


def _walk_parts(payload: dict) -> Iterator[dict]:
    if "parts" in payload:
        for p in payload["parts"]:
            yield from _walk_parts(p)
    else:
        yield payload


def _ext(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _parse_email_date(raw: str | None) -> datetime:
    if not raw:
        return datetime.utcnow()
    try:
        from email.utils import parsedate_to_datetime

        return parsedate_to_datetime(raw)
    except Exception:
        return datetime.utcnow()


def _extract_email(from_header: str) -> str:
    if "<" in from_header and ">" in from_header:
        return from_header.split("<")[1].split(">")[0].strip()
    return from_header.strip()


def _extract_name(from_header: str) -> str:
    if "<" in from_header:
        return from_header.split("<")[0].strip().strip('"')
    return ""
