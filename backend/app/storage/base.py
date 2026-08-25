"""
BaseStorageBackend — the swap point for "local now, cloud/company-server later"
(mirrors Prodigon ADR-003's BaseQueue pattern: one abstract interface, current
implementation is LocalStorageBackend, a future CloudStorageBackend implements
the same methods with no caller-side changes).
"""

from abc import ABC, abstractmethod
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.db import Candidate, EmailAccount, Job, Match, ResumeSource, SearchHistoryEntry, User


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
    ) -> tuple[list[Candidate], int]: ...

    @abstractmethod
    def record_search_history(self, session: Session, entry: SearchHistoryEntry) -> SearchHistoryEntry: ...

    @abstractmethod
    def any_user_exists(self, session: Session) -> bool: ...

    @abstractmethod
    def find_user_by_email(self, session: Session, email: str) -> User | None: ...

    @abstractmethod
    def create_user(self, session: Session, user: User) -> User: ...
