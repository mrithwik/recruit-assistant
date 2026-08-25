import json

from app.models.enums import ResumeOrigin
from app.scanning.email_ingestor import load_fixtures_from_manifest


def test_load_fixtures_missing_manifest_returns_empty(tmp_path):
    assert load_fixtures_from_manifest(str(tmp_path / "does_not_exist.json")) == []


def test_load_fixtures_from_manifest(tmp_path):
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    (attachments / "a.txt").write_text("Jordan Rivera resume content")

    manifest = {
        "attachments_dir": "attachments",
        "emails": [
            {
                "id": "app-1",
                "from_name": "Jordan Rivera",
                "from_email": "jordan@example.com",
                "date": "2026-01-05T12:00:00",
                "attachment_file": "a.txt",
            },
            {
                # References a file that doesn't exist — should be skipped, not error.
                "id": "app-2",
                "from_name": "Ghost Candidate",
                "from_email": "ghost@example.com",
                "date": "2026-01-06T12:00:00",
                "attachment_file": "missing.txt",
            },
        ],
    }
    manifest_path = tmp_path / "emails_manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    fixtures = load_fixtures_from_manifest(str(manifest_path))

    assert len(fixtures) == 1
    f = fixtures[0]
    assert f.origin == ResumeOrigin.EMAIL
    assert f.sender_email == "jordan@example.com"
    assert f.filename == "a.txt"
    assert b"Jordan Rivera" in f.file_bytes
