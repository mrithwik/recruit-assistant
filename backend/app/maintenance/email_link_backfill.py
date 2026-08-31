"""Backfills ResumeSource.email_link for resumes ingested before that field
existed. A normal rescan does NOT do this — ingest_service.py's dedup keys
on (content_hash, source_ref), and an already-seen message hits that exact
match and gets silently skipped, so its ResumeSource row is never touched or
re-created (see project-log). This walks the existing rows directly and
looks up just enough info (Gmail: threadId, Outlook: webLink) to fill in the
link — no re-ingestion, no re-parsing, no LLM calls, just the one field.

Registered in app/maintenance/tasks.py as "email_link_backfill" — see that
module for why maintenance tasks exist as a pattern rather than one-off code
for just this feature."""

from collections.abc import Callable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.email_auth.oauth import get_valid_access_token
from app.matching.concurrency import bounded_gather
from app.models.db import EmailAccount, ResumeSource
from app.models.schemas import ScanResult
from app.scanning.email_ingestor import GMAIL_API_BASE, GRAPH_API_BASE, get_with_retry

MAX_CONCURRENT = 15
CHECKPOINT_EVERY = 200


async def _backfill_for_account(
    client: httpx.AsyncClient, account: EmailAccount, sources: list[ResumeSource]
) -> tuple[int, list[str]]:
    """Returns (links_filled, errors) for one account's sources."""
    errors: list[str] = []

    async def _fill_one(source: ResumeSource) -> bool:
        message_id = source.source_ref.split(":", 1)[1] if ":" in source.source_ref else ""
        if not message_id:
            return False
        try:
            if account.provider == "gmail":
                resp = await get_with_retry(client, f"/messages/{message_id}", params={"fields": "threadId"})
                thread_id = resp.json().get("threadId", message_id)
                source.email_link = f"https://mail.google.com/mail/u/0/#all/{thread_id}"
            else:
                resp = await get_with_retry(client, f"/messages/{message_id}", params={"$select": "webLink"})
                web_link = resp.json().get("webLink", "")
                if not web_link:
                    return False
                source.email_link = web_link
            return True
        except httpx.HTTPStatusError as exc:
            # A message deleted/moved since it was first scanned 404s here —
            # expected at some rate over a large backfill, not worth failing
            # the whole run over. Recorded, not raised.
            errors.append(f"{account.email_address}:{message_id}: {exc.response.status_code}")
            return False

    results = await bounded_gather(sources, _fill_one, MAX_CONCURRENT)
    return sum(1 for r in results if r), errors


async def backfill_email_links(
    session: Session,
    settings: Settings,
    on_progress: Callable[[ScanResult], None] | None = None,
    on_should_cancel: Callable[[], bool] | None = None,
) -> ScanResult:
    sources = list(
        session.execute(
            select(ResumeSource).where(ResumeSource.origin == "email", ResumeSource.email_link == "")
        ).scalars()
    )

    considered = 0
    filled = 0
    skipped_no_account = 0
    errors: list[str] = []

    # Group by the account_email prefix of source_ref so each account's
    # sources share one access token and one client instead of
    # re-authenticating per row.
    by_account_email: dict[str, list[ResumeSource]] = {}
    for source in sources:
        account_email = source.source_ref.split(":", 1)[0] if ":" in source.source_ref else ""
        by_account_email.setdefault(account_email, []).append(source)

    for account_email, account_sources in by_account_email.items():
        if on_should_cancel and on_should_cancel():
            break
        considered += len(account_sources)
        account = session.execute(
            select(EmailAccount).where(EmailAccount.email_address == account_email)
        ).scalar_one_or_none()
        if not account:
            # Mock fixtures ("mock-demo-mailbox:...") or an account that's
            # since been disconnected — nothing to look up against.
            skipped_no_account += len(account_sources)
            continue

        access_token = get_valid_access_token(
            account.id,
            account.provider,
            ms_client_id=settings.ms_oauth_client_id,
            ms_client_secret=settings.ms_oauth_client_secret,
            ms_tenant_id=settings.ms_oauth_tenant_id,
        )
        if not access_token:
            errors.append(f"{account_email}: no valid token, reconnect the account")
            continue

        base_url = GMAIL_API_BASE if account.provider == "gmail" else GRAPH_API_BASE
        async with httpx.AsyncClient(base_url=base_url, headers={"Authorization": f"Bearer {access_token}"}, timeout=30.0) as client:
            for i in range(0, len(account_sources), CHECKPOINT_EVERY):
                batch = account_sources[i : i + CHECKPOINT_EVERY]
                batch_filled, batch_errors = await _backfill_for_account(client, account, batch)
                filled += batch_filled
                errors.extend(batch_errors)
                session.commit()
                if on_progress:
                    on_progress(
                        ScanResult(
                            resumes_found=considered,
                            candidates_created=filled,
                            candidates_updated=0,
                            duplicates_skipped=skipped_no_account,
                            errors=errors,
                        )
                    )
                if on_should_cancel and on_should_cancel():
                    break

    return ScanResult(
        resumes_found=considered,
        candidates_created=filled,
        candidates_updated=0,
        duplicates_skipped=skipped_no_account,
        errors=errors,
    )
