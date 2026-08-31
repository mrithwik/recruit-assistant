"""
ResumeIngestor — one interface, two sources (folder, email). Both produce the
same IngestedResume shape so everything downstream (parsing, identity
resolution, mirroring, matching) is source-agnostic.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime

from app.models.schemas import IngestedResume


class ResumeIngestor(ABC):
    @abstractmethod
    def scan(
        self,
        date_start: datetime | None = None,
        date_end: datetime | None = None,
    ) -> AsyncIterator[IngestedResume]:
        """Yield every resume found in range. An async generator so network-
        bound implementations (email) can overlap I/O instead of blocking the
        event loop — see GmailIngestor/OutlookIngestor for the concurrent
        fetch pattern. Implementations should still stream page-by-page
        rather than buffering the whole mailbox, so large mailboxes/folder
        trees don't blow up memory."""
        ...
