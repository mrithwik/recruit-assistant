"""Delivers synthetic mail two ways: a small batch via real SMTP (single
initial-application message per persona — proves the true end-to-end
OAuth+scan path), and the bulk remainder as full multi-event journeys via
the Gmail API's messages.insert (follow-ups, resume updates, casual
check-ins, back-and-forth threads — see journeys.py). Insert is used for
journeys because it can set arbitrary historical Date headers and thread
messages together via a shared threadId, neither of which real SMTP send
allows for anything but "right now, from the authenticated sender."

Every message carries SYNTHETIC_TAG in its subject line (and a custom
header) so the cleanup script can find every synthetic candidate later even
though nothing is deleted automatically after this run.
"""

from __future__ import annotations

import asyncio
import base64
import json
import smtplib
import time
from dataclasses import asdict
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from pathlib import Path

import httpx

from app.matching.concurrency import bounded_gather

from .documents import (
    render_cover_letter_pdf,
    render_passport_pdf,
    render_photo_id_pdf,
    render_resume_pdf,
    render_resume_pdf_image_only,
    render_work_auth_pdf,
)
from .journeys import EmailEvent
from .personas import Persona

SYNTHETIC_TAG = "[SYNTH-DEMO-2026-08-26]"
GMAIL_INSERT_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"


def build_single_application_message(p: Persona, work_dir: Path, sender_email: str) -> EmailMessage:
    """Used only for the small real-SMTP proof batch: one plain initial
    application, no threading, no journey — keeps the real-send path simple
    and easy to reason about."""
    work_dir.mkdir(parents=True, exist_ok=True)
    slug = f"{p.idx:06d}_{p.first_name}_{p.last_name}".lower()

    resume_path = work_dir / f"{slug}_resume.pdf"
    if p.ocr_image_resume:
        render_resume_pdf_image_only(p, resume_path)
    else:
        render_resume_pdf(p, resume_path)

    attachments = [resume_path]
    if p.include_cover_letter:
        cl_path = work_dir / f"{slug}_cover_letter.pdf"
        render_cover_letter_pdf(p, cl_path)
        attachments.append(cl_path)
    if p.include_work_auth:
        wa_path = work_dir / f"{slug}_work_authorization.pdf"
        render_work_auth_pdf(p, wa_path)
        attachments.append(wa_path)
    if p.include_photo_id:
        id_path = work_dir / f"{slug}_photo_id.pdf"
        render_photo_id_pdf(p, id_path)
        attachments.append(id_path)
    if p.include_passport:
        pp_path = work_dir / f"{slug}_passport.pdf"
        render_passport_pdf(p, pp_path)
        attachments.append(pp_path)

    msg = EmailMessage()
    msg["From"] = f"{p.first_name} {p.last_name} <{sender_email}>"
    msg["Subject"] = f"{SYNTHETIC_TAG} Application for {p.title} — {p.first_name} {p.last_name}"
    msg["Reply-To"] = p.email
    msg["X-Recruit-Assistant-Synthetic"] = SYNTHETIC_TAG
    body = (
        f"Hi,\n\nPlease find my resume attached for the {p.title} position.\n\n"
        f"Best,\n{p.first_name} {p.last_name}\n{p.phone}"
    )
    msg.set_content(body)
    for path in attachments:
        msg.add_attachment(path.read_bytes(), maintype="application", subtype="pdf", filename=path.name)
    return msg


def send_batch_via_smtp(messages: list[EmailMessage], sender_email: str, app_password: str, recipient: str) -> list[str]:
    """Sends via real Gmail SMTP. Returns the list of successfully-sent
    subjects (Gmail doesn't hand back a message id at send time — the
    cleanup script identifies these later purely by SYNTHETIC_TAG, same as
    the API-inserted ones)."""
    sent_subjects = []
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender_email, app_password)
        for msg in messages:
            msg["To"] = recipient
            smtp.send_message(msg)
            sent_subjects.append(msg["Subject"])
            time.sleep(0.5)  # stay well under Gmail's per-second send burst limits
    return sent_subjects


def _build_event_mime(event: EmailEvent, p: Persona, recipient: str, message_id: str, in_reply_to: str | None, references: list[str]) -> EmailMessage:
    msg = EmailMessage()
    if event.direction == "candidate_to_recruiter":
        msg["From"] = f"{p.first_name} {p.last_name} <{p.email}>"
        msg["To"] = recipient
    else:
        msg["From"] = recipient
        msg["To"] = p.email
    msg["Subject"] = f"{SYNTHETIC_TAG} {event.subject}"
    msg["Message-ID"] = message_id
    msg["Date"] = format_datetime(event.timestamp)
    msg["X-Recruit-Assistant-Synthetic"] = SYNTHETIC_TAG
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = " ".join(references)
    msg.set_content(event.body)
    for path in event.attachments:
        msg.add_attachment(path.read_bytes(), maintype="application", subtype="pdf", filename=path.name)
    return msg


