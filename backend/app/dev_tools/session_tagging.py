"""Tags each sample-data generation run with a session id, embedded directly
in the filenames it writes (`sess-<timestamp>-<hex>__<original-name>`) —
this is the one signal both FolderIngestor (which only ever sees a bare
filename on disk) and MockEmailIngestor (which reads a manifest entry's
`attachment_file`, itself just the same generated filename) already carry
through to `IngestedResume.filename` with zero changes to either ingestor.
`ingest_service.py` extracts it back out via `extract_session_id` and stamps
it onto `ResumeSource.generation_session_id`, which is what lets a
recruiter delete one generation batch's candidates without touching any
other."""

import re
import uuid
from datetime import datetime

_SESSION_ID_RE = re.compile(r"^sess-\d{8}-\d{6}-[0-9a-f]{6}$")
_TAGGED_FILENAME_RE = re.compile(r"^(sess-\d{8}-\d{6}-[0-9a-f]{6})__")


def new_session_id(when: datetime | None = None) -> str:
    when = when or datetime.now()
    return f"sess-{when:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


def is_session_id(value: str) -> bool:
    return bool(_SESSION_ID_RE.match(value))


def tag_filename(session_id: str, filename: str) -> str:
    return f"{session_id}__{filename}"


def extract_session_id(filename: str) -> str | None:
    match = _TAGGED_FILENAME_RE.match(filename)
    return match.group(1) if match else None
