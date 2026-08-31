"""
EmailIngestor — Gmail API / Microsoft Graph, read-only mail scope, resume
attachments only. Same IngestedResume output shape as FolderIngestor so the
rest of the pipeline (parse -> identity resolution -> mirror -> match) never
branches on source.

Real OAuth wiring lives in app/email_auth/ (token acquisition + OS-keychain
storage). This module only needs a valid access token per account, handed to
it by the /scan/email-accounts route via get_email_token().

MockEmailIngestor below is what USE_MOCK_EMAIL=true runs against — a fixture inbox
so the full email path is exercisable and testable with no live account.

Gmail/Outlook fetching is async + bounded-concurrent (one page of message
refs listed at a time, then all messages in that page fetched concurrently
via bounded_gather) rather than one-message-at-a-time sequential blocking
calls — a real mailbox scan surfaced this as the actual bottleneck (see
project-log): 2 sequential network round-trips per message with no
concurrency meant a ~11,000-message scan took over an hour and froze the
whole single-process backend for its entire duration, since the old sync
httpx.Client calls blocked the event loop directly with no threadpool
offload. Async httpx + bounded_gather fixes both: the event loop stays
responsive between awaits, and concurrent fetches cut wall-clock time
dramatically (validated: ~7-10 req/sec at concurrency 15-20 vs ~2-3 req/sec
sequential, with retry/backoff absorbing Gmail's occasional 429s).
"""

from collections.abc import AsyncIterator, Iterator
from datetime import datetime

import httpx

from app.matching.concurrency import bounded_gather
from app.models.enums import ResumeOrigin
from app.models.schemas import IngestedResume
from app.scanning.folder_ingestor import SUPPORTED_EXTENSIONS
from app.scanning.ingestor_base import ResumeIngestor

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0/me"

# Only request the payload fields _walk_parts/header-parsing actually use —
# format=full's default response also includes snippet/labelIds/sizeEstimate/
# historyId etc. we never read, so this trims real bytes off every single
# message fetch at zero behavior change. threadId is the one addition kept
# purely for the deep link below.
GMAIL_MESSAGE_FIELDS = "id,threadId,internalDate,payload/headers,payload/parts,payload/filename,payload/mimeType,payload/body"


class GmailIngestor(ResumeIngestor):
    """Read-only Gmail scan for messages with resume-like attachments."""

    def __init__(self, access_token: str, account_email: str, max_concurrent: int = 15, sender_email: str = ""):
        self.access_token = access_token
        self.account_email = account_email
        self.max_concurrent = max_concurrent
        # Set for a per-candidate "check for updates" rescan (see
        # routes/candidate_rescan.py) — narrows to just that person's
        # messages instead of the whole mailbox, so it's fast enough to run
        # on demand from the candidate detail page.
        self.sender_email = sender_email

    async def scan(
        self,
        date_start: datetime | None = None,
        date_end: datetime | None = None,
    ) -> AsyncIterator[IngestedResume]:
        query_parts = ["has:attachment"]
        if date_start:
            query_parts.append(f"after:{int(date_start.timestamp())}")
        if date_end:
            query_parts.append(f"before:{int(date_end.timestamp())}")
        if self.sender_email:
            query_parts.append(f"from:{self.sender_email}")
        query = " ".join(query_parts)

        async with httpx.AsyncClient(
            base_url=GMAIL_API_BASE, headers={"Authorization": f"Bearer {self.access_token}"}, timeout=30.0
        ) as client:
            page_token = None
            while True:
                params = {"q": query, "maxResults": 100}
                if page_token:
                    params["pageToken"] = page_token
                resp = await client.get("/messages", params=params)
                resp.raise_for_status()
                data = resp.json()

                message_ids = [m["id"] for m in data.get("messages", [])]
                if message_ids:
                    results = await bounded_gather(
                        message_ids,
                        lambda mid: self._extract_one(client, mid),
                        self.max_concurrent,
                    )
                    for r in results:
                        if r is not None:
                            yield r

                page_token = data.get("nextPageToken")
                if not page_token:
                    break

    async def _extract_one(self, client: httpx.AsyncClient, message_id: str) -> IngestedResume | None:
        resp = await get_with_retry(client, f"/messages/{message_id}", params={"format": "full", "fields": GMAIL_MESSAGE_FIELDS})
        msg = resp.json()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        date_submitted = _parse_email_date(headers.get("Date"))
        sender = headers.get("From", "")

        # A message can carry more than one qualifying attachment (resume +
        # cover letter, say). Only the first is ingested as the resume;
        # yielding every one as its own equally-weighted IngestedResume
        # previously ran full LLM extraction on a cover letter and could
        # overwrite better fields already parsed from the actual resume —
        # the rest are recorded as filenames on the primary one instead.
        qualifying_parts = [
            part
            for part in _walk_parts(msg.get("payload", {}))
            if part.get("filename") and _ext(part["filename"]) in SUPPORTED_EXTENSIONS and part.get("body", {}).get("attachmentId")
        ]
        if not qualifying_parts:
            return None

        primary, *rest = qualifying_parts
        import base64

        att_resp = await get_with_retry(client, f"/messages/{message_id}/attachments/{primary['body']['attachmentId']}")
        file_bytes = base64.urlsafe_b64decode(att_resp.json()["data"])
        return IngestedResume(
            origin=ResumeOrigin.EMAIL,
            source_ref=f"{self.account_email}:{message_id}",
            file_bytes=file_bytes,
            filename=primary["filename"],
            date_submitted=date_submitted,
            sender_email=_extract_email(sender),
            sender_name=_extract_name(sender),
            additional_attachments=[part["filename"] for part in rest],
            # Deliberately the *thread* id, not the message id: Gmail's web
            # UI renders this URL fragment as a conversation view keyed on
            # the thread, and a reply/forward's own message id either 404s
            # or opens the wrong item in that view — only the first message
            # in a single-message thread happens to share its thread's id,
            # which is why this looked like it worked in casual testing.
            email_link=f"https://mail.google.com/mail/u/0/#all/{msg.get('threadId', message_id)}",
        )


