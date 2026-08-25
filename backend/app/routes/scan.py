"""Scan Sources tab (2.2) — folder scan and email scan, both converging on
run_scan(). Both are first-class: a recruiter with no local resumes yet can
scan email alone, or a recruiter with only saved folders can skip email."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings
from app.dependencies import get_llm_client, get_settings, get_storage
from app.email_auth.oauth import get_valid_access_token
from app.matching.llm_client import LLMClient
from app.models.db import EmailAccount
from app.models.schemas import ScanEmailRequest, ScanFolderRequest, ScanResult
from app.scanning.email_ingestor import GmailIngestor, MockEmailIngestor, OutlookIngestor, load_fixtures_from_manifest
from app.scanning.folder_ingestor import FolderIngestor
from app.scanning.ingest_service import run_scan
from app.storage.base import BaseStorageBackend

router = APIRouter(prefix="/api/v1/scan", tags=["scan"])

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MOCK_MANIFEST = REPO_ROOT / "sample_data" / "emails_manifest.json"


def _resolve_mock_manifest_path(settings: Settings) -> str:
    # MOCK_EMAIL_FIXTURES_PATH may not be set yet on a fresh install — the
    # in-app generator (dev_tools.py) writes to sample_data/ by default
    # regardless, so fall back to that path rather than silently scanning
    # nothing (see project-log: "generated data not showing up" bug).
    if settings.mock_email_fixtures_path:
        return settings.mock_email_fixtures_path
    return str(DEFAULT_MOCK_MANIFEST)


@router.post("/folders", response_model=ScanResult)
async def scan_folders(
    payload: ScanFolderRequest,
    storage: BaseStorageBackend = Depends(get_storage),
    llm: LLMClient = Depends(get_llm_client),
    settings: Settings = Depends(get_settings),
):
    ingestor = FolderIngestor(payload.folder_paths, include_subfolders=payload.include_subfolders)
    with storage.session() as session:
        return await run_scan(
            ingestor=ingestor,
            storage=storage,
            session=session,
            candidates_dir=settings.candidates_dir,
            llm=llm,
            summary_model=settings.llm_scoring_model,
            embedding_model=settings.embedding_model,
            date_start=payload.date_start,
            date_end=payload.date_end,
            max_concurrent_embeddings=settings.max_concurrent_llm_calls,
        )


@router.post("/email-accounts", response_model=ScanResult)
async def scan_email_accounts(
    payload: ScanEmailRequest,
    storage: BaseStorageBackend = Depends(get_storage),
    llm: LLMClient = Depends(get_llm_client),
    settings: Settings = Depends(get_settings),
):
    combined = ScanResult(resumes_found=0, candidates_created=0, candidates_updated=0, duplicates_skipped=0, errors=[])
    mock_fixtures = (
        load_fixtures_from_manifest(_resolve_mock_manifest_path(settings)) if settings.use_mock else []
    )

    with storage.session() as session:
        for account_id in payload.account_ids:
            if settings.use_mock:
                ingestor = MockEmailIngestor(fixtures=mock_fixtures)
            else:
                account = session.get(EmailAccount, account_id)
                if not account:
                    combined.errors.append(f"{account_id}: account not found")
                    continue
                access_token = get_valid_access_token(
                    account_id,
                    account.provider,
                    ms_client_id=settings.ms_oauth_client_id,
                    ms_client_secret=settings.ms_oauth_client_secret,
                    ms_tenant_id=settings.ms_oauth_tenant_id,
                )
                if not access_token:
                    combined.errors.append(f"{account_id}: no stored token, reconnect the account")
                    continue
                if account.provider == "gmail":
                    ingestor = GmailIngestor(access_token, account.email_address)
                else:
                    ingestor = OutlookIngestor(access_token, account.email_address)

            result = await run_scan(
                ingestor=ingestor,
                storage=storage,
                session=session,
                candidates_dir=settings.candidates_dir,
                llm=llm,
                summary_model=settings.llm_scoring_model,
                embedding_model=settings.embedding_model,
                date_start=payload.date_start,
                date_end=payload.date_end,
                max_concurrent_embeddings=settings.max_concurrent_llm_calls,
            )
            combined.resumes_found += result.resumes_found
            combined.candidates_created += result.candidates_created
            combined.candidates_updated += result.candidates_updated
            combined.duplicates_skipped += result.duplicates_skipped
            combined.errors.extend(result.errors)
            combined.elapsed_seconds = round(combined.elapsed_seconds + result.elapsed_seconds, 2)

    if not payload.account_ids:
        raise HTTPException(400, "No email accounts specified.")
    return combined
