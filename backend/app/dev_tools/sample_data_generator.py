#!/usr/bin/env python3
"""
Generates a large synthetic dataset for testing Recruit Assistant's scanning
and matching pipeline: thousands of "applications" and "follow-ups" spread
across a two-year date range, written in a dozen different personas, with a
deliberate slice of incomplete/garbled data.

Produces two things from one generation pass, so the same content can be
tested through either ingestion path (and their merge):

  sample_data/resumes/<date-bucket>/*.txt|.docx   — point Scan Sources'
      "Local folders" at sample_data/resumes with subfolders on.

  sample_data/emails_manifest.json                — read by
      MockEmailIngestor via load_fixtures_from_manifest() when
      MOCK_EMAIL_FIXTURES_PATH is set (see .env.example), so the Email
      Access / Scan Sources tabs work against this data with zero OAuth
      setup, through a seeded demo mailbox.

Usage:
    python scripts/generate_sample_data.py [--out sample_data] [--seed 42]
                                            [--initial 1600] [--followups 450]

Deterministic given the same --seed (default 42) — re-running regenerates
the identical dataset, which is what golden/regression testing wants.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

try:
    from docx import Document
except ImportError:  # pragma: no cover - docx is a project dependency already
    Document = None


# --------------------------------------------------------------------------
# Reference data pools
# --------------------------------------------------------------------------

FIRST_NAMES = [
    "Jordan", "Alex", "Sam", "Taylor", "Morgan", "Casey", "Jamie", "Riley",
    "Priya", "Wei", "Fatima", "Diego", "Aisha", "Hiro", "Elena", "Omar",
    "Grace", "Liam", "Noor", "Kwame", "Sofia", "Ravi", "Mei", "Carlos",
    "Ingrid", "Yusuf", "Anya", "Dmitri", "Chloe", "Kenji", "Layla", "Marcus",
    "Nadia", "Oscar", "Rin", "Sven", "Tara", "Viktor", "Wren", "Xiomara",
    "Amara", "Bilal", "Camila", "Dae", "Esperanza", "Femi", "Giulia", "Hana",
    "Ibrahim", "Junko", "Keiko", "Lars", "Mira", "Niko", "Olga", "Paulo",
    "Quinn", "Rosa", "Santiago", "Thandiwe", "Uma", "Valentina", "Wesley",
]

LAST_NAMES = [
    "Rivera", "Chen", "Patel", "Kim", "Garcia", "Nguyen", "Johnson", "Smith",
    "Kowalski", "Silva", "Mueller", "Andersson", "Rossi", "Dubois", "Yamamoto",
    "Okafor", "Haddad", "Petrov", "Larsen", "Nakamura", "Osei", "Ivanova",
    "Fernandez", "Kaur", "Wong", "Schmidt", "Costa", "Nilsson", "Abara",
    "Volkov", "Sato", "Mensah", "Torres", "Berg", "Alvarez", "Novak",
    "Hassan", "Lindqvist", "Moreau", "Tanaka", "Adeyemi", "Popescu",
]

DOMAINS: dict[str, list[str]] = {
    "backend": ["Python", "FastAPI", "Django", "PostgreSQL", "Redis", "Kubernetes",
                "Docker", "AWS", "microservices", "Go", "Java", "Spring Boot", "gRPC"],
    "frontend": ["JavaScript", "TypeScript", "React", "Vue", "CSS", "HTML",
                 "Tailwind", "Webpack", "Next.js", "accessibility", "GraphQL"],
    "data": ["Python", "SQL", "pandas", "Spark", "Airflow", "machine learning",
             "TensorFlow", "PyTorch", "data visualization", "ETL pipelines"],
    "product": ["product strategy", "roadmapping", "Agile", "user research",
                "stakeholder management", "SQL", "analytics", "Jira"],
    "design": ["Figma", "UI design", "UX research", "design systems",
               "prototyping", "Adobe Creative Suite", "wireframing"],
    "sales": ["Salesforce", "lead generation", "negotiation", "CRM",
              "account management", "cold outreach", "pipeline management"],
    "marketing": ["SEO", "content strategy", "Google Analytics",
                  "campaign management", "social media", "copywriting"],
    "ops_hr": ["recruiting", "onboarding", "HRIS", "payroll", "compliance",
               "employee relations", "benefits administration"],
    "finance": ["Excel", "financial modeling", "forecasting", "GAAP",
                "QuickBooks", "budgeting", "variance analysis"],
}

JOB_TITLES: dict[str, list[str]] = {
    "backend": ["Backend Engineer", "Platform Engineer", "Software Engineer"],
    "frontend": ["Frontend Engineer", "UI Engineer", "Web Developer"],
    "data": ["Data Engineer", "Data Scientist", "Analytics Engineer"],
    "product": ["Product Manager", "Associate Product Manager", "Product Owner"],
    "design": ["Product Designer", "UX Designer", "Visual Designer"],
    "sales": ["Account Executive", "Sales Development Rep", "Sales Manager"],
    "marketing": ["Marketing Manager", "Content Marketer", "Growth Marketer"],
    "ops_hr": ["HR Generalist", "Recruiting Coordinator", "People Ops Manager"],
    "finance": ["Financial Analyst", "Accountant", "FP&A Manager"],
}

COMPANIES = [
    "Acme Corp", "Widget Labs", "Northwind Software", "Globex", "Initech",
    "Vertex Systems", "Bluepeak", "Cascade Digital", "Ironleaf", "Nimbus Cloud",
    "Redwood Analytics", "Fathom AI", "Harbor Robotics", "Lumen Health",
    "Orbit Logistics", "Pinecrest Media", "Quartz Financial", "Sable Studio",
    "Tidewater Retail", "Vantage Point", "Anchorpoint", "Brightline",
    "Coastal Data", "Driftwood Games", "Everline", "Frontier Biotech",
]

SCHOOLS = [
    "State University", "Tech University", "Riverside College", "Metro Institute",
    "Highland University", "Coastal State", "Summit College", "Union Tech",
    "Lakeshore University", "Prairie State College", "Ashford Institute",
    "Grantham University", "Millbrook College", "Cedarwood University",
]

DEGREES = ["B.S.", "B.A.", "M.S.", "M.A.", "MBA", "B.Eng.", "Ph.D."]

CITIES = [
    "Austin, TX", "Denver, CO", "Chicago, IL", "Seattle, WA", "Atlanta, GA",
    "Raleigh, NC", "Phoenix, AZ", "Boston, MA", "Minneapolis, MN",
    "Portland, OR", "Nashville, TN", "San Diego, CA", "Columbus, OH",
    "Remote",
]

# Weighted so unknown/other stay a minority — matches WorkVisaStatus enum values.
VISA_WEIGHTS = [
    ("us_citizen", 42), ("green_card", 10), ("h1b", 15), ("opt", 8),
    ("stem_opt", 5), ("tn", 3), ("l1", 2), ("e3", 1), ("h4_ead", 2),
    ("other", 4), ("unknown", 8),
]
EMPLOYMENT_WEIGHTS = [
    ("actively_looking", 34), ("employed", 24), ("unemployed", 14),
    ("open_to_offers", 16), ("not_looking", 3), ("unknown", 9),
]

PERSONAS = [
    "formal_professional", "casual_friendly", "terse_minimal", "enthusiastic",
    "plainspoken_direct", "detail_oriented", "rambling", "blunt",
    "anxious_apologetic", "confident_salesy", "academic_formal", "minimalist_genz",
]


def weighted_choice(rng: random.Random, weights: list[tuple[str, int]]) -> str:
    total = sum(w for _, w in weights)
    r = rng.uniform(0, total)
    upto = 0.0
    for label, w in weights:
        upto += w
        if upto >= r:
            return label
    return weights[-1][0]


# --------------------------------------------------------------------------
# Candidate profile
# --------------------------------------------------------------------------


@dataclass
class Candidate:
    first_name: str
    last_name: str
    email: str
    phone: str
    domain: str
    job_title: str
    years_exp: int
    skills: list[str]
    company: str
    school: str
    degree: str
    city: str
    employment_status: str
    visa_status: str
    persona: str
    completeness: str  # "full" | "missing_contact" | "thin_garbled"
    submitted_at: datetime
    source: str  # "email" | "folder"


def make_candidate(rng: random.Random, submitted_at: datetime, source: str) -> Candidate:
    first = rng.choice(FIRST_NAMES)
    last = rng.choice(LAST_NAMES)
    domain = rng.choice(list(DOMAINS.keys()))
    completeness = rng.choices(
        ["full", "missing_contact", "thin_garbled"], weights=[70, 15, 15]
    )[0]

    email = f"{first.lower()}.{last.lower()}{rng.randint(1, 99)}@example.com"
    phone = f"({rng.randint(200,989)}) {rng.randint(200,989)}-{rng.randint(1000,9999)}"

    return Candidate(
        first_name=first,
        last_name=last,
        email=email,
        phone=phone,
        domain=domain,
        job_title=rng.choice(JOB_TITLES[domain]),
        years_exp=rng.randint(1, 14),
        skills=rng.sample(DOMAINS[domain], k=min(len(DOMAINS[domain]), rng.randint(3, 6))),
        company=rng.choice(COMPANIES),
        school=rng.choice(SCHOOLS),
        degree=rng.choice(DEGREES),
        city=rng.choice(CITIES),
        employment_status=weighted_choice(rng, EMPLOYMENT_WEIGHTS)
        if completeness != "thin_garbled" or rng.random() > 0.6
        else "unknown",
        visa_status=weighted_choice(rng, VISA_WEIGHTS)
        if completeness != "thin_garbled" or rng.random() > 0.6
        else "unknown",
        persona=rng.choice(PERSONAS),
        completeness=completeness,
        submitted_at=submitted_at,
        source=source,
    )


def make_upskilled_snapshot(rng: random.Random, original: Candidate, new_date: datetime, years_elapsed: float) -> Candidate:
    """A later resubmission from the same person — more experience, usually
    a skill or two picked up in the meantime. This is what "old candidates
    who upskilled over the years" looks like: same identity (name/email),
    later date_submitted, a fuller resume than whatever they sent originally."""
    domain_pool = DOMAINS[original.domain]
    available_new = [s for s in domain_pool if s not in original.skills]
    added = rng.sample(available_new, k=min(len(available_new), rng.randint(1, 2))) if available_new else []
    return dataclasses.replace(
        original,
        years_exp=min(30, round(original.years_exp + years_elapsed)),
        skills=[*original.skills, *added],
        submitted_at=new_date,
        completeness="full",  # a returning candidate sends a real, current resume
    )


# --------------------------------------------------------------------------
# Persona-flavored text rendering
# --------------------------------------------------------------------------

OPENERS = {
    "formal_professional": "I am writing to formally submit my application for the {title} position.",
    "casual_friendly": "Hi there! I'd love to be considered for the {title} role.",
    "terse_minimal": "Application: {title}.",
    "enthusiastic": "I am SO excited to apply for the {title} role — this is a dream opportunity!",
    "plainspoken_direct": "I'm applying for the {title} position.",
    "detail_oriented": "Please find below a comprehensive overview of my qualifications for the {title} role.",
    "rambling": "So I saw the {title} posting and, honestly, I've been thinking about making a move for a while now, and this really caught my eye for a bunch of reasons I'll get into.",
    "blunt": "Applying for {title}. Here's what I've got.",
    "anxious_apologetic": "I hope this isn't too forward, but I wanted to apply for the {title} role — I know my background may not be a perfect fit, but I'd really appreciate the chance.",
    "confident_salesy": "You're looking for a {title} who delivers results — that's exactly what I bring to the table.",
    "academic_formal": "Please accept this application for the position of {title}, submitted in accordance with the posted requirements.",
    "minimalist_genz": "hey! applying for {title}, resume below, lmk!",
}

CLOSERS = {
    "formal_professional": "Thank you for your time and consideration.",
    "casual_friendly": "Thanks so much for taking a look — hope to hear from you soon!",
    "terse_minimal": "Available immediately.",
    "enthusiastic": "Can't wait to hear back!!",
    "plainspoken_direct": "Let me know if you'd like to talk.",
    "detail_oriented": "I am happy to provide any additional documentation upon request.",
    "rambling": "Anyway, I could go on, but I'll let the resume speak for itself — thanks for reading this far!",
    "blunt": "Contact me if interested.",
    "anxious_apologetic": "Sorry again if this isn't quite the right fit — thank you for considering me regardless.",
    "confident_salesy": "Let's talk about how I can drive results for your team.",
    "academic_formal": "I welcome the opportunity to discuss my candidacy further.",
    "minimalist_genz": "thanks!!",
}

FOLLOWUP_TEMPLATES = {
    "formal_professional": "I am writing to follow up on my application for the {title} position submitted on {date}. I remain very interested in this opportunity.",
    "casual_friendly": "Just wanted to check in on my application from {date} for the {title} role — still super interested!",
    "terse_minimal": "Following up. Applied {date}. {title}.",
    "enthusiastic": "Checking in on my {title} application from {date} — still incredibly excited about this one!!",
    "plainspoken_direct": "Following up on my {title} application from {date}.",
    "detail_oriented": "I wanted to follow up regarding my application for {title}, submitted {date}, and confirm receipt of my materials.",
    "rambling": "Hey, so it's been a bit since I applied on {date} for the {title} role, and I know things get busy on your end, but I figured I'd just check in and see where things stand.",
    "blunt": "Following up. {title}. Applied {date}. Any update?",
    "anxious_apologetic": "Sorry to bother you — just wanted to gently follow up on my {title} application from {date}, no pressure at all.",
    "confident_salesy": "Circling back on my {title} application from {date} — still confident I'd be a great fit and would love to connect.",
    "academic_formal": "I write to follow up on my application of {date} for the position of {title}.",
    "minimalist_genz": "just following up on my app from {date} for {title}, no rush!",
}


def render_resume_body(c: Candidate) -> str:
    opener = OPENERS[c.persona].format(title=c.job_title)
    closer = CLOSERS[c.persona].format(title=c.job_title)

    name_line = f"{c.first_name} {c.last_name}" if c.completeness != "thin_garbled" else ""
    contact_bits = []
    if c.completeness == "full":
        contact_bits = [c.email, c.phone, c.city]
    elif c.completeness == "missing_contact":
        # Sometimes drop phone, sometimes drop the in-body email (sender
        # email on the message is still the source of truth for those).
        contact_bits = [c.email] if random.random() > 0.5 else [c.phone]
    # thin_garbled: no contact block in the body at all.

    lines = [name_line] if name_line else []
    lines += [" | ".join(contact_bits)] if contact_bits else []
    lines.append("")
    lines.append(opener)
    lines.append("")

    if c.completeness == "thin_garbled":
        # Simulates a bad OCR scan / copy-paste artifact / near-empty body —
        # exercises the parser's thin-extraction fallback path.
        garbled_snippets = [
            f"{c.job_title}... exp {c.years_exp}yr",
            f"see attached (scan quality poor) - {c.job_title}",
            f"{c.last_name} - {c.job_title} - resume attached",
        ]
        lines.append(random.choice(garbled_snippets))
        return "\n".join(lines).strip()

    lines.append(f"Summary: {c.years_exp} years of experience as a {c.job_title.lower()}, "
                 f"most recently at {c.company}.")
    lines.append("")
    lines.append(f"Skills: {', '.join(c.skills)}")
    lines.append("")
    lines.append(f"Experience: {c.job_title}, {c.company} — owned day-to-day delivery, "
                 f"collaborated cross-functionally, and shipped consistently.")
    lines.append("")
    lines.append(f"Education: {c.degree} , {c.school}")
    if c.completeness == "full":
        lines.append("")
        lines.append(f"Work authorization: {c.visa_status.replace('_', ' ').upper()}")
        lines.append(f"Status: {c.employment_status.replace('_', ' ')}")
        # Web presence — exercises the linkedin/github/portfolio extraction
        # (parser.py _regex_fallback) at realistic volume, not just on a
        # hand-written test resume. Most candidates have LinkedIn; GitHub
        # and a personal site are rarer, mirroring real resume mixes.
        handle = slugify(f"{c.first_name}{c.last_name}").replace("-", "")
        if random.random() < 0.7:
            lines.append(f"LinkedIn: linkedin.com/in/{handle}")
        if random.random() < 0.35:
            lines.append(f"GitHub: github.com/{handle}")
        if random.random() < 0.15:
            lines.append(f"Portfolio: {handle}.dev/work")
    lines.append("")
    lines.append(closer)
    return "\n".join(lines).strip()


def render_followup_body(c: Candidate, original_date: datetime) -> str:
    template = FOLLOWUP_TEMPLATES[c.persona]
    body = template.format(title=c.job_title, date=original_date.strftime("%B %d"))
    return f"{c.first_name} {c.last_name}\n{c.email}\n\n{body}\n\n— {c.first_name}"


# --------------------------------------------------------------------------
# Date distribution
# --------------------------------------------------------------------------

DATE_BUCKETS = [
    ("last_30_days", 0, 30, 0.28),
    ("1_3_months_ago", 30, 90, 0.18),
    ("3_6_months_ago", 90, 182, 0.14),
    ("6_12_months_ago", 182, 365, 0.10),
    ("1_2_years_ago", 365, 730, 0.10),
    ("2_4_years_ago", 730, 1460, 0.09),
    ("4_7_years_ago", 1460, 2555, 0.07),
    ("7_10_years_ago", 2555, 3650, 0.04),
]


def pick_bucket(rng: random.Random) -> tuple[str, int, int]:
    r = rng.random()
    cumulative = 0.0
    for name, lo, hi, weight in DATE_BUCKETS:
        cumulative += weight
        if r <= cumulative:
            return name, lo, hi
    return DATE_BUCKETS[-1][0], DATE_BUCKETS[-1][1], DATE_BUCKETS[-1][2]


def bucket_for_date(now: datetime, when: datetime) -> str:
    """Which DATE_BUCKETS folder an explicit (not randomly chosen) date falls
    into — used for upskill resubmissions, which pick their own date rather
    than a random bucket."""
    days_ago = max(0, (now - when).days)
    for name, lo, hi, _ in DATE_BUCKETS:
        if lo <= days_ago < hi:
            return name
    return DATE_BUCKETS[-1][0]


def random_date_in_bucket(rng: random.Random, now: datetime) -> tuple[str, datetime]:
    bucket, lo, hi = pick_bucket(rng)
    days_ago = rng.randint(lo, hi - 1)
    seconds_jitter = rng.randint(0, 86399)
    return bucket, now - timedelta(days=days_ago, seconds=-seconds_jitter)


# --------------------------------------------------------------------------
# File writing
# --------------------------------------------------------------------------


def slugify(text: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in text.lower()).strip("-")


def write_txt(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def write_docx(path: Path, body: str) -> None:
    if Document is None:
        write_txt(path.with_suffix(".txt"), body)
        return
    doc = Document()
    for line in body.split("\n"):
        doc.add_paragraph(line)
    doc.save(path)


def set_mtime(path: Path, when: datetime) -> None:
    ts = when.timestamp()
    import os

    os.utime(path, (ts, ts))


# --------------------------------------------------------------------------
# Main generation
# --------------------------------------------------------------------------


@dataclass
class ManifestEntry:
    id: str
    kind: str  # "application" | "followup"
    from_name: str
    from_email: str
    subject: str
    date: str
    attachment_file: str
    persona: str
    completeness: str
    thread_of: str | None = None


def generate(
    out_dir: Path, seed: int, initial_count: int, followup_count: int, upskill_count: int = 0
) -> dict:
    rng = random.Random(seed)
    random.seed(seed)  # render_* helpers use the module-level `random` for brevity
    now = datetime.now()

    resumes_dir = out_dir / "resumes"
    attachments_dir = out_dir / "attachments"  # flat copy for the email manifest path
    resumes_dir.mkdir(parents=True, exist_ok=True)
    attachments_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[ManifestEntry] = []
    applications: list[tuple[Candidate, str]] = []  # (candidate, item_id)

    print(f"Generating {initial_count} initial applications...")
    for i in range(initial_count):
        bucket, submitted_at = random_date_in_bucket(rng, now)
        source = "email" if rng.random() < 0.65 else "folder"
        c = make_candidate(rng, submitted_at, source)
        body = render_resume_body(c)

        item_id = f"app-{i:05d}-{slugify(c.first_name + c.last_name)}"
        use_docx = rng.random() < 0.3 and Document is not None
        ext = "docx" if use_docx else "txt"
        filename = f"{item_id}.{ext}"

        bucket_dir = resumes_dir / bucket
        bucket_dir.mkdir(parents=True, exist_ok=True)
        bucket_path = bucket_dir / filename
        flat_path = attachments_dir / filename

        if use_docx:
            write_docx(bucket_path, body)
            write_docx(flat_path, body)
        else:
            write_txt(bucket_path, body)
            write_txt(flat_path, body)
        set_mtime(bucket_path, submitted_at)
        set_mtime(flat_path, submitted_at)

        manifest.append(
            ManifestEntry(
                id=item_id,
                kind="application",
                from_name=f"{c.first_name} {c.last_name}",
                from_email=c.email,
                subject=f"Application: {c.job_title}",
                date=submitted_at.isoformat(),
                attachment_file=filename,
                persona=c.persona,
                completeness=c.completeness,
            )
        )
        applications.append((c, item_id))

    print(f"Generating {followup_count} follow-ups...")
    # Most follow-ups reference a real prior application (identity-merge
    # test); a minority are standalone check-ins from someone not otherwise
    # in the dataset (noise / edge case).
    linked_count = int(followup_count * 0.85)
    standalone_count = followup_count - linked_count

    linked_sample = rng.sample(applications, k=min(linked_count, len(applications)))
    for i, (orig_c, orig_id) in enumerate(linked_sample):
        max_gap = max(1, (now - orig_c.submitted_at).days - 1)
        gap_days = rng.randint(1, min(30, max_gap)) if max_gap > 1 else 1
        followup_at = orig_c.submitted_at + timedelta(days=gap_days)
        if followup_at > now:
            followup_at = now

        body = render_followup_body(orig_c, orig_c.submitted_at)
        item_id = f"followup-{i:05d}-{slugify(orig_c.first_name + orig_c.last_name)}"
        filename = f"{item_id}.txt"
        bucket = "last_30_days" if (now - followup_at).days <= 30 else "1_3_months_ago"
        bucket_dir = resumes_dir / bucket
        bucket_dir.mkdir(parents=True, exist_ok=True)
        bucket_path = bucket_dir / filename
        flat_path = attachments_dir / filename
        write_txt(bucket_path, body)
        write_txt(flat_path, body)
        set_mtime(bucket_path, followup_at)
        set_mtime(flat_path, followup_at)

        manifest.append(
            ManifestEntry(
                id=item_id,
                kind="followup",
                from_name=f"{orig_c.first_name} {orig_c.last_name}",
                from_email=orig_c.email,
                subject=f"Following up: {orig_c.job_title}",
                date=followup_at.isoformat(),
                attachment_file=filename,
                persona=orig_c.persona,
                completeness="thin_garbled",  # follow-ups are intentionally sparse
                thread_of=orig_id,
            )
        )

    for i in range(standalone_count):
        bucket, submitted_at = random_date_in_bucket(rng, now)
        c = make_candidate(rng, submitted_at, "email")
        body = render_followup_body(c, submitted_at - timedelta(days=rng.randint(5, 20)))
        item_id = f"followup-standalone-{i:05d}-{slugify(c.first_name + c.last_name)}"
        filename = f"{item_id}.txt"
        bucket_dir = resumes_dir / bucket
        bucket_dir.mkdir(parents=True, exist_ok=True)
        bucket_path = bucket_dir / filename
        flat_path = attachments_dir / filename
        write_txt(bucket_path, body)
        write_txt(flat_path, body)
        set_mtime(bucket_path, submitted_at)
        set_mtime(flat_path, submitted_at)

        manifest.append(
            ManifestEntry(
                id=item_id,
                kind="followup",
                from_name=f"{c.first_name} {c.last_name}",
                from_email=c.email,
                subject=f"Checking in: {c.job_title}",
                date=submitted_at.isoformat(),
                attachment_file=filename,
                persona=c.persona,
                completeness="thin_garbled",
            )
        )

    upskill_journey_candidates = [
        (c, cid) for c, cid in rng.sample(applications, k=min(upskill_count, len(applications)))
        if (now - c.submitted_at).days / 365.25 >= 0.5
    ]
    upskill_items = 0
    if upskill_journey_candidates:
        print(f"Generating upskill journeys for {len(upskill_journey_candidates)} returning candidates...")
    for orig_c, orig_id in upskill_journey_candidates:
        cursor, cursor_date = orig_c, orig_c.submitted_at
        for _ in range(rng.randint(1, 3)):
            remaining_years = (now - cursor_date).days / 365.25
            if remaining_years < 0.3:
                break
            gap_years = rng.uniform(0.5, min(3.0, remaining_years))
            new_date = cursor_date + timedelta(days=int(gap_years * 365.25))
            if new_date > now:
                new_date = now

            snapshot = make_upskilled_snapshot(rng, cursor, new_date, gap_years)
            body = render_resume_body(snapshot)
            item_id = f"upskill-{upskill_items:05d}-{slugify(orig_c.first_name + orig_c.last_name)}"
            upskill_items += 1
            filename = f"{item_id}.txt"
            bucket = bucket_for_date(now, new_date)
            bucket_dir = resumes_dir / bucket
            bucket_dir.mkdir(parents=True, exist_ok=True)
            bucket_path = bucket_dir / filename
            flat_path = attachments_dir / filename
            write_txt(bucket_path, body)
            write_txt(flat_path, body)
            set_mtime(bucket_path, new_date)
            set_mtime(flat_path, new_date)

            manifest.append(
                ManifestEntry(
                    id=item_id,
                    kind="application",  # a real updated resume, not a sparse check-in
                    from_name=f"{snapshot.first_name} {snapshot.last_name}",
                    from_email=snapshot.email,
                    subject=f"Updated application: {snapshot.job_title}",
                    date=new_date.isoformat(),
                    attachment_file=filename,
                    persona=snapshot.persona,
                    completeness="full",
                    thread_of=orig_id,
                )
            )
            cursor, cursor_date = snapshot, new_date

    manifest_path = out_dir / "emails_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "generated_at": now.isoformat(),
                "seed": seed,
                "attachments_dir": "attachments",
                "count": len(manifest),
                "emails": [entry.__dict__ for entry in manifest],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    readme = out_dir / "README.md"
    readme.write_text(
        f"""# Sample Dataset

