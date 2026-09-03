"""Speed-plan lever — incremental scan applied to the opt-in nightly
scheduler too: a scheduled folder/mailbox shouldn't have its entire history
re-fetched and re-parsed every night, only what's new since that source's
own last successful run (ScheduledSource.last_run_at for folders,
EmailAccount.last_scanned_at for mailboxes)."""

import uuid
from collections.abc import AsyncIterator
from datetime import datetime

from app.models.db import EmailAccount, ScheduledSource
from app.models.enums import ResumeOrigin
from app.models.schemas import IngestedResume
from app.scanning.ingestor_base import ResumeIngestor


class _RecordingIngestor(ResumeIngestor):
    def __init__(self):
        self.calls: list[tuple] = []

    async def scan(self, date_start=None, date_end=None) -> AsyncIterator[IngestedResume]:
        self.calls.append((date_start, date_end))
        return
        yield  # pragma: no cover - unreachable, makes this an async generator


async def test_scheduled_folder_source_scans_from_its_own_last_run_at(storage, mock_llm, tmp_path, monkeypatch):
    from app.config import Settings

    watermark = datetime(2026, 8, 1, 12, 0, 0)
    with storage.session() as session:
        source = ScheduledSource(
            id=str(uuid.uuid4()),
            kind="folder",
            ref=str(tmp_path / "resumes"),
            include_subfolders=True,
            last_run_at=watermark,
        )
        session.add(source)
        session.commit()

    recorder = _RecordingIngestor()
    import app.scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module, "FolderIngestor", lambda *a, **k: recorder)

    settings = Settings(data_dir=str(tmp_path / "data_dir"))
    await scheduler_module._run_nightly_scan(storage, mock_llm, settings)

    assert recorder.calls == [(watermark, None)]


async def test_scheduled_email_source_scans_from_the_accounts_own_last_scanned_at(storage, mock_llm, tmp_path, monkeypatch):
    from app.config import Settings

    watermark = datetime(2026, 8, 1, 12, 0, 0)
    account_id = str(uuid.uuid4())
    with storage.session() as session:
        session.add(
            EmailAccount(
                id=account_id,
                provider="gmail",
                email_address="scheduled@example.com",
                keychain_ref="",
                status="connected",
                last_scanned_at=watermark,
            )
        )
        session.add(ScheduledSource(id=str(uuid.uuid4()), kind="email_account", ref=account_id))
        session.commit()

    recorder = _RecordingIngestor()
    import app.scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module, "build_email_ingestor", lambda *a, **k: (recorder, None))
    monkeypatch.setattr(scheduler_module, "get_use_mock_email", lambda: True)

    settings = Settings(data_dir=str(tmp_path / "data_dir"))
    await scheduler_module._run_nightly_scan(storage, mock_llm, settings)

    assert recorder.calls == [(watermark, None)]


async def test_a_never_run_scheduled_folder_source_scans_full_history(storage, mock_llm, tmp_path, monkeypatch):
    with storage.session() as session:
        source = ScheduledSource(
            id=str(uuid.uuid4()), kind="folder", ref=str(tmp_path / "resumes"), include_subfolders=True
        )
        session.add(source)
        session.commit()

    recorder = _RecordingIngestor()
    import app.scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module, "FolderIngestor", lambda *a, **k: recorder)

    from app.config import Settings

    settings = Settings(data_dir=str(tmp_path / "data_dir"))
    await scheduler_module._run_nightly_scan(storage, mock_llm, settings)

    assert recorder.calls == [(None, None)]
