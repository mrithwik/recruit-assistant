"""Opt-in nightly auto-scan. Off by default (SCHEDULER_ENABLED=false) — main.py's
lifespan only calls start_scheduler() when that's explicitly turned on, and
even then only sources with a ScheduledSource row (the per-source "auto-scan
nightly" checkbox on the Scan Sources page) are touched. Reuses the exact
same run_scan() pipeline and email-ingestor selection the on-demand
/scan/* routes use (see routes/scan.py's build_email_ingestor) rather than
a second parallel implementation."""

from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.config import Settings
from app.logging import get_logger
from app.matching.llm_client import LLMClient
from app.models.db import EmailAccount, ScheduledSource
from app.routes.scan import build_email_ingestor, record_ingest_scan, resolve_mock_manifest_path
from app.runtime_settings import get_use_mock_email
from app.scanning.email_ingestor import load_fixtures_from_manifest
from app.scanning.folder_ingestor import FolderIngestor
from app.scanning.ingest_service import run_scan
from app.storage.base import BaseStorageBackend

logger = get_logger(__name__)


async def _run_nightly_scan(storage: BaseStorageBackend, llm: LLMClient, settings: Settings) -> None:
    with storage.session() as session:
        sources = list(session.execute(select(ScheduledSource)).scalars())
        if not sources:
            return

        # Loaded lazily, at most once — reads every fixture file off disk
        # (thousands, for a real generated dataset), so it's only worth
        # paying for if a scheduled source actually needs it.
        mock_fixtures: list | None = None

        for source in sources:
            try:
                # Nightly runs default to incremental: only mail/files new
                # since this source's own last successful run get
                # re-fetched and re-parsed, not its entire history every
                # night — see speed-plan "incremental scan" lever and
                # routes/scan.py's _effective_date_start (this path has no
                # explicit-override/full_rescan option, since it's never
                # user-driven — a full rescan here just means clearing
                # last_run_at/last_scanned_at, or using the on-demand
                # routes' full_rescan flag instead).
                date_start = source.last_run_at
                if source.kind == "folder":
                    ingestor = FolderIngestor([source.ref], include_subfolders=source.include_subfolders)
                else:
                    account = session.get(EmailAccount, source.ref)
                    if not account and not get_use_mock_email():
                        logger.warning("scheduled_source_account_missing", ref=source.ref)
                        continue
                    if mock_fixtures is None:
                        mock_fixtures = (
                            load_fixtures_from_manifest(resolve_mock_manifest_path(settings))
                            if get_use_mock_email()
                            else []
                        )
                    ingestor, error = build_email_ingestor(source.ref, account, settings, mock_fixtures)
                    if error:
                        logger.warning("scheduled_source_skipped", ref=source.ref, error=error)
                        continue
                    date_start = account.last_scanned_at if account else source.last_run_at

                # Captured before the fetch runs, not after run_scan (which
                # includes real parse/summarize LLM calls) finishes — a
                # message that arrives mid-scan would otherwise fall before
                # the recorded watermark but never have been in this scan's
                # results, silently and permanently excluding it from every
                # future incremental scan. See routes/scan.py's matching
                # comment / project-log's incremental-scan QA finding.
                scan_started_at = datetime.utcnow()
                result = await run_scan(
                    ingestor=ingestor,
                    storage=storage,
                    session=session,
                    candidates_dir=settings.candidates_dir,
                    llm=llm,
                    summary_model=settings.llm_scoring_model,
                    embedding_model=settings.embedding_model,
                    date_start=date_start,
                    max_concurrent_embeddings=settings.max_concurrent_llm_calls,
                    max_concurrent_processing=settings.max_concurrent_llm_calls,
                )
                source.last_run_at = scan_started_at
                if source.kind == "email_account" and account:
                    account.last_scanned_at = scan_started_at
                origin = "email" if source.kind == "email_account" else "folder"
                record_ingest_scan(storage, session, origin, f"auto-scan: {source.ref}", result)
                session.commit()
                logger.info(
                    "scheduled_scan_complete",
                    kind=source.kind,
                    ref=source.ref,
                    resumes_found=result.resumes_found,
                    candidates_created=result.candidates_created,
                )
            except Exception as exc:  # noqa: BLE001 - one bad source shouldn't cancel the rest of the nightly run
                logger.error("scheduled_scan_failed", kind=source.kind, ref=source.ref, error=str(exc))


def start_scheduler(storage: BaseStorageBackend, llm: LLMClient, settings: Settings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _run_nightly_scan,
        trigger=CronTrigger(hour=settings.scheduler_hour, minute=0),
        args=[storage, llm, settings],
        id="nightly_auto_scan",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("scheduler_started", hour=settings.scheduler_hour)
    return scheduler