async def _insert_one_journey(
    events: list[EmailEvent], personas_by_idx: dict[int, Persona], recipient: str, client: httpx.AsyncClient, get_token
) -> list[dict]:
    """Inserts one persona's full journey in timestamp order, chaining
    In-Reply-To/References and reusing the Gmail-assigned threadId from the
    journey's first message so the whole conversation groups into one
    thread — same as a real back-and-forth would. Within a journey this
    must stay sequential (each insert needs the previous message's id/
    threadId); different personas' journeys are independent and run
    concurrently via bounded_gather. internalDateSource=dateHeader is
    essential: without it Gmail stamps every message with "now" regardless
    of our synthetic Date header, collapsing the 10-year timeline onto
    today."""
    p = personas_by_idx[events[0].persona_idx]
    references: list[str] = []
    thread_id: str | None = None
    results = []
    for event in events:
        message_id = make_msgid(domain="synthetic.recruit-assistant.local")
        in_reply_to = references[-1] if references else None
        msg = _build_event_mime(event, p, recipient, message_id, in_reply_to, references)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        label = "SENT" if event.direction == "recruiter_to_candidate" else "INBOX"
        body: dict = {"raw": raw, "labelIds": [label] if label == "SENT" else [label, "UNREAD"]}
        if thread_id:
            body["threadId"] = thread_id

        data = None
        backoff = 1.0
        resp = None
        try:
            for _attempt in range(8):
                # Fetched fresh (not once at process start) — a 10,000-persona
                # run can take well over an hour, longer than a Google access
                # token's ~1-hour lifetime. get_valid_access_token() refreshes
                # under the hood when the cached token has expired.
                token = await asyncio.to_thread(get_token)
                resp = await client.post(
                    GMAIL_INSERT_URL,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    params={"internalDateSource": "dateHeader"},
                    json=body,
                )
                if resp.status_code == 401 or resp.status_code == 429 or resp.status_code >= 500:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30)
                    continue
                if resp.status_code >= 400:
                    raise RuntimeError(f"Gmail insert failed ({resp.status_code}): {resp.text[:500]}")
                data = resp.json()
                break
            if data is None:
                raise RuntimeError(f"Gmail insert failed after retries (last: {resp.status_code if resp else '?'})")
        except Exception as exc:  # noqa: BLE001 - a single journey's failure must not sink the whole batch
            results.append({"error": str(exc), "persona_idx": p.idx, "kind": event.kind, "subject": msg["Subject"]})
            break
        thread_id = thread_id or data["threadId"]
        references.append(message_id)
        results.append(
            {
                "gmail_message_id": data["id"],
                "thread_id": data["threadId"],
                "persona_idx": p.idx,
                "kind": event.kind,
                "subject": msg["Subject"],
            }
        )
    return results


async def insert_journeys_via_gmail_api_async(
    journeys: list[list[EmailEvent]],
    personas_by_idx: dict[int, Persona],
    get_token,
    recipient: str,
    max_concurrent: int = 8,
) -> list[dict]:
    """get_token is a zero-arg callable (e.g. functools.partial(get_valid_access_token,
    account_id, "gmail")) invoked fresh before every single insert, not once at the
    start — required for a run long enough to outlast a Google access token's ~1hr
    lifetime (see the 401-cascade this fixed after the first full-scale run)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        per_journey_results = await bounded_gather(
            journeys,
            lambda events: _insert_one_journey(events, personas_by_idx, recipient, client, get_token),
            max_concurrent,
        )
    return [item for sublist in per_journey_results for item in sublist]


def write_manifest(
    path: Path, personas: list[Persona], smtp_subjects: list[str], api_inserted: list[dict], journey_event_counts: dict[int, int]
) -> None:
    manifest = {
        "tag": SYNTHETIC_TAG,
        "persona_count": len(personas),
        "smtp_sent_subjects": smtp_subjects,
        "api_inserted_count": len(api_inserted),
        "api_inserted": api_inserted,
        "journey_event_counts": journey_event_counts,
        "personas": [
            {**asdict(p), "submitted_at": p.submitted_at.isoformat()} for p in personas
        ],
    }
    path.write_text(json.dumps(manifest, indent=2))
