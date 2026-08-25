from app.models.enums import ResumeOrigin
from app.scanning.folder_ingestor import FolderIngestor, content_hash


def test_folder_ingestor_finds_supported_files(tmp_path):
    (tmp_path / "resume.txt").write_text("Jordan Rivera, backend engineer")
    (tmp_path / "notes.md").write_text("not a resume format we scan")
    sub = tmp_path / "subfolder"
    sub.mkdir()
    (sub / "resume2.txt").write_text("Another candidate")

    ingestor = FolderIngestor([str(tmp_path)], include_subfolders=True)
    results = list(ingestor.scan())

    assert len(results) == 2
    assert all(r.origin == ResumeOrigin.FOLDER for r in results)
    assert {r.filename for r in results} == {"resume.txt", "resume2.txt"}


def test_folder_ingestor_respects_subfolder_toggle(tmp_path):
    sub = tmp_path / "subfolder"
    sub.mkdir()
    (sub / "resume.txt").write_text("Candidate in subfolder")

    ingestor = FolderIngestor([str(tmp_path)], include_subfolders=False)
    assert list(ingestor.scan()) == []


def test_content_hash_is_stable():
    assert content_hash(b"abc") == content_hash(b"abc")
    assert content_hash(b"abc") != content_hash(b"abd")
