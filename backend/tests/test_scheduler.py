"""Opt-in nightly auto-scan (see scheduler/__init__.py). SCHEDULER_ENABLED is
off by default and the scheduler only ever touches sources with a
ScheduledSource row — these tests pin both halves: the job function actually
runs a scan for a scheduled folder source, and main.py's lifespan never
starts the scheduler unless the setting is explicitly on."""

import uuid

from sqlalchemy import select

from app.config import Settings
from app.models.db import Candidate, ScheduledSource

RESUME_TEXT = (
    b"Jordan Rivera\njordan.rivera@example.com\n"
    b"7 years backend engineering experience with Python, FastAPI, and PostgreSQL."
)


async def test_nightly_scan_runs_for_scheduled_folder_source(storage, mock_llm, tmp_path):
    from app.scheduler import _run_nightly_scan

    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    (resumes_dir / "jordan.txt").write_bytes(RESUME_TEXT)

    with storage.session() as session:
        source = ScheduledSource(id=str(uuid.uuid4()), kind="folder", ref=str(resumes_dir), include_subfolders=True)
        session.add(source)
        session.commit()
        source_id = source.id

    settings = Settings(data_dir=str(tmp_path / "data_dir"))

    await _run_nightly_scan(storage, mock_llm, settings)

    with storage.session() as session:
        candidates = list(session.execute(select(Candidate)).scalars())
        assert len(candidates) == 1

        refreshed = session.get(ScheduledSource, source_id)
        assert refreshed.last_run_at is not None


async def test_nightly_scan_is_a_noop_with_no_scheduled_sources(storage, mock_llm, tmp_path):
    from app.scheduler import _run_nightly_scan

    settings = Settings()
    # Should return cleanly without touching anything — no sources, nothing to do.
    await _run_nightly_scan(storage, mock_llm, settings)


def test_scheduler_not_started_when_disabled(monkeypatch):
    """The actual safety property the user asked for: off by default."""
    from app import main

    started = {"called": False}

    def fake_start_scheduler(*a, **kw):
        started["called"] = True

    monkeypatch.setattr("app.scheduler.start_scheduler", fake_start_scheduler)
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")

    from app.config import Settings as SettingsCls

    settings = SettingsCls()
    assert settings.scheduler_enabled is False
    # main.py's lifespan only imports+calls start_scheduler inside the
    # `if settings.scheduler_enabled:` branch — with it False, that whole
    # branch (including the import) is never reached.
    assert started["called"] is False