Generated {now.strftime("%Y-%m-%d %H:%M")} with seed {seed} — {len(manifest)} total items
({initial_count} initial applications + {followup_count} short follow-ups + {upskill_items}
"upskill" resubmissions from {len(upskill_journey_candidates)} returning candidates), spread
across the last **10 years**, in 12 writing personas, ~30% with missing/thin data on purpose.

Upskill resubmissions are the same person (same email) applying again years later with more
experience and new skills — exercises the app's candidate-history timeline
(`Candidate.history`), not just identity merging.

## Use it via folder scanning (works right now, no setup)

Scan Sources tab -> Local folders -> add `{resumes_dir.resolve()}`, include subfolders, Scan.
File dates (mtime) are set to match each item's synthetic submission date, so the
date-range picker on Scan Sources / Candidate Results / Search History all work against it.

## Use it via mock email scanning

Set `MOCK_EMAIL_FIXTURES_PATH={manifest_path.resolve()}` in `.env` (with `USE_MOCK=true`),
restart the backend. A demo mailbox is auto-seeded — go to Email Access, you'll see it
connected, then scan it from Scan Sources like a real mailbox.

Scanning both paths against the same people is a good test of cross-source identity
merging: `85%` of follow-ups reference a real prior application by the same email address.

## What's deliberately imperfect

