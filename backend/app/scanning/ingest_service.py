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

import asyncio
import dataclasses
import time
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dev_tools.session_tagging import extract_session_id
from app.matching.concurrency import bounded_gather
from app.matching.llm_client import LLMClient
from app.matching.matcher import summarize_candidate
from app.models.db import Candidate, ResumeSource
from app.models.schemas import IngestedResume, ScanResult
from app.scanning.folder_ingestor import content_hash
from app.scanning.identity_resolution import (
    build_resume_source,
    compute_fingerprint,
    merge_into_candidate,
)
from app.scanning.ingestor_base import ResumeIngestor
from app.scanning.mirror_writer import write_mirror
from app.scanning.parser import parse_resume
from app.storage.base import BaseStorageBackend


@dataclasses.dataclass
class _ParsedItem:
    """Result of the concurrent parse+summarize phase for one resume (see
    _parse_and_summarize) — carries either a successful profile/summary, an
    error message, or neither (meaning it was already a known (hash,
    source_ref) at the time this batch was dispatched, so no work was done
    at all). Kept separate from an exception so one bad resume never
    aborts its sibling tasks in the same asyncio.gather batch — matching
    the isolation the old per-resume try/except gave every resume before
    this was parallelized."""

    ingested: IngestedResume
    file_hash: str
    profile: object | None = None
    semantic_summary: str = ""
    error: str | None = None


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


async def _parse_and_summarize(
    ingested: IngestedResume,
    llm: LLMClient,
    summary_model: str,
    seen_sources: set[tuple[str, str]],
    stage_timings: dict[str, float],
) -> _ParsedItem:
    """The concurrent phase of processing one resume: parsing (LLM
    extraction + regex fallback, with the CPU/disk-bound text extraction
    itself offloaded to a thread — see parser.py) and summarizing, both
    network/CPU-bound and independent of every other resume in the batch —
    unlike identity resolution (needs the shared `fingerprints` dict
    updated in a specific order) or mirror-writing (can collide on the same
    on-disk directory for two same-day submissions of the same candidate),
    neither of which is safe to run concurrently across a batch. See
    run_scan's docstring for the full split.

    Never raises — every exception is caught and returned as `.error`, so
    one bad resume can't cancel its sibling tasks in the same
    asyncio.gather batch (bounded_gather doesn't use return_exceptions,
    matching the isolation the old sequential per-resume try/except gave
    every resume before this was parallelized)."""
    file_hash = content_hash(ingested.file_bytes)
    if (file_hash, ingested.source_ref) in seen_sources:
        # Already known as of when this batch was dispatched — skip the
        # expensive work entirely. A duplicate *within* this same batch
        # (seen_sources isn't mutated until the sequential phase below)
        # isn't caught here; run_scan's sequential loop re-checks and skips
        # it there instead, which is what actually matters for correctness.
        return _ParsedItem(ingested=ingested, file_hash=file_hash)
    try:
        stage_start = time.monotonic()
        profile = await parse_resume(ingested.file_bytes, ingested.filename, llm)
        stage_timings["parse"] += time.monotonic() - stage_start
        if not profile.email and ingested.sender_email:
            profile.email = ingested.sender_email

        stage_start = time.monotonic()
        semantic_summary = await summarize_candidate(llm, summary_model, profile.raw_text)
        stage_timings["summarize"] += time.monotonic() - stage_start
        return _ParsedItem(ingested=ingested, file_hash=file_hash, profile=profile, semantic_summary=semantic_summary)
    except Exception as exc:  # noqa: BLE001 - one bad resume shouldn't abort the whole scan
        return _ParsedItem(ingested=ingested, file_hash=file_hash, error=f"{ingested.filename}: {exc}")


