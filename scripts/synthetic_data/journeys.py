"""Turns a single Persona into a realistic multi-email relationship: the
initial application, optional follow-ups, an optional resume-update
resubmission (new skill/cert — exercises the app's resubmission/dedup path),
optional long-gap relationship-maintenance check-ins, and — for ~10% of
personas — a genuine back-and-forth thread (recruiter asks something,
candidate replies in character, recruiter sends good/bad news or advice,
candidate optionally reacts again). Timing is drawn from the same 10-year
DATE_BUCKETS weighting the folder/mock-email generator already uses; a
"current opening" follow-up gets a short gap, a relationship-maintenance
check-in gets a long one, matching what was asked for.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from .documents import render_cover_letter_pdf, render_resume_pdf, render_resume_pdf_image_only
from .personas import CERTS, Persona

TONE = {
    "patient": {
        "openers": ["No rush at all — just following up when you have a moment.", "Whenever it's convenient, I wanted to check in."],
        "closers": ["Take your time, I appreciate it.", "No pressure either way — thanks for considering me."],
    },
    "laid_back": {
        "openers": ["Hey, just wanted to touch base whenever.", "No big deal, just circling back."],
        "closers": ["Whenever works for you!", "All good either way, just wanted to check."],
    },
    "neutral": {
        "openers": ["I wanted to follow up on my application.", "Checking in on the status of my application."],
        "closers": ["Thank you for your time.", "Looking forward to hearing from you."],
    },
    "anxious": {
        "openers": ["I hope this isn't a bad time to ask, but I wanted to check in.", "Sorry to bother you again — I just wanted to make sure my application went through okay."],
        "closers": ["Sorry again for the extra email — I really appreciate any update.", "Thank you so much, and apologies if this is too soon to ask."],
    },
    "worried": {
        "openers": ["I've been a bit worried I might have missed something on my end — wanted to check in.", "I wanted to make sure everything on my application was complete."],
        "closers": ["I hope I haven't done anything wrong on my end.", "Please let me know if there's anything else you need from me."],
    },
    "tense": {
        "openers": ["I'll be honest, the waiting has been stressful — any update would help.", "I wanted to check in, this process has been a bit nerve-wracking."],
        "closers": ["I'd really appreciate some clarity soon.", "Hoping to hear something either way."],
    },
    "micromanaging": {
        "openers": ["Circling back — could you give me a specific date by which this will be resolved?", "Following up with a request for a concrete status update and next steps."],
        "closers": ["Please confirm receipt of this email.", "Could you let me know the exact timeline going forward?"],
    },
    "pushy": {
        "openers": ["Following up again — I'd like an answer soon.", "This is my second note on this — wanted to make sure it didn't get lost."],
        "closers": ["Looking forward to your prompt reply.", "Hoping to hear back soon rather than later."],
    },
    "demanding": {
        "openers": ["I'd appreciate a response within the next day or two.", "This delay is a bit frustrating — I need some clarity."],
        "closers": ["I trust this will be handled promptly.", "Please treat this as time-sensitive."],
    },
}


@dataclass
class EmailEvent:
    persona_idx: int
    direction: str  # "candidate_to_recruiter" | "recruiter_to_candidate"
    kind: str
    timestamp: datetime
    subject: str
    body: str
    attachments: list[Path] = field(default_factory=list)


def _tone(p: Persona) -> dict:
    return TONE[p.challenge_persona]


def _initial_application(p: Persona, work_dir: Path, rng: random.Random) -> EmailEvent:
    slug = f"{p.idx:06d}_{p.first_name}_{p.last_name}".lower()
    resume_path = work_dir / f"{slug}_resume.pdf"
    if p.ocr_image_resume:
        render_resume_pdf_image_only(p, resume_path)
    else:
        render_resume_pdf(p, resume_path)
    attachments = [resume_path]
    if p.include_cover_letter:
        cl_path = work_dir / f"{slug}_cover_letter.pdf"
        render_cover_letter_pdf(p, cl_path)
        attachments.append(cl_path)

    body = (
        f"Hi,\n\nPlease find my resume attached for the {p.title} position.\n\n"
        f"Best,\n{p.first_name} {p.last_name}\n{p.phone}"
    )
    return EmailEvent(
        persona_idx=p.idx,
        direction="candidate_to_recruiter",
        kind="initial_application",
        timestamp=p.submitted_at,
        subject=f"Application for {p.title} — {p.first_name} {p.last_name}",
        body=body,
        attachments=attachments,
    )


def _follow_up(p: Persona, when: datetime, rng: random.Random) -> EmailEvent:
    tone = _tone(p)
    body = (
        f"Hi,\n\n{rng.choice(tone['openers'])} I applied for the {p.title} role on "
        f"{p.submitted_at.strftime('%B %d')} and wanted to see if there's any update.\n\n"
        f"{rng.choice(tone['closers'])}\n\n{p.first_name} {p.last_name}"
    )
    return EmailEvent(
        persona_idx=p.idx, direction="candidate_to_recruiter", kind="follow_up", timestamp=when,
        subject=f"Re: Application for {p.title} — {p.first_name} {p.last_name}", body=body,
    )


def _resume_update(p: Persona, when: datetime, work_dir: Path, rng: random.Random, base_subject: str) -> EmailEvent:
    updated = copy.deepcopy(p)
    cert_pool = [c for c in CERTS.get(p.role, []) if c not in p.certs]
    new_cert = rng.choice(cert_pool) if cert_pool else None
    if new_cert:
        updated.certs = [*p.certs, new_cert]
    updated.years_exp = p.years_exp + max(0, round((when - p.submitted_at).days / 365))

    slug = f"{p.idx:06d}_{p.first_name}_{p.last_name}_update".lower()
    resume_path = work_dir / f"{slug}_resume.pdf"
    render_resume_pdf(updated, resume_path)

    cert_note = f" — I recently earned {new_cert}" if new_cert else " with some updates"
    body = (
        f"Hi,\n\nWanted to share an updated resume{cert_note}. Figured it was worth sending in "
        f"case the {p.title} role (or something similar) is still open.\n\n{p.first_name} {p.last_name}"
    )
    return EmailEvent(
        persona_idx=p.idx, direction="candidate_to_recruiter", kind="resume_update", timestamp=when,
        subject=f"Re: {base_subject}", body=body, attachments=[resume_path],
    )


def _casual_checkin(p: Persona, when: datetime, base_subject: str) -> EmailEvent:
    body = (
        f"Hi,\n\nHope you've been doing well! Just wanted to check in and see how things are on "
        f"your end. Let me know if anything opens up down the line that might be a fit for someone "
        f"with my background ({p.title}).\n\nBest,\n{p.first_name} {p.last_name}"
    )
    return EmailEvent(
        persona_idx=p.idx, direction="candidate_to_recruiter", kind="casual_checkin", timestamp=when,
        subject=f"Re: {base_subject}", body=body,
    )


def _recruiter_info_request(p: Persona, when: datetime) -> EmailEvent:
    body = (
        f"Hi {p.first_name},\n\nThanks for applying for the {p.title} role. Before we move forward, "
        f"could you confirm your current work authorization status and your availability to start?\n\n"
        f"Thanks,\nRecruiting Team"
    )
    return EmailEvent(
        persona_idx=p.idx, direction="recruiter_to_candidate", kind="recruiter_info_request", timestamp=when,
        subject=f"Re: Application for {p.title} — {p.first_name} {p.last_name}", body=body,
    )


def _candidate_reply(p: Persona, when: datetime, context: str, rng: random.Random) -> EmailEvent:
    tone = _tone(p)
    visa_line = f"My current status is {p.visa_status.replace('_', ' ')}, and I'm {p.employment_status.replace('_', ' ')}."
    body = f"Hi,\n\n{rng.choice(tone['openers'])} {context} {visa_line}\n\n{rng.choice(tone['closers'])}\n\n{p.first_name} {p.last_name}"
    return EmailEvent(
        persona_idx=p.idx, direction="candidate_to_recruiter", kind="candidate_reply", timestamp=when,
        subject=f"Re: Application for {p.title} — {p.first_name} {p.last_name}", body=body,
    )


def _recruiter_update(p: Persona, when: datetime, kind: str) -> EmailEvent:
    if kind == "good_news":
        body = (
            f"Hi {p.first_name},\n\nGood news — we'd like to move you forward to the next round for "
            f"the {p.title} role. Are you available for a call this week?\n\nThanks,\nRecruiting Team"
        )
    elif kind == "bad_news":
        body = (
            f"Hi {p.first_name},\n\nThank you for your patience. Unfortunately we've decided to move "
            f"forward with other candidates for the {p.title} role at this time. We'll keep your resume "
            f"on file for future openings.\n\nBest,\nRecruiting Team"
        )
    else:  # advice
        skill = p.skills[0] if p.skills else "your core skills"
        body = (
            f"Hi {p.first_name},\n\nOne piece of feedback from the team while your application is in "
            f"review: highlighting more hands-on {skill} experience nearer the top of your resume "
            f"could strengthen future applications. Just wanted to pass that along.\n\nRecruiting Team"
        )
    return EmailEvent(
        persona_idx=p.idx, direction="recruiter_to_candidate", kind=f"recruiter_update_{kind}", timestamp=when,
        subject=f"Re: Application for {p.title} — {p.first_name} {p.last_name}", body=body,
    )


def generate_journey(p: Persona, rng: random.Random, work_dir: Path, now: datetime) -> list[EmailEvent]:
    initial = _initial_application(p, work_dir, rng)
    events = [initial]
    base_subject = initial.subject
    cursor = p.submitted_at

    if p.has_followups:
        for _ in range(rng.randint(1, 2)):
            cursor = cursor + timedelta(days=rng.randint(2, 14))
            if cursor >= now:
                break
            events.append(_follow_up(p, cursor, rng))

    if p.has_resume_update:
        when = p.submitted_at + timedelta(days=rng.randint(30, 400))
        if when < now:
            events.append(_resume_update(p, when, work_dir, rng, base_subject))

    if p.has_casual_checkins:
        checkin_cursor = p.submitted_at
        for _ in range(rng.randint(1, 3)):
            checkin_cursor = checkin_cursor + timedelta(days=rng.randint(60, 1000))
            if checkin_cursor >= now:
                break
            events.append(_casual_checkin(p, checkin_cursor, base_subject))

    if p.is_back_and_forth:
        t1 = p.submitted_at + timedelta(days=rng.randint(1, 5))
        if t1 < now:
            events.append(_recruiter_info_request(p, t1))
            t2 = t1 + timedelta(days=rng.randint(0, 3), hours=rng.randint(1, 20))
            if t2 < now:
                events.append(_candidate_reply(p, t2, "Happy to confirm my details:", rng))
                outcome = rng.choices(["good_news", "bad_news", "advice"], weights=[30, 40, 30])[0]
                t3 = t2 + timedelta(days=rng.randint(3, 21))
                if t3 < now:
                    events.append(_recruiter_update(p, t3, outcome))
                    if p.challenge_persona in ("pushy", "demanding", "micromanaging", "anxious") and outcome != "bad_news":
                        t4 = t3 + timedelta(hours=rng.randint(2, 48))
                        if t4 < now:
                            events.append(_candidate_reply(p, t4, "Thanks for the update — following up on next steps:", rng))

    events.sort(key=lambda e: e.timestamp)
    return events
