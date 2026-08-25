"""
ResumeIngestor — one interface, two sources (folder, email). Both produce the
same IngestedResume shape so everything downstream (parsing, identity
resolution, mirroring, matching) is source-agnostic.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import datetime

from app.models.schemas import IngestedResume


class ResumeIngestor(ABC):
    @abstractmethod
    def scan(
        self,
        date_start: datetime | None = None,
        date_end: datetime | None = None,
    ) -> Iterator[IngestedResume]:
        """Yield every resume found in range. Implementations should stream,
        not buffer, so large mailboxes/folder trees don't blow up memory."""
        ...
