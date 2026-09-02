"""
Resume parsing: deterministic text extraction first (pypdf/pdfplumber/docx),
LLM structured-extraction fallback when extraction is thin or garbled (scanned
PDFs, unusual formatting). Output is always a CandidateProfile — this is what
both matching and the "missing info" flag (2.5) key off of.
"""

import asyncio
import io
import re

import docx
import pdfplumber
from pypdf import PdfReader

from app.logging import get_logger
from app.matching.llm_client import LLMClient
from app.models.enums import EmploymentStatus, WorkVisaStatus
from app.models.schemas import CandidateProfile

logger = get_logger(__name__)

MIN_VIABLE_TEXT_LENGTH = 200

EXTRACTION_PROMPT = """Extract structured candidate info from this resume text.
Return JSON with keys: legal_first_name, legal_middle_name, legal_last_name,
email, phone, employment_status (one of {statuses}), work_visa_status
(one of {visas}), skills (list of strings), experience_years (number),
education (list of strings). If a field is unknown, use "" or 0 or [] as
appropriate — do not guess.

Resume text:
---
{text}
---
"""


def extract_text(file_bytes: bytes, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    try:
        if ext == "pdf":
            return _extract_pdf_text(file_bytes)
        if ext == "docx":
            return _extract_docx_text(file_bytes)
        if ext == "txt":
            return file_bytes.decode("utf-8", errors="ignore")
    except Exception:
        return ""
    return ""


def _extract_pdf_text(file_bytes: bytes) -> str:
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception:
        text = ""
    if len(text.strip()) < MIN_VIABLE_TEXT_LENGTH:
        reader = PdfReader(io.BytesIO(file_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if len(text.strip()) < MIN_VIABLE_TEXT_LENGTH:
        text = _ocr_pdf_text(file_bytes)
    return text


def _ocr_pdf_text(file_bytes: bytes) -> str:
    """Last-resort fallback when pdfplumber/pypdf both come back thin — the
    signature of a scanned/image PDF with no embedded text layer, which
    otherwise produces an almost-empty candidate profile. Needs the
    `tesseract` OCR engine and `poppler` (pdf2image's PDF rasterizer)
    installed as system binaries — see architecture/getting-started.md.
    Neither is a hard Python dependency (`pip install ".[ocr]"` pulls the
    Python side only); if the binaries aren't present this logs and returns
    "", so ingest continues exactly as it did before OCR existed rather than
    failing the whole resume over one missing optional feature."""
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
    except ImportError:
        logger.warning("ocr_fallback_unavailable", reason="pytesseract/pdf2image not installed")
        return ""
    try:
        images = convert_from_bytes(file_bytes)
        return "\n".join(pytesseract.image_to_string(image) for image in images)
    except Exception as exc:  # noqa: BLE001 - OCR is best-effort, never fatal to ingest
        logger.warning("ocr_fallback_failed", error=str(exc))
        return ""


def _extract_docx_text(file_bytes: bytes) -> str:
    d = docx.Document(io.BytesIO(file_bytes))
    return "\n".join(p.text for p in d.paragraphs)


LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-%]+/?", re.IGNORECASE)
GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[\w\-]+/?", re.IGNORECASE)
PORTFOLIO_RE = re.compile(
    r"(?:https?://)?(?:www\.)?[\w\-]+\.(?:dev|me|io|com|design|xyz|art)/[\w\-/.]*", re.IGNORECASE
)


def _regex_fallback(text: str) -> dict:
    """Cheap deterministic signals used to seed / cross-check the LLM extraction.
    URLs are always regex-extracted (never LLM-guessed) — they're cheap and
    reliable to pattern-match directly out of resume text."""
    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    phone_match = re.search(r"(\+?\d[\d\-\s().]{8,}\d)", text)
    linkedin_match = LINKEDIN_RE.search(text)
    github_match = GITHUB_RE.search(text)
    portfolio_match = None
    for m in PORTFOLIO_RE.finditer(text):
        candidate = m.group(0)
        if "linkedin.com" in candidate.lower() or "github.com" in candidate.lower():
            continue
        portfolio_match = candidate
        break
    return {
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0) if phone_match else "",
        "linkedin_url": linkedin_match.group(0) if linkedin_match else "",
        "github_url": github_match.group(0) if github_match else "",
        "portfolio_url": portfolio_match or "",
    }


async def parse_resume(file_bytes: bytes, filename: str, llm: LLMClient) -> CandidateProfile:
    # extract_text is synchronous CPU/disk-bound work (pdfplumber, pypdf,
    # python-docx, and worst-case a Tesseract OCR subprocess call) — run on
    # a worker thread so it doesn't block the event loop while it runs, and
    # so multiple resumes' extraction can genuinely overlap when ingest
    # processes them concurrently (see run_scan's batched processing).
    text = await asyncio.to_thread(extract_text, file_bytes, filename)
    regex_hints = _regex_fallback(text)

    if len(text.strip()) < MIN_VIABLE_TEXT_LENGTH:
        # Thin/garbled extraction (e.g. scanned PDF) — nothing reliable to send.
        profile = CandidateProfile(raw_text=text)
        profile.email = regex_hints["email"]
        profile.phone = regex_hints["phone"]
        profile.linkedin_url = regex_hints["linkedin_url"]
        profile.github_url = regex_hints["github_url"]
        profile.portfolio_url = regex_hints["portfolio_url"]
        return profile

    prompt = EXTRACTION_PROMPT.format(
        statuses=[s.value for s in EmploymentStatus],
        visas=[v.value for v in WorkVisaStatus],
        text=text[:12000],
    )
    extracted = await llm.extract_json(prompt)

    profile = CandidateProfile(
        legal_first_name=extracted.get("legal_first_name", ""),
        legal_middle_name=extracted.get("legal_middle_name", ""),
        legal_last_name=extracted.get("legal_last_name", ""),
        email=extracted.get("email") or regex_hints["email"],
        phone=extracted.get("phone") or regex_hints["phone"],
        employment_status=_safe_enum(EmploymentStatus, extracted.get("employment_status")),
        work_visa_status=_safe_enum(WorkVisaStatus, extracted.get("work_visa_status")),
        skills=extracted.get("skills", []) or [],
        experience_years=float(extracted.get("experience_years") or 0),
        education=extracted.get("education", []) or [],
        raw_text=text,
        linkedin_url=regex_hints["linkedin_url"],
        github_url=regex_hints["github_url"],
        portfolio_url=regex_hints["portfolio_url"],
    )
    return profile


def _safe_enum(enum_cls, value):
    try:
        return enum_cls(value)
    except Exception:
        return enum_cls.UNKNOWN
