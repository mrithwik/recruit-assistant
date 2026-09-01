"""
mirror_writer — writes every ingested resume (regardless of origin) to the
same on-disk structure: data/candidates/<job-slug-or-unassigned>/<date>/<candidate-slug>/

This is what makes email-sourced resumes browsable offline as plain files,
and what gives folder-scanned and email-scanned resumes one converged shape
on disk (satisfies requirement 2.9 and the offline-access requirement).
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from app.models.schemas import CandidateProfile

if TYPE_CHECKING:
    from app.models.db import ResumeSource


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[\s_-]+", "-", text) or "unknown"


def write_mirror(
    candidates_dir: Path,
    candidate_id: str,
    profile: CandidateProfile,
    file_bytes: bytes,
    filename: str,
    date_submitted: datetime,
    origin: str,
    source_ref: str,
    semantic_summary: str,
    job_slug: str = "unassigned",
) -> str:
    candidate_slug = slugify(f"{profile.legal_first_name}-{profile.legal_last_name}-{candidate_id[:8]}")
    date_dir = date_submitted.strftime("%Y-%m-%d")
    target_dir = candidates_dir / job_slug / date_dir / candidate_slug
    target_dir.mkdir(parents=True, exist_ok=True)

    ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
    resume_path = target_dir / f"resume.{ext}"
    resume_path.write_bytes(file_bytes)

    (target_dir / "profile_summary.md").write_text(semantic_summary or "(summary pending)")

    (target_dir / "meta.json").write_text(
        json.dumps(
            {
                "candidate_id": candidate_id,
                "origin": origin,
                "source_ref": source_ref,
                "date_submitted": date_submitted.isoformat(),
                "original_filename": filename,
            },
            indent=2,
        )
    )
    return str(resume_path)


def delete_candidate_mirror(candidate_id: str, sources: list["ResumeSource"]) -> None:
    """Removes the on-disk mirror (resume file(s), summary, meta) for every
    ResumeSource a candidate has — the counterpart to write_mirror, needed
    for a real per-candidate PII delete (see routes/candidates.py).

    Two submissions on the same day land in the *same* target_dir (write_mirror
    keys the directory on candidate + date, not per-submission) — if they have
    different extensions, that directory holds two resume files
    (resume.pdf, resume.docx) sharing one meta.json/profile_summary.md, since
    each write overwrites those two. Sources are grouped by target_dir first,
    so every resume file in a shared directory is deleted in the same pass
    that reads and checks meta.json — checking meta.json is safe here because
    it's read once, before anything in that directory is deleted (an earlier,
    per-source version deleted meta.json while handling the first source
    sharing a directory, then had nothing left to check when it reached the
    second source pointing at the same directory, and defensively skipped it
    — silently orphaning that file; see QA finding). Deletes only file names
    write_mirror is known to create — never an rmtree, so an unexpected file
    in the directory is left alone rather than silently swept up."""
    by_dir: dict[Path, list[Path]] = {}
    for source in sources:
        resume_path = Path(source.file_path)
        by_dir.setdefault(resume_path.parent, []).append(resume_path)

    for target_dir, resume_paths in by_dir.items():
        meta_path = target_dir / "meta.json"
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if meta.get("candidate_id") != candidate_id:
            continue
        for resume_path in resume_paths:
            resume_path.unlink(missing_ok=True)
        (target_dir / "profile_summary.md").unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        try:
            target_dir.rmdir()
        except OSError:
            pass  # not empty — something unexpected is in there, leave it


def delete_candidate_mirror_partial(
    candidate_id: str, sources_to_delete: list["ResumeSource"], surviving_sources: list["ResumeSource"]
) -> None:
    """Removes mirror files for a *subset* of a candidate's sources, keeping
    the candidate itself — used when trimming a sample-data session off a
    candidate that also has sources from another session or from real data
    (see routes/dev_tools.py's delete_sample_session). Unlike
    delete_candidate_mirror, this must not blindly wipe every file in a
    shared target_dir: write_mirror keys directories on candidate + date,
    not per-submission, so two sources from *different* sessions scanned on
    the same day can land in the same directory — a same-extension resubmit
    even overwrites the earlier session's resume.<ext>/meta.json/
    profile_summary.md in place, so both ResumeSource rows can point at the
    literal same physical file. A resume file is only deleted if no
    surviving source still points at that exact path; meta.json/
    profile_summary.md (and the directory itself) are only removed if no
    surviving source points anywhere in that directory at all."""
    surviving_dirs = {Path(s.file_path).parent for s in surviving_sources}
    surviving_paths = {Path(s.file_path) for s in surviving_sources}

    by_dir: dict[Path, list[Path]] = {}
    for source in sources_to_delete:
        by_dir.setdefault(Path(source.file_path).parent, []).append(Path(source.file_path))

    for target_dir, resume_paths in by_dir.items():
        for resume_path in resume_paths:
            if resume_path in surviving_paths:
                continue  # a surviving source still needs this exact file
            resume_path.unlink(missing_ok=True)

        if target_dir in surviving_dirs:
            continue  # a surviving source still lives in this directory — leave meta.json/summary alone

        meta_path = target_dir / "meta.json"
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if meta.get("candidate_id") != candidate_id:
            continue
        (target_dir / "profile_summary.md").unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        try:
            target_dir.rmdir()
        except OSError:
            pass  # not empty — something unexpected is in there, leave it
