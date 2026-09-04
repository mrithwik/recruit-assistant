"""
Two-stage matching pipeline + LLM-as-judge (requirement 7):

  1. Embedding pre-filter — cheap, runs over every candidate in the pool.
  2. Deep LLM scoring — stronger model, runs only on the embedding shortlist.
  3. LLM judge — reviews borderline (40-70) or explicitly re-flagged scores,
     can correct them. This is the "reiterate the scan as needed" hook.

Tiers map straight to the color bands in the Candidate Results UI (2.5).
"""

import time

from app.matching.concurrency import bounded_gather
from app.matching.embeddings import top_n_by_similarity
from app.matching.llm_client import LLMClient
from app.matching.prompts import (
    JUDGE_PROMPT,
    RESUME_TEXT_LABEL,
    SCORING_PROMPT,
    SUMMARY_LABEL,
    SUMMARY_PROMPT,
    TRIAGE_PROMPT,
)
from app.models.enums import MatchTier

DEFAULT_MAX_CONCURRENT_LLM_CALLS = 8

JUDGE_REVIEW_LOW = 40
JUDGE_REVIEW_HIGH = 70

SHORTLIST_MULTIPLIER = 3  # embedding pre-filter keeps top_n * this many before deep scoring

# triage_mode="llm" only: how much wider the embedding net is cast before the
# LLM triage pass narrows it back down to the same top_n * SHORTLIST_MULTIPLIER
# deep-score gets either way — the LLM gets a chance to pull in candidates
# pure vector similarity ranked outside the narrower embedding-only shortlist,
# without changing deep_score's own cost/timing between the two modes.
TRIAGE_WIDENING_MULTIPLIER = 3


def score_to_tier(score: float, has_red_flag: bool) -> MatchTier:
    if has_red_flag:
        return MatchTier.RED_FLAG
    if score >= 85:
        return MatchTier.GREAT
    if score >= 70:
        return MatchTier.GOOD
    if score >= 50:
        return MatchTier.AVERAGE
    return MatchTier.POOR


async def deep_score(
    llm: LLMClient, model: str, job_text: str, resume_text: str, profile, resume_label: str = RESUME_TEXT_LABEL
) -> dict:
    """resume_label tells the model honestly what resume_text actually is —
    the raw resume (default) or an AI-generated summary (pass SUMMARY_LABEL)
    — see prompts.py for why a mislabeled input risks the model reading a
    summary's deliberate omissions as gaps in the real resume."""
    prompt = SCORING_PROMPT.format(
        job_text=job_text[:6000],
        skills=", ".join(profile.skills),
        experience_years=profile.experience_years,
        education=", ".join(profile.education),
        employment_status=profile.employment_status.value,
        work_visa_status=profile.work_visa_status.value,
        resume_label=resume_label,
        resume_text=resume_text[:6000],
    )
    return await llm.extract_json(prompt, model=model)


async def judge_score(
    llm: LLMClient, model: str, job_text: str, candidate_summary: str, score_result: dict
) -> dict:
    prompt = JUDGE_PROMPT.format(
        job_text=job_text[:4000],
        candidate_summary=candidate_summary,
        score=score_result.get("score"),
        matched=score_result.get("matched"),
        gaps=score_result.get("gaps"),
    )
    return await llm.extract_json(prompt, model=model)


async def summarize_candidate(llm: LLMClient, model: str, resume_text: str) -> str:
    return await llm.complete(model, SUMMARY_PROMPT.format(resume_text=resume_text[:6000]))


async def llm_triage(
    llm: LLMClient, model: str, job_text: str, candidates: list[dict], keep_n: int, max_concurrent: int
) -> tuple[list[dict], list[str]]:
    """triage_mode="llm": a cheap pass (meant for a fast/low-cost model —
    settings.llm_triage_model, swappable for a local model later) re-ranks a
    wider embedding-similarity net down to keep_n before the expensive
    deep-score stage, catching relevance a pure vector-similarity shortlist
    might miss. Scores against the candidate's summary (falling back to raw
    resume text, same as deep_score) — never the full deep-score prompt,
    that's the whole point of this being the cheap stage.

    One candidate's triage call failing (a transient provider error, say)
    must not abort the whole batch via bounded_gather's unmodified
    asyncio.gather — caught per-item and recorded in the returned errors
    list instead. Fails open (a neutral mid-range relevance, per
    TRIAGE_PROMPT's own "err toward including if unsure" instruction) rather
    than silently dropping the candidate from consideration entirely."""
    errors: list[str] = []

    async def _triage_one(c: dict) -> tuple[dict, float]:
        try:
            candidate_summary = c.get("summary") or c["resume_text"]
            prompt = TRIAGE_PROMPT.format(job_text=job_text[:4000], candidate_summary=candidate_summary[:2000])
            result = await llm.extract_json(prompt, model=model)
            return c, float(result.get("relevance", 0))
        except Exception as exc:  # noqa: BLE001 - isolated to this one candidate, doesn't abort the batch
            errors.append(f"triage failed for candidate {c['id']}: {exc}")
            return c, 50.0

    scored = await bounded_gather(candidates, _triage_one, max_concurrent)
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [c for c, _relevance in scored[:keep_n]], errors


