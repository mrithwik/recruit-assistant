"""
BaseStorageBackend — the swap point for "local now, cloud/company-server later"
(mirrors Prodigon ADR-003's BaseQueue pattern: one abstract interface, current
implementation is LocalStorageBackend, a future CloudStorageBackend implements
the same methods with no caller-side changes).
"""

from abc import ABC, abstractmethod
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.db import Candidate, EmailAccount, IngestScanHistoryEntry, Job, Match, ResumeSource, SearchHistoryEntry, User


class BaseStorageBackend(ABC):
    @abstractmethod
    def session(self) -> Session: ...

    @abstractmethod
    def find_candidate_by_fingerprint(self, session: Session, fingerprint: str) -> Candidate | None: ...

    @abstractmethod
    def upsert_candidate(self, session: Session, candidate: Candidate) -> Candidate: ...

    @abstractmethod
    def add_resume_source(self, session: Session, source: ResumeSource) -> ResumeSource: ...

    @abstractmethod
    def find_resume_source_by_hash(
        self, session: Session, content_hash: str, source_ref: str
    ) -> ResumeSource | None: ...

    @abstractmethod
    def candidates_page(
        self,
        session: Session,
        start: datetime | None,
        end: datetime | None,
        source: str | None,
        query: str | None,
        sort: str,
        limit: int,
        offset: int,
        skills: list[str] | None = None,
        employment_statuses: list[str] | None = None,
        work_visa_statuses: list[str] | None = None,
        experience_min: float | None = None,
        experience_max: float | None = None,
        data_mode: str = "all",
        needs_attention: bool = False,
    ) -> tuple[list[Candidate], int]: ...

    @abstractmethod
    def candidate_facets(self, session: Session, data_mode: str = "all") -> tuple[list[str], float]:
        """Distinct skills actually present in the pool, plus the current
        max experience_years — backs the All Candidates filter bar's
        options (see routes/candidates.py's /facets)."""
        ...

    @abstractmethod
    def record_search_history(self, session: Session, entry: SearchHistoryEntry) -> SearchHistoryEntry: ...

    @abstractmethod
    def record_ingest_scan(self, session: Session, entry: IngestScanHistoryEntry) -> IngestScanHistoryEntry: ...

    @abstractmethod
    def any_user_exists(self, session: Session) -> bool: ...

    @abstractmethod
    def find_user_by_email(self, session: Session, email: str) -> User | None: ...

    @abstractmethod
    def create_user(self, session: Session, user: User) -> User: ...
