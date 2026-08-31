"""Renders the actual attachment files for each Persona: resumes (text-layer
PDF, or image-only PDF for the OCR-fallback subset), cover letters, work
authorization letters, and watermarked photo-ID/passport mocks. Everything is
wrapped as a single-page PDF, since app/scanning/folder_ingestor.py's
SUPPORTED_EXTENSIONS ({.pdf, .docx, .txt}) is what decides whether an
attachment even qualifies to be recorded at all — a bare .png would be
silently dropped, not recorded as additional_attachments.
"""

from __future__ import annotations

import io
from pathlib import Path

import img2pdf
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from .personas import Persona

PAGE_W, PAGE_H = LETTER


def _wrap_text(c: canvas.Canvas, text: str, x: float, y: float, max_width: float, font="Helvetica", size=10, leading=13) -> float:
    c.setFont(font, size)
    for paragraph in text.split("\n"):
        words = paragraph.split(" ")
        line = ""
        for word in words:
            trial = f"{line} {word}".strip()
            if c.stringWidth(trial, font, size) > max_width and line:
                c.drawString(x, y, line)
                y -= leading
                line = word
            else:
                line = trial
        c.drawString(x, y, line)
        y -= leading
    return y


def render_resume_text(p: Persona) -> str:
    header = f"{p.first_name} {p.last_name}\n{p.email} | {p.phone} | {p.city}"
    summary = (
        f"{p.seniority} {p.title} with {p.years_exp} years of experience. "
        f"Work authorization: {p.visa_status.replace('_', ' ')}. Status: {p.employment_status.replace('_', ' ')}."
    )
    skills = "Skills: " + ", ".join(p.skills)
    certs = ("Certifications: " + ", ".join(p.certs)) if p.certs else ""
    experience_lines = []
    for i, company in enumerate(p.company_history):
        experience_lines.append(f"- {p.title} @ {company}")
    experience = "Experience:\n" + "\n".join(experience_lines)
    education = f"Education: {p.degree}, {p.school}"
    parts = [header, "", summary, "", skills]
    if certs:
        parts += ["", certs]
    parts += ["", experience, "", education]
    return "\n".join(parts)


def render_resume_pdf(p: Persona, out_path: Path) -> None:
    c = canvas.Canvas(str(out_path), pagesize=LETTER)
    x, y = 0.75 * inch, PAGE_H - 0.75 * inch
    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, f"{p.first_name} {p.last_name}")
    y -= 20
    c.setFont("Helvetica", 10)
    c.drawString(x, y, f"{p.email}  |  {p.phone}  |  {p.city}")
    y -= 24
    body = render_resume_text(p).split("\n", 2)[2]  # skip header already drawn
    y = _wrap_text(c, body, x, y, PAGE_W - 1.5 * inch)
    c.save()


def render_resume_pdf_image_only(p: Persona, out_path: Path) -> None:
    """Renders the resume as a flattened image with no text layer, so
    pypdf/pdfplumber extraction yields ~0 chars and the OCR fallback in
    parser.py has to fire to recover anything."""
    img = Image.new("RGB", (1700, 2200), "white")
    draw = ImageDraw.Draw(img)
    try:
        font_bold = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 42)
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
    except OSError:
        font_bold = font = ImageFont.load_default()

    y = 80
    draw.text((80, y), f"{p.first_name} {p.last_name}", fill="black", font=font_bold)
    y += 70
    draw.text((80, y), f"{p.email} | {p.phone} | {p.city}", fill="black", font=font)
    y += 60
    body = render_resume_text(p).split("\n", 2)[2]
    for line in body.split("\n"):
        wrapped = []
        cur = ""
        for word in line.split(" "):
            trial = f"{cur} {word}".strip()
            if draw.textlength(trial, font=font) > 1500 and cur:
                wrapped.append(cur)
                cur = word
            else:
                cur = trial
        wrapped.append(cur)
        for w in wrapped:
            draw.text((80, y), w, fill="black", font=font)
            y += 40

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    out_path.write_bytes(img2pdf.convert(buf.getvalue()))


def render_cover_letter_pdf(p: Persona, out_path: Path) -> None:
    c = canvas.Canvas(str(out_path), pagesize=LETTER)
    x, y = 0.75 * inch, PAGE_H - 0.75 * inch
    text = (
        f"Dear Hiring Team,\n\n"
        f"I'm writing to apply for the {p.title} role. With {p.years_exp} years of experience in "
        f"{', '.join(p.skills[:3])}, I believe I'd be a strong fit for this position.\n\n"
        f"Thank you for your consideration.\n\n{p.first_name} {p.last_name}"
    )
    _wrap_text(c, text, x, y, PAGE_W - 1.5 * inch)
    c.save()


def render_work_auth_pdf(p: Persona, out_path: Path) -> None:
    c = canvas.Canvas(str(out_path), pagesize=LETTER)
    x, y = 0.75 * inch, PAGE_H - 0.75 * inch
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, y, "Work Authorization Summary")
    y -= 30
    text = (
        f"Name: {p.first_name} {p.last_name}\n"
        f"Status: {p.visa_status.replace('_', ' ').title()}\n"
        f"This document is a synthetic test fixture and confers no legal status."
    )
    _wrap_text(c, text, x, y, PAGE_W - 1.5 * inch)
    c.save()


def _mock_id_image(title: str, p: Persona, doc_number: str) -> Image.Image:
    img = Image.new("RGB", (1013, 638), "#EAF2FB")
    draw = ImageDraw.Draw(img)
    try:
        font_title = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 34)
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 26)
        font_watermark = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 60)
    except OSError:
        font_title = font = font_watermark = ImageFont.load_default()

    draw.rectangle([0, 0, 1013, 90], fill="#1E3A5F")
    draw.text((30, 25), title, fill="white", font=font_title)
    draw.rectangle([40, 130, 260, 350], outline="#888888", width=3)
    draw.ellipse([70, 160, 230, 320], fill="#CBD5E1")

    lines = [
        f"Name: {p.first_name} {p.last_name}",
        f"DOB: 01/01/1995",
        f"Document No: {doc_number}",
        f"Issued: Synthetic Test Authority",
        f"Expires: N/A (test fixture)",
    ]
    y = 150
    for line in lines:
        draw.text((300, y), line, fill="#1E1E1E", font=font)
        y += 45

    # Watermark
    watermark_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    wd = ImageDraw.Draw(watermark_layer)
    wd.text((120, 480), "SAMPLE — NOT A REAL DOCUMENT", fill=(200, 30, 30, 140), font=font_watermark)
    img = Image.alpha_composite(img.convert("RGBA"), watermark_layer).convert("RGB")
    return img


def render_photo_id_pdf(p: Persona, out_path: Path) -> None:
    img = _mock_id_image("SAMPLE STATE ID", p, f"ID-{p.idx:08d}")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    out_path.write_bytes(img2pdf.convert(buf.getvalue()))


def render_passport_pdf(p: Persona, out_path: Path) -> None:
    img = _mock_id_image("SAMPLE PASSPORT", p, f"P{p.idx:08d}")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    out_path.write_bytes(img2pdf.convert(buf.getvalue()))
