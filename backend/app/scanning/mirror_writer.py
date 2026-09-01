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
    """Removes the on-disk mirror (resume file, summary, meta) for every
    ResumeSource a candidate has — the counterpart to write_mirror, needed
    for a real per-candidate PII delete (see routes/candidates.py). Deletes
    only the three files write_mirror is known to create, by name, and only
    after meta.json confirms the directory belongs to this candidate — never
    an rmtree, so an unexpected file in the directory is left alone rather
    than silently swept up."""
    for source in sources:
        resume_path = Path(source.file_path)
        target_dir = resume_path.parent
        meta_path = target_dir / "meta.json"
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if meta.get("candidate_id") != candidate_id:
            continue
        for name in (resume_path.name, "profile_summary.md", "meta.json"):
            (target_dir / name).unlink(missing_ok=True)
        try:
            target_dir.rmdir()
        except OSError:
            pass  # not empty — something unexpected is in there, leave it
