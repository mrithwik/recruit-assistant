"""
LLMClient — thin abstraction over OpenRouter (primary) with OpenAI as a direct
fallback provider, plus a MockLLMClient for USE_MOCK_LLM=true / golden tests.

Kept intentionally small: one method to get a chat completion, one to get a
JSON object back (used by the resume parser and matcher), one for embeddings.
Swapping/adding a provider (e.g. Anthropic direct) means one new adapter, not
changes to every call site.
"""

import asyncio
import json
import re
from abc import ABC, abstractmethod

import httpx

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"


async def _post_with_retry(
    client: httpx.AsyncClient, path: str, json_body: dict, max_attempts: int = 6
) -> httpx.Response:
    """429/5xx retry with exponential backoff — mirrors
    scanning/email_ingestor.py's get_with_retry (same reasoning, applied to
    the scoring/embedding calls instead of the mailbox-fetch ones): a real
    matching or ingest run makes many concurrent LLM calls (see
    max_concurrent_llm_calls), so an occasional rate-limit or transient
    server error is expected, not exceptional — without this, a single
    429/5xx failed a whole deep-score/judge/embed call outright (and, for
    OpenRouterClient, immediately fell through to the fallback provider
    rather than just retrying the primary one first). A non-retryable
    error (any other 4xx) still raises immediately, and the final attempt
    always raises rather than retrying forever."""
    backoff = 1.0
    for attempt in range(max_attempts):
        resp = await client.post(path, json=json_body)
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == max_attempts - 1:
                resp.raise_for_status()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
            continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()
    return resp


class LLMClient(ABC):
    @abstractmethod
    async def complete(self, model: str, prompt: str, system: str = "") -> str: ...

    @abstractmethod
    async def embed(self, model: str, text: str) -> list[float]: ...

    async def extract_json(self, prompt: str, model: str = "") -> dict:
        raw = await self.complete(model or "", prompt, system="Respond with ONLY valid JSON, no prose.")
        return _safe_json_loads(raw)


class OpenRouterClient(LLMClient):
    """Primary provider. Falls back to OpenAIClient on failure if configured."""

    def __init__(self, api_key: str, fallback: "LLMClient | None" = None, default_model: str = ""):
        self.api_key = api_key
        self.fallback = fallback
        self.default_model = default_model
        self._client = httpx.AsyncClient(
            base_url=OPENROUTER_BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60.0,
        )

    async def complete(self, model: str, prompt: str, system: str = "") -> str:
        try:
            messages = ([{"role": "system", "content": system}] if system else []) + [
                {"role": "user", "content": prompt}
            ]
            resp = await _post_with_retry(
                self._client,
                "/chat/completions",
                {"model": model or self.default_model, "messages": messages},
            )
            return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            if self.fallback:
                return await self.fallback.complete(model, prompt, system)
            raise

    async def embed(self, model: str, text: str) -> list[float]:
        try:
            resp = await _post_with_retry(self._client, "/embeddings", {"model": model, "input": text})
            return resp.json()["data"][0]["embedding"]
        except Exception:
            if self.fallback:
                return await self.fallback.embed(model, text)
            raise


class OpenAIClient(LLMClient):
    """Direct OpenAI provider, used as fallback (or primary if the user prefers)."""

    def __init__(self, api_key: str, default_model: str = "gpt-4.1-mini"):
        self.default_model = default_model
        self._client = httpx.AsyncClient(
            base_url=OPENAI_BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60.0,
        )

    async def complete(self, model: str, prompt: str, system: str = "") -> str:
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        model = model.split("/")[-1] if model else self.default_model
        resp = await _post_with_retry(self._client, "/chat/completions", {"model": model, "messages": messages})
        return resp.json()["choices"][0]["message"]["content"]

    async def embed(self, model: str, text: str) -> list[float]:
        model = model.split("/")[-1] if model else "text-embedding-3-small"
        resp = await _post_with_retry(self._client, "/embeddings", {"model": model, "input": text})
        return resp.json()["data"][0]["embedding"]


