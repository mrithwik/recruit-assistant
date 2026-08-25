"""
Orchestrates one scan run: ingestor.scan() -> parse -> identity resolution ->
mirror-to-disk -> persist. Same function runs for both FolderIngestor and
EmailIngestor since they emit the same IngestedResume shape — this is the
convergence point described in the plan's ADR-style reasoning.

Performance note: earlier versions ran one `find_candidate_by_fingerprint`
and one `find_resume_source_by_hash` SQL query *per resume*, plus a
`session.flush()` after every insert — fine at dozens of resumes, a real
bottleneck at thousands (10,000 resumes = 20,000+ round trips + 10,000
flushes). Both existing fingerprints and existing (hash, source_ref) pairs
are now preloaded into memory once before the loop, updated in memory as new
rows are created, and nothing is flushed until the single commit at the end
— see project-log for the before/after numbers.
"""

import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.matching.concurrency import bounded_gather
from app.matching.llm_client import LLMClient
from app.matching.matcher import summarize_candidate
from app.models.db import Candidate, ResumeSource
from app.models.schemas import ScanResult
from app.scanning.folder_ingestor import content_hash
from app.scanning.identity_resolution import build_resume_source, compute_fingerprint, merge_into_candidate
from app.scanning.ingestor_base import ResumeIngestor
from app.scanning.mirror_writer import write_mirror
from app.scanning.parser import parse_resume
from app.storage.base import BaseStorageBackend


def _append_history_entry(
    candidate: Candidate, ingested, is_new: bool, prior_skills: set, prior_years: float
) -> list:
    """Builds this ingestion's dated timeline entry and returns the full
    history re-sorted by date. Ingestion order isn't guaranteed chronological
    (a folder walk, or an out-of-order email/upskill-journey scan can process
    a later resubmission before the true earliest one) — so "is_new" (first
    time this identity was *seen*) is not the same as "earliest by date", and
    the entry gets relabeled after sorting: whichever entry ends up
    chronologically first is the "initial" one, regardless of ingestion order.
    `detail` carries the diff (skills/experience changed); the "Initial
    application" vs "Updated" framing is derived purely from sort position.
    """
    if is_new:
        # detail is filled in either way (never blank) since a relabel after
        # sorting can display this under the "Updated via X: {detail}."
        # template if a chronologically earlier entry shows up later.
        detail = f"{candidate.experience_years:g} yrs experience" if candidate.experience_years else "no experience info detected"
    else:
        new_skills = set(candidate.skills) - prior_skills
        parts = []
        if new_skills:
            parts.append(f"added skills: {', '.join(sorted(new_skills))}")
        if candidate.experience_years > prior_years:
            parts.append(f"experience now {candidate.experience_years:g} yrs (was {prior_years:g})")
        detail = "; ".join(parts) if parts else "resubmitted, no new info detected"

    entry = {
        "date": ingested.date_submitted.isoformat(),
        "origin": ingested.origin.value,
        "detail": detail,
    }
    updated_history = [*(candidate.history or []), entry]
    updated_history.sort(key=lambda h: h["date"])

    for i, h in enumerate(updated_history):
        if i == 0:
            h["note"] = f"Initial application via {h['origin']}." + (f" {h['detail']}." if h["detail"] else "")
        else:
            h["note"] = f"Updated via {h['origin']}: {h['detail']}."
    return updated_history