async def _next_batch(resume_iter, batch_size: int) -> tuple[list[IngestedResume], Exception | None]:
    """Pulls up to `batch_size` items from the ingestor's async generator.
    If the generator itself raises partway through (a real mailbox
    exhausting its retries mid-scan, say — see
    test_ingest_service.py's checkpoint test), whatever was already pulled
    is still returned for processing rather than discarded: the old
    sequential `async for` let every already-yielded resume finish
    processing (and checkpoint) before the *next* iteration attempt raised
    and propagated — batching must not lose that "partial progress survives
    a mid-scan failure" guarantee just because several items are now
    fetched ahead at once. The caller processes `batch` first, then
    re-raises the returned exception, matching that same ordering."""
    batch: list[IngestedResume] = []
    for _ in range(batch_size):
        try:
            batch.append(await resume_iter.__anext__())
        except StopAsyncIteration:
            return batch, None
        except Exception as exc:  # noqa: BLE001 - re-raised by the caller after `batch` is processed
            return batch, exc
    return batch, None


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
    max_concurrent_processing: int = 8,
    checkpoint_every: int = 500,
    on_progress: "Callable[[ScanResult], None] | None" = None,
    on_should_cancel: "Callable[[], bool] | None" = None,
) -> ScanResult:
    """checkpoint_every / on_progress exist for real-mailbox-scale scans (see
    project-log): the previous single-commit-at-the-end design meant a scan
    that ran for tens of minutes lost *everything* if it failed near the
    end — a persistent network blip late in an otherwise-successful run
    would discard all of it. Committing (and flushing pending embeddings)
    every `checkpoint_every` resumes makes partial progress durable at a
    small throughput cost. on_progress is called after every resume (cheap,
    in-memory only) so a background job can report live counts instead of
    only a final result.

    Processing runs in batches of `max_concurrent_processing` resumes,
    split into two phases per batch (see the speed-plan report — this was
    previously fully sequential, one resume at a time, the report's #1
    lever): parsing and summarizing every resume in the batch concurrently
    (_parse_and_summarize, network/CPU-bound and independent per resume),
    then a second, strictly *sequential* pass applying identity resolution,
    mirror-writing, and persistence in the batch's original order. The
    second pass can't be parallelized the same way: identity resolution
    reads and writes the shared `fingerprints` dict (two resumes for the
    same person in one batch must merge into one Candidate, in order, not
    race each other), and write_mirror can collide on the same on-disk
    directory for two same-day submissions of the same candidate (see
    mirror_writer.py) — both need one resume fully finished before the
    next starts. write_mirror itself still runs off the event loop via
    asyncio.to_thread even though it's sequential here, so a scan stays
    responsive to other concurrent work (other jobs, the API) between
    writes rather than blocking on disk I/O — see the speed-plan report's
    #2 lever."""
    start_time = time.monotonic()
    resumes_found = 0
    created = 0
    updated = 0
    skipped = 0
    errors: list[str] = []
    # Total wall-clock seconds per stage, across every resume — see
    # ScanResult.stage_timings and the speed-plan report's "instrument
    # first" recommendation. Not mutually exclusive with elapsed_seconds,
    # and no longer even bounded by it for "parse"/"summarize" specifically:
    # those two now run concurrently across a batch, so their summed total
    # can legitimately exceed the batch's own wall-clock contribution to
    # elapsed_seconds — this is total time spent, not a timeline.
    stage_timings: dict[str, float] = {"parse": 0.0, "summarize": 0.0, "mirror_write": 0.0, "embed": 0.0}
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

    async def _flush_checkpoint() -> None:
        if pending_embeddings:
            embed_start = time.monotonic()
            embeddings = await bounded_gather(
                pending_embeddings,
                lambda pair: llm.embed(embedding_model, pair[1]),
                max_concurrent_embeddings,
            )
            stage_timings["embed"] += time.monotonic() - embed_start
            for (candidate, _text), embedding in zip(pending_embeddings, embeddings):
                candidate.embedding = embedding
            pending_embeddings.clear()
        session.commit()

    resume_iter = ingestor.scan(date_start=date_start, date_end=date_end).__aiter__()
    cancelled = False

    while not cancelled:
        batch, iterator_error = await _next_batch(resume_iter, max_concurrent_processing)
        if not batch:
            if iterator_error is not None:
                raise iterator_error
            break

        # Phase 1 — concurrent: parse + summarize every resume in the
        # batch. Each worker catches its own exceptions (see
        # _parse_and_summarize), so one bad resume can't take down its
        # siblings the way a raised exception through asyncio.gather would.
        parsed_items = await bounded_gather(
            batch,
            lambda ingested: _parse_and_summarize(ingested, llm, summary_model, seen_sources, stage_timings),
            max_concurrent_processing,
        )

        # Phase 2 — sequential, in the batch's original order: identity
        # resolution, mirror-writing, persistence. See run_scan's
        # docstring for why this can't be parallelized the same way.
        for parsed in parsed_items:
            ingested = parsed.ingested
            resumes_found += 1
            try:
                if parsed.error:
                    errors.append(parsed.error)
                    continue
                if (parsed.file_hash, ingested.source_ref) in seen_sources:
                    # Already seen — either known before this batch started
                    # (parsed.profile is None, Phase 1 skipped the work), or
                    # a duplicate of an earlier item processed earlier in
                    # this same sequential pass. Same outcome either way.
                    skipped += 1
                    continue

                profile = parsed.profile
                fingerprint = compute_fingerprint(profile)
                existing = fingerprints.get(fingerprint)
                is_new = existing is None
                prior_skills = set(existing.skills) if existing else set()
                prior_years = existing.experience_years if existing else 0.0

                candidate: Candidate = merge_into_candidate(existing, profile, fingerprint)
                if is_new:
                    candidate.date_submitted = ingested.date_submitted
                candidate.semantic_summary = parsed.semantic_summary
                candidate.history = _append_history_entry(candidate, ingested, is_new, prior_skills, prior_years)
                if embedding_model:
                    # Computed once at ingest time and cached on the row so
                    # matching never has to re-embed the whole pool on every
                    # run — see routes/matches.py. Deferred to a concurrent
                    # pass after this loop instead of awaited inline (see
                    # pending_embeddings above).
                    pending_embeddings.append((candidate, profile.raw_text or candidate.semantic_summary))

                stage_start = time.monotonic()
                # Off the event loop (see run_scan's docstring) — still one
                # at a time within this sequential pass, so two same-day
                # submissions of the same candidate can never race on the
                # same mirror directory.
                file_path = await asyncio.to_thread(
                    write_mirror,
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
                stage_timings["mirror_write"] += time.monotonic() - stage_start
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
                    content_hash=parsed.file_hash,
                    file_path=file_path,
                    date_submitted=ingested.date_submitted,
                    additional_attachments=ingested.additional_attachments,
                    email_link=ingested.email_link,
                    generation_session_id=extract_session_id(ingested.filename),
                )
                session.add(source)
                seen_sources.add((parsed.file_hash, ingested.source_ref))

                if is_new:
                    created += 1
                else:
                    updated += 1
            except Exception as exc:  # noqa: BLE001 - one bad resume shouldn't abort the whole scan
                errors.append(f"{ingested.filename}: {exc}")
            finally:
                # A `finally` (not code after the try/except) so this still runs
                # on the "already seen this exact resume" `continue` path above,
                # not just the fall-through/exception paths.
                if on_progress:
                    on_progress(
                        ScanResult(
                            resumes_found=resumes_found,
                            candidates_created=created,
                            candidates_updated=updated,
                            duplicates_skipped=skipped,
                            errors=list(errors),
                            elapsed_seconds=round(time.monotonic() - start_time, 2),
                            # Deliberately unrounded — a caller combining
                            # several run_scan() calls (scan_email_accounts,
                            # scan_all) sums these; rounding here first can
                            # quantize a real but small per-call time down to
                            # 0.00, and several 0.00s still sum to 0.00 even
                            # though real work happened (see QA finding).
                            # Rounded once, at the point a ScanResult is
                            # actually handed to a job as its final/displayed
                            # state — see routes/scan.py's _round_stage_timings.
                            stage_timings=dict(stage_timings),
                        )
                    )
                if resumes_found % checkpoint_every == 0:
                    await _flush_checkpoint()

                # Checked once per resume (cheap, in-memory) — cancelling
                # stops the scan here, after committing everything found so
                # far, not mid-resume. Whatever was already found stays;
                # nothing about the resumes not yet reached is touched. The
                # rest of this batch's already-parsed items are still
                # applied (Phase 1's work for them is done and paid for;
                # discarding it would waste it for nothing) — no `break`
                # here, deliberately: setting `cancelled` alone lets this
                # inner loop run to completion over the rest of the current
                # batch, and only stops the outer while loop from pulling
                # any further batches from the ingestor.
                if on_should_cancel and on_should_cancel():
                    cancelled = True

        if iterator_error is not None:
            # This batch's already-fetched items were just processed (and
            # checkpointed) above — now propagate the failure exactly as
            # the old sequential `async for` did when the *next* iteration
            # attempt raised, only after every already-yielded resume had
            # already been handled.
            raise iterator_error

    await _flush_checkpoint()
    return ScanResult(
        resumes_found=resumes_found,
        candidates_created=created,
        candidates_updated=updated,
        duplicates_skipped=skipped,
        errors=errors,
        elapsed_seconds=round(time.monotonic() - start_time, 2),
        # Unrounded — see the on_progress ScanResult above for why.
        stage_timings=stage_timings,
    )
