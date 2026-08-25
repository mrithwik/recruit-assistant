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

from app.models.schemas import CandidateProfile


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