_SKILL_VOCAB = [
    "python", "fastapi", "django", "postgresql", "redis", "kubernetes", "docker",
    "aws", "microservices", "go", "java", "spring boot", "grpc",
    "javascript", "typescript", "react", "vue", "css", "html", "tailwind",
    "webpack", "next.js", "accessibility", "graphql",
    "sql", "pandas", "spark", "airflow", "machine learning", "tensorflow",
    "pytorch", "data visualization", "etl",
    "product strategy", "roadmapping", "agile", "user research",
    "stakeholder management", "jira",
    "figma", "ui design", "ux research", "design systems", "prototyping",
    "adobe creative suite", "wireframing",
    "salesforce", "lead generation", "negotiation", "crm",
    "account management", "cold outreach", "pipeline management",
    "seo", "content strategy", "google analytics", "campaign management",
    "social media", "copywriting",
    "recruiting", "onboarding", "hris", "payroll", "compliance",
    "employee relations", "benefits administration",
    "excel", "financial modeling", "forecasting", "gaap", "quickbooks",
    "budgeting", "variance analysis",
]


def _mock_extract_profile(prompt: str) -> dict:
    """Lightweight regex-based 'reading' of the resume text embedded in the
    extraction prompt — not a real LLM, but reads the actual input instead of
    returning one canned profile for every resume. Matters at volume: a
    generated dataset of thousands of varied resumes should show up as
    varied candidates even with USE_MOCK_LLM=true and no API key."""
    marker = "Resume text:\n---\n"
    text = prompt.split(marker, 1)[1] if marker in prompt else prompt

    first_name, last_name = "", ""
    for line in text.strip().splitlines()[:3]:
        words = line.strip().split()
        if 2 <= len(words) <= 4 and all(w[:1].isupper() and w.replace("-", "").isalpha() for w in words):
            first_name, last_name = words[0], words[-1]
            break

    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    phone_match = re.search(r"(\+?\d[\d\-\s().]{8,}\d)", text)

    from app.scanning.parser import _regex_fallback

    link_hints = _regex_fallback(text)

    # Word-boundary match, not plain substring — "go" must not match inside
    # "Google" or "negotiation", "css" must not match inside a longer token.
    text_lower = text.lower()
    skills = [kw for kw in _SKILL_VOCAB if re.search(rf"\b{re.escape(kw)}\b", text_lower)]

    visa_match = re.search(r"work authorization:\s*(.+)", text, re.IGNORECASE)
    work_visa_status = visa_match.group(1).strip().lower().replace(" ", "_") if visa_match else "unknown"

    status_match = re.search(r"^status:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    employment_status = status_match.group(1).strip().lower().replace(" ", "_") if status_match else "unknown"

    years_match = re.search(r"(\d+)\s*years?", text, re.IGNORECASE)
    experience_years = int(years_match.group(1)) if years_match else 0

    education_match = re.search(r"education:\s*(.+)", text, re.IGNORECASE)
    education = [education_match.group(1).strip()] if education_match else []

    return {
        "legal_first_name": first_name,
        "legal_middle_name": "",
        "legal_last_name": last_name,
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0) if phone_match else "",
        "employment_status": employment_status,
        "work_visa_status": work_visa_status,
        "skills": skills,
        "experience_years": experience_years,
        "education": education,
        "linkedin_url": link_hints["linkedin_url"],
        "github_url": link_hints["github_url"],
        "portfolio_url": link_hints["portfolio_url"],
    }