- ~15% missing phone or in-body email (relies on sender email only)
- ~15% "thin_garbled" — very short/fragmented body, exercises the parser's fallback path
- All follow-ups are intentionally sparse (that's what a real follow-up looks like)
- Visa/employment status is "unknown" more often on thin/garbled items

## Note on USE_MOCK=true

With `USE_MOCK=true`, `MockLLMClient` does a lightweight regex-based read of each resume
(name, email, phone, skills-by-keyword, "Work authorization:"/"Status:" lines, years of
experience) rather than a fixed canned profile — so this dataset's variety actually shows
up in the dashboard/results without needing a real LLM key. It's not as accurate as a real
model (no semantic understanding), but it's real per-item extraction, not one identity
repeated 2,000 times. Match *scores* are still a fixed placeholder in mock mode — set
`USE_MOCK=false` with an OpenRouter/OpenAI key to see real, differentiated scoring.
""",
        encoding="utf-8",
    )

    summary = {
        "total_items": len(manifest),
        "initial_applications": initial_count,
        "followups": followup_count,
        "upskill_resubmissions": upskill_items,
        "upskill_journey_candidates": len(upskill_journey_candidates),
        "resumes_dir": str(resumes_dir.resolve()),
        "manifest_path": str(manifest_path.resolve()),
    }
    print(f"Done. {len(manifest)} items written to {out_dir}/")
    print(f"  resumes/       — folder-scan tree, {len(list(resumes_dir.rglob('*.*')))} files")
    print(f"  attachments/   — flat copy for the email manifest")
    print(f"  emails_manifest.json")
    print(f"  README.md")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="sample_data", help="Output directory (default: sample_data)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--initial", type=int, default=7000, help="Number of initial applications")
    parser.add_argument("--followups", type=int, default=2200, help="Number of short follow-up emails")
    parser.add_argument(
        "--upskill", type=int, default=1400, help="Number of candidates who get multi-year upskill resubmissions"
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    generate(out_dir, args.seed, args.initial, args.followups, args.upskill)


if __name__ == "__main__":
    main()