async def run_scan(
    ingestor: ResumeIngestor,
    storage: BaseStorageBackend,
    session: Session,
    candidates_dir: Path,
    llm: LLMClient,
    summary_model: str,
    embedding_model: str = "",
    date_start=None,
    date_end=None,
    max_concurrent_embeddings: int = 8,
) -> ScanResult:
    start_time = time.monotonic()
    resumes_found = 0
    created = 0
    updated = 0
    skipped = 0
    errors: list[str] = []
    # (candidate, text) pairs needing an embedding, collected during the loop
    # and computed afterward in one bounded-concurrency pass instead of one
    # sequential `await llm.embed()` per resume — see module docstring. If two
    # resumes in this same scan merge into the same candidate, both entries
    # are kept and applied in loop order below, so the later one still wins,
    # matching the previous sequential behavior exactly.
    pending_embeddings: list[tuple[Candidate, str]] = []

    # Preload once instead of querying per resume — see module docstring.
    fingerprints: dict[str, Candidate] = {
        c.identity_fingerprint: c for c in session.execute(select(Candidate)).scalars()
    }
    seen_sources: set[tuple[str, str]] = set(
        session.execute(select(ResumeSource.content_hash, ResumeSource.source_ref)).all()
    )

    for ingested in ingestor.scan(date_start=date_start, date_end=date_end):
        resumes_found += 1
        try:
            file_hash = content_hash(ingested.file_bytes)
            if (file_hash, ingested.source_ref) in seen_sources:
                # Same file, same source, already processed by a prior scan —
                # skip re-parsing/re-scoring entirely rather than creating a
                # second ResumeSource row for identical content.
                skipped += 1
                continue

            profile = await parse_resume(ingested.file_bytes, ingested.filename, llm)
            if not profile.email and ingested.sender_email:
                profile.email = ingested.sender_email

            fingerprint = compute_fingerprint(profile)
            existing = fingerprints.get(fingerprint)
            is_new = existing is None
            prior_skills = set(existing.skills) if existing else set()
            prior_years = existing.experience_years if existing else 0.0

            candidate: Candidate = merge_into_candidate(existing, profile, fingerprint)
            if is_new:
                candidate.date_submitted = ingested.date_submitted
            candidate.semantic_summary = await summarize_candidate(llm, summary_model, profile.raw_text)
            candidate.history = _append_history_entry(candidate, ingested, is_new, prior_skills, prior_years)
            if embedding_model:
                # Computed once at ingest time and cached on the row so
                # matching never has to re-embed the whole pool on every
                # run — see routes/matches.py. Deferred to a concurrent pass
                # after this loop instead of awaited inline (see
                # pending_embeddings above).
                pending_embeddings.append((candidate, profile.raw_text or candidate.semantic_summary))

            file_path = write_mirror(
                candidates_dir=candidates_dir,
                candidate_id=candidate.id,
                profile=profile,
                file_bytes=ingested.file_bytes,
                filename=ingested.filename,
                date_submitted=ingested.date_submitted,
                origin=ingested.origin.value,
                source_ref=ingested.source_ref,
                semantic_summary=candidate.semantic_summary,
            )
            candidate.primary_file_path = file_path

            # No flush here — the object's id is already a client-generated
            # uuid, so nothing downstream needs the row to exist in the DB
            # yet, only in these in-memory caches (updated right below).
            session.add(candidate)
            fingerprints[fingerprint] = candidate

            source = build_resume_source(
                candidate_id=candidate.id,
                origin=ingested.origin,
                source_ref=ingested.source_ref,
                content_hash=file_hash,
                file_path=file_path,
                date_submitted=ingested.date_submitted,
            )
            session.add(source)
            seen_sources.add((file_hash, ingested.source_ref))

            if is_new:
                created += 1
            else:
                updated += 1
        except Exception as exc:  # noqa: BLE001 - one bad resume shouldn't abort the whole scan
            errors.append(f"{ingested.filename}: {exc}")

    if pending_embeddings:
        embeddings = await bounded_gather(
            pending_embeddings,
            lambda pair: llm.embed(embedding_model, pair[1]),
            max_concurrent_embeddings,
        )
        for (candidate, _text), embedding in zip(pending_embeddings, embeddings):
            candidate.embedding = embedding

    session.commit()
    return ScanResult(
        resumes_found=resumes_found,
        candidates_created=created,
        candidates_updated=updated,
        duplicates_skipped=skipped,
        errors=errors,
        elapsed_seconds=round(time.monotonic() - start_time, 2),
    )