async def match_job_against_pool(
    llm: LLMClient,
    triage_model: str,
    scoring_model: str,
    judge_model: str,
    job_text: str,
    job_embedding: list[float],
    candidate_pool: list[dict],  # [{id, embedding, resume_text, profile}]
    top_n: int,
    max_concurrent: int = DEFAULT_MAX_CONCURRENT_LLM_CALLS,
    triage_mode: str = "embedding",
) -> tuple[list[dict], dict[str, float], list[str]]:
    """Returns (scored results, stage_timings, errors) — up to
    top_n * SHORTLIST_MULTIPLIER candidates, deep-scored and judge-reviewed
    where warranted. Caller persists Match rows and trims to top_n for
    display. stage_timings feeds ScanResult.stage_timings (see the
    speed-plan report's "instrument first" recommendation) — "triage",
    "deep_score" and "judge" are each one bounded_gather pass's wall-clock
    time, not a per-candidate sum.

    triage_mode="embedding" (default) keeps the original behavior exactly:
    pure cosine-similarity picks the top_n * SHORTLIST_MULTIPLIER shortlist,
    "triage" costs 0 seconds. triage_mode="llm" casts a wider embedding net
    (see TRIAGE_WIDENING_MULTIPLIER) and spends a cheap LLM pass (see
    llm_triage) narrowing it back down to the same final size — deep_score's
    own cost is identical either way, only which candidates reach it differs.

    Deep-scoring and judging each run as one bounded-concurrency pass (via
    bounded_gather) instead of a single sequential loop — at top_n=20 /
    SHORTLIST_MULTIPLIER=3 that's up to 60 deep-score calls; awaiting them
    one at a time left most of the wall-clock time idle on network I/O.

    One candidate's deep-score or judge call failing must not abort the
    whole run and lose every other candidate's already-computed results —
    the same "one bad thing shouldn't take down everything else" guarantee
    already enforced in ingestion (per-resume) and email fan-in
    (per-source). A failing deep-score drops that one candidate from the
    results (nothing to score it with); a failing judge call just leaves
    that candidate's deep-score result un-reviewed, exactly like a
    candidate whose score never fell in the judge-review band to begin
    with. Both are recorded in the returned errors list rather than
    raised."""
    errors: list[str] = []
    keep_n = top_n * SHORTLIST_MULTIPLIER
    embedding_n = keep_n * TRIAGE_WIDENING_MULTIPLIER if triage_mode == "llm" else keep_n
    embeddings_by_id = {c["id"]: c["embedding"] for c in candidate_pool}
    shortlist_ids = set(top_n_by_similarity(job_embedding, embeddings_by_id, n=embedding_n))
    shortlist = [c for c in candidate_pool if c["id"] in shortlist_ids]

    triage_seconds = 0.0
    if triage_mode == "llm":
        triage_start = time.monotonic()
        shortlist, triage_errors = await llm_triage(llm, triage_model, job_text, shortlist, keep_n, max_concurrent)
        errors.extend(triage_errors)
        triage_seconds = time.monotonic() - triage_start

    async def _score_one(c: dict) -> dict | None:
        # Score against the LLM-generated summary, not the raw resume text —
        # see speed-plan lever "summary-based scoring": the summary is
        # already what the judge stage scores against (below), and scoring
        # against it too means deep_score sees a normalized, noise-free
        # input instead of a truncated raw-text blob (which silently drops
        # anything past 6000 chars and carries PDF/OCR formatting noise).
        # Falls back to raw text for a candidate with no summary yet (pre-
        # dates this feature, or summarization failed) rather than scoring
        # against nothing.
        summary = c.get("summary")
        scoring_text = summary or c["resume_text"]
        resume_label = SUMMARY_LABEL if summary else RESUME_TEXT_LABEL
        try:
            score_result = await deep_score(llm, scoring_model, job_text, scoring_text, c["profile"], resume_label)
        except Exception as exc:  # noqa: BLE001 - isolated to this one candidate, doesn't abort the batch
            errors.append(f"deep_score failed for candidate {c['id']}: {exc}")
            return None
        return {"candidate": c, "score_result": score_result}

    deep_score_start = time.monotonic()
    scored = [entry for entry in await bounded_gather(shortlist, _score_one, max_concurrent) if entry is not None]
    deep_score_seconds = time.monotonic() - deep_score_start

    def _needs_judgment(entry: dict) -> bool:
        score = float(entry["score_result"].get("score", 0))
        return JUDGE_REVIEW_LOW <= score <= JUDGE_REVIEW_HIGH

    borderline = [entry for entry in scored if _needs_judgment(entry)]

    async def _judge_one(entry: dict) -> dict | None:
        c, score_result = entry["candidate"], entry["score_result"]
        try:
            return await judge_score(llm, judge_model, job_text, c.get("summary", ""), score_result)
        except Exception as exc:  # noqa: BLE001 - isolated to this one candidate, doesn't abort the batch
            errors.append(f"judge failed for candidate {c['id']}: {exc}")
            return None

    judge_start = time.monotonic()
    judgments = await bounded_gather(borderline, _judge_one, max_concurrent)
    judge_seconds = time.monotonic() - judge_start
    judgments_by_candidate_id = {
        entry["candidate"]["id"]: judgment
        for entry, judgment in zip(borderline, judgments)
        if judgment is not None
    }

    results = []
    for entry in scored:
        c, score_result = entry["candidate"], entry["score_result"]
        score = float(score_result.get("score", 0))
        judge_notes = ""

        judgment = judgments_by_candidate_id.get(c["id"])
        if judgment is not None:
            judge_notes = judgment.get("judge_notes", "")
            if judgment.get("agrees") is False and judgment.get("corrected_score") is not None:
                score = float(judgment["corrected_score"])

        results.append(
            {
                "candidate_id": c["id"],
                "score": score,
                "matched": score_result.get("matched", []),
                "gaps": score_result.get("gaps", []),
                "missing_info": score_result.get("missing_info", []),
                "judge_notes": judge_notes,
            }
        )
    results.sort(key=lambda r: r["score"], reverse=True)
    # Unrounded — the caller may still be combining this with other timing
    # sources before display; round once, at the point it's finally shown.
    stage_timings = {"triage": triage_seconds, "deep_score": deep_score_seconds, "judge": judge_seconds}
    return results, stage_timings, errors