class OutlookIngestor(ResumeIngestor):
    """Read-only Microsoft Graph scan for messages with resume-like attachments."""

    def __init__(self, access_token: str, account_email: str, max_concurrent: int = 15, sender_email: str = ""):
        self.access_token = access_token
        self.account_email = account_email
        self.max_concurrent = max_concurrent
        self.sender_email = sender_email  # see GmailIngestor's sender_email

    async def scan(
        self,
        date_start: datetime | None = None,
        date_end: datetime | None = None,
    ) -> AsyncIterator[IngestedResume]:
        filters = ["hasAttachments eq true"]
        if date_start:
            filters.append(f"receivedDateTime ge {date_start.isoformat()}Z")
        if date_end:
            filters.append(f"receivedDateTime le {date_end.isoformat()}Z")
        if self.sender_email:
            filters.append(f"from/emailAddress/address eq '{self.sender_email}'")
        params = {"$filter": " and ".join(filters), "$top": 50}

        async with httpx.AsyncClient(
            base_url=GRAPH_API_BASE, headers={"Authorization": f"Bearer {self.access_token}"}, timeout=30.0
        ) as client:
            url = "/messages"
            while url:
                resp = await client.get(url, params=params if url == "/messages" else None)
                resp.raise_for_status()
                data = resp.json()

                messages = data.get("value", [])
                if messages:
                    results = await bounded_gather(
                        messages,
                        lambda msg: self._extract_one(client, msg),
                        self.max_concurrent,
                    )
                    for r in results:
                        if r is not None:
                            yield r

                url = data.get("@odata.nextLink")
                if url:
                    url = url.replace(GRAPH_API_BASE, "")

    async def _extract_one(self, client: httpx.AsyncClient, msg: dict) -> IngestedResume | None:
        message_id = msg["id"]
        date_submitted = datetime.fromisoformat(msg["receivedDateTime"].replace("Z", "+00:00"))
        sender = msg.get("from", {}).get("emailAddress", {})

        att_resp = await get_with_retry(client, f"/messages/{message_id}/attachments")
        # Same "only the first qualifying attachment is the resume" rule as
        # GmailIngestor — see its _extract_one for why.
        qualifying = [att for att in att_resp.json().get("value", []) if _ext(att.get("name", "")) in SUPPORTED_EXTENSIONS]
        if not qualifying:
            return None

        primary, *rest = qualifying
        import base64

        file_bytes = base64.b64decode(primary.get("contentBytes", ""))
        return IngestedResume(
            origin=ResumeOrigin.EMAIL,
            source_ref=f"{self.account_email}:{message_id}",
            file_bytes=file_bytes,
            filename=primary.get("name", ""),
            date_submitted=date_submitted,
            sender_email=sender.get("address", ""),
            sender_name=sender.get("name", ""),
            additional_attachments=[att.get("name", "") for att in rest],
            # Graph returns a ready-made Outlook Web Access link on every
            # message by default — no URL construction needed (unlike Gmail;
            # see GmailIngestor._extract_one).
            email_link=msg.get("webLink", ""),
        )


class MockEmailIngestor(ResumeIngestor):
    """Fixture inbox for USE_MOCK_EMAIL=true / offline dev / golden tests."""

    def __init__(self, fixtures: list[IngestedResume] | None = None, sender_email: str = ""):
        self.fixtures = fixtures or []
        self.sender_email = sender_email  # see GmailIngestor's sender_email

    async def scan(
        self,
        date_start: datetime | None = None,
        date_end: datetime | None = None,
    ) -> AsyncIterator[IngestedResume]:
        for r in self.fixtures:
            if date_start and r.date_submitted < date_start:
                continue
            if date_end and r.date_submitted > date_end:
                continue
            if self.sender_email and r.sender_email.lower() != self.sender_email.lower():
                continue
            yield r


async def get_with_retry(client: httpx.AsyncClient, url: str, params: dict | None = None, max_attempts: int = 6) -> httpx.Response:
    """429/5xx retry with exponential backoff — a scan at real-mailbox scale
    will hit occasional rate-limit responses even at a conservative
    concurrency cap; without this a single blip aborts the entire scan."""
    import asyncio

    backoff = 1.0
    for attempt in range(max_attempts):
        resp = await client.get(url, params=params)
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == max_attempts - 1:
                resp.raise_for_status()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
            continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()
    return resp


def load_fixtures_from_manifest(manifest_path: str) -> list[IngestedResume]:
    """Loads a MockEmailIngestor fixture set from the JSON manifest produced by
    scripts/generate_sample_data.py — lets the Scan Sources / Email Access
    tabs work against a large synthetic dataset with USE_MOCK_EMAIL=true and no
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
