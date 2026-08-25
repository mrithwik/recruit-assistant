"""FastAPI DI — module globals initialized during lifespan, exposed via typed
getters used with Depends(). Same pattern as Prodigon ADR-008: simple,
explicit, testable, and avoids re-creating expensive clients per request."""

from functools import lru_cache

from app.config import Settings
from app.matching.llm_client import LLMClient, build_llm_client
from app.storage.base import BaseStorageBackend
from app.storage.local import LocalStorageBackend


@lru_cache
def get_settings() -> Settings:
    return Settings()


_storage: BaseStorageBackend | None = None
_llm_client: LLMClient | None = None


def init_dependencies(settings: Settings) -> None:
    global _storage, _llm_client
    _storage = LocalStorageBackend(settings.sqlite_path)
    _llm_client = build_llm_client(
        use_mock=settings.use_mock,
        openrouter_key=settings.openrouter_api_key,
        openai_key=settings.openai_api_key,
    )
    if settings.use_mock and settings.mock_email_fixtures_path:
        _seed_demo_mailbox(_storage)


def _seed_demo_mailbox(storage: BaseStorageBackend) -> None:
    """So the Email Access / Scan Sources tabs have something to select when
    testing against a generated sample dataset (see
    scripts/generate_sample_data.py) — idempotent, only inserts if missing."""
    import uuid

    from sqlalchemy import select

    from app.models.db import EmailAccount

    with storage.session() as session:
        existing = session.execute(
            select(EmailAccount).where(EmailAccount.email_address == "demo@mock.local")
        ).scalar_one_or_none()
        if existing:
            return
        session.add(
            EmailAccount(
                id=str(uuid.uuid4()),
                provider="gmail",
                email_address="demo@mock.local",
                keychain_ref="",
                status="connected",
            )
        )
        session.commit()


def get_storage() -> BaseStorageBackend:
    if _storage is None:
        raise RuntimeError("Storage backend not initialized.")
    return _storage


def get_llm_client() -> LLMClient:
    if _llm_client is None:
        raise RuntimeError("LLM client not initialized.")
    return _llm_client