def _mock_score_match(prompt: str) -> dict:
    """Regex-based scoring that actually reads the job text and candidate
    profile embedded in SCORING_PROMPT (see matching/prompts.py), instead of
    returning one fixed score/reasons for every candidate — the same class
    of bug as the earlier canned-extraction fix, this time in the scorer:
    every match was showing an identical 72 and identical reasons regardless
    of who was being scored."""
    job_text = ""
    if "Job Description:\n---\n" in prompt:
        job_text = prompt.split("Job Description:\n---\n", 1)[1].split("\n---\n", 1)[0]

    skills_line = re.search(r"- Skills:\s*(.*)", prompt)
    candidate_skills = (
        {s.strip().lower() for s in skills_line.group(1).split(",") if s.strip()} if skills_line else set()
    )

    exp_match = re.search(r"- Experience:\s*([\d.]+)\s*years", prompt)
    experience_years = float(exp_match.group(1)) if exp_match else 0.0

    visa_match = re.search(r"- Work authorization:\s*(\S+)", prompt)
    work_visa_status = visa_match.group(1) if visa_match else "unknown"

    job_lower = job_text.lower()
    job_skills = {kw for kw in _SKILL_VOCAB if re.search(rf"\b{re.escape(kw)}\b", job_lower)}

    overlap = job_skills & candidate_skills
    missing_skills = job_skills - candidate_skills

    skill_ratio = len(overlap) / len(job_skills) if job_skills else 0.5
    experience_bonus = min(experience_years, 10) * 1.5
    score = max(5.0, min(98.0, 25 + skill_ratio * 55 + experience_bonus))

    matched = [f"has required skill: {s}" for s in sorted(overlap)] or (
        ["general experience overlaps the role"] if score >= 40 else []
    )
    gaps = [f"missing skill: {s}" for s in sorted(missing_skills)] or (
        [] if job_skills else ["job description has no clearly listed required skills to compare against"]
    )
    missing_info = []
    if work_visa_status == "unknown":
        missing_info.append("work authorization / visa status not stated")
    if experience_years == 0:
        missing_info.append("years of experience not stated")

    return {
        "score": round(score, 1),
        "matched": matched,
        "gaps": gaps,
        "missing_info": missing_info,
    }


class MockLLMClient(LLMClient):
    """Deterministic canned responses — powers USE_MOCK_LLM=true and the golden
    test harness, so the full pipeline is exercisable with zero API keys."""

    async def complete(self, model: str, prompt: str, system: str = "") -> str:
        if "JSON" in system:
            if "legal_first_name" in prompt:
                return json.dumps(_mock_extract_profile(prompt))
            if "Critique this score" in prompt:
                # Mock judge defers to the initial (already-varied) score
                # rather than overriding it with another canned number.
                return json.dumps(
                    {
                        "agrees": True,
                        "corrected_score": None,
                        "judge_notes": "Mock judge: initial score looks consistent with the stated evidence.",
                    }
                )
            return json.dumps(_mock_score_match(prompt))
        return "Mock candidate with relevant experience for the given role."

    async def embed(self, model: str, text: str) -> list[float]:
        # Deterministic pseudo-embedding from a hash — good enough for offline
        # dev/tests where we only need consistent relative similarity, not
        # semantic accuracy.
        import hashlib

        h = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in h[:32]]


def _safe_json_loads(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.removeprefix("json")
    try:
        return json.loads(raw)
    except Exception:
        return {}


class DispatcherLLMClient(LLMClient):
    """Wraps a MockLLMClient and (if API keys are configured) a real client,
    routing every call to whichever one app.runtime_settings.get_use_mock_llm()
    says to use *at call time* — this is what lets the UI toggle mock/real
    without restarting the backend, instead of the choice being baked in
    once at startup. Falls back to mock if real mode is requested but no
    provider was ever configured, rather than raising mid-scan (routes/
    mock_mode.py's PATCH endpoint is where that gets rejected up front)."""

    def __init__(self, mock_client: LLMClient, real_client: LLMClient | None):
        self.mock_client = mock_client
        self.real_client = real_client

    def _active(self) -> LLMClient:
        from app.runtime_settings import get_use_mock_llm

        if get_use_mock_llm() or self.real_client is None:
            return self.mock_client
        return self.real_client

    async def complete(self, model: str, prompt: str, system: str = "") -> str:
        return await self._active().complete(model, prompt, system)

    async def embed(self, model: str, text: str) -> list[float]:
        return await self._active().embed(model, text)


def build_real_llm_client(openrouter_key: str, openai_key: str) -> LLMClient | None:
    fallback = OpenAIClient(openai_key) if openai_key else None
    if openrouter_key:
        return OpenRouterClient(openrouter_key, fallback=fallback)
    return fallback


def build_llm_client(openrouter_key: str, openai_key: str) -> LLMClient:
    """Always returns a DispatcherLLMClient so mock/real can be toggled live
    at runtime — see DispatcherLLMClient. Works even with no API keys
    configured (real mode just stays unavailable until keys are added; the
    PATCH /api/v1/settings/mock-mode route refuses to enable real LLM mode
    in that case rather than letting it fail confusingly mid-scan)."""
    return DispatcherLLMClient(mock_client=MockLLMClient(), real_client=build_real_llm_client(openrouter_key, openai_key))
