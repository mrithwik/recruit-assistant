"""FolderIngestor — recursive multi-folder resume scan (requirement 2.2).

Dedupes by content hash so repeated scans of the same folder don't reprocess
unchanged files; date_submitted falls back to file mtime when no better
signal exists (folder-dropped resumes rarely carry a "submitted date").
"""

import hashlib
from collections.abc import AsyncIterator, Iterator
from datetime import datetime
from pathlib import Path

from app.models.enums import ResumeOrigin
from app.models.schemas import IngestedResume
from app.scanning.ingestor_base import ResumeIngestor

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


class FolderIngestor(ResumeIngestor):
    def __init__(self, folder_paths: list[str], include_subfolders: bool = True):
        self.folder_paths = [Path(p) for p in folder_paths]
        self.include_subfolders = include_subfolders

    def _iter_files(self) -> Iterator[Path]:
        for root in self.folder_paths:
            if not root.exists():
                continue
            glob_fn = root.rglob if self.include_subfolders else root.glob
            for path in glob_fn("*"):
                if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                    yield path

    async def scan(
        self,
        date_start: datetime | None = None,
        date_end: datetime | None = None,
    ) -> AsyncIterator[IngestedResume]:
        for path in self._iter_files():
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            if date_start and mtime < date_start:
                continue
            if date_end and mtime > date_end:
                continue
            file_bytes = path.read_bytes()
            yield IngestedResume(
                origin=ResumeOrigin.FOLDER,
                source_ref=str(path.parent),
                file_bytes=file_bytes,
                filename=path.name,
                date_submitted=mtime,
            )


def content_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()
