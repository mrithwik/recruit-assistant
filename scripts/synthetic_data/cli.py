#!/usr/bin/env python3
"""Generates synthetic tech-candidate emails (resume + optional cover
letter/work-auth/photo-ID/passport) and delivers them into the connected
Gmail test account: a small batch via real SMTP, the rest via Gmail API
insert. See architecture/project-log.md for the full plan this implements.

Usage (run from repo root, backend venv):
    python scripts/synthetic_data/cli.py --count 20 --smtp-count 5 --trial
    python scripts/synthetic_data/cli.py --count 10000 --smtp-count 75 --ocr-count 100

Requires: TEST_SENDER_EMAIL / TEST_SENDER_APP_PASSWORD in .env, and a
connected Gmail account (via the app's Email Access page) with the
gmail.insert scope granted.
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import os
import random
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT))
# Settings.data_dir_path / sqlite_path are relative paths the real app only
# resolves correctly because uvicorn runs with cwd=backend/ — match that so
# resolved_secret_key and the sqlite path line up with the running backend.
os.chdir(REPO_ROOT / "backend")

from dotenv import dotenv_values  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.config import Settings  # noqa: E402
from app.email_auth.oauth import get_valid_access_token  # noqa: E402
from app.models.db import EmailAccount  # noqa: E402
from app.storage.local import LocalStorageBackend  # noqa: E402

from scripts.synthetic_data.journeys import generate_journey  # noqa: E402
from scripts.synthetic_data.personas import generate_personas  # noqa: E402
from scripts.synthetic_data.pipeline import (  # noqa: E402
    build_single_application_message,
    insert_journeys_via_gmail_api_async,
    send_batch_via_smtp,
    write_manifest,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--smtp-count", type=int, default=5)
    parser.add_argument("--ocr-count", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--concurrency", type=int, default=8, help="max concurrent Gmail API insert journeys")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("/private/tmp/claude-501/-Users-mrithwik-projects-recruit-assistant/84a0869d-6430-410c-8d69-e65416344284/scratchpad/synthetic_data"),
    )
    args = parser.parse_args()

    env = dotenv_values(REPO_ROOT / ".env")
    sender_email = env.get("TEST_SENDER_EMAIL")
    sender_password = env.get("TEST_SENDER_APP_PASSWORD")
    if not sender_email or not sender_password:
        print("Missing TEST_SENDER_EMAIL / TEST_SENDER_APP_PASSWORD in .env", file=sys.stderr)
        sys.exit(1)

    settings = Settings(_env_file=str(REPO_ROOT / ".env"))
    storage = LocalStorageBackend(settings.sqlite_path)
    with storage.session() as session:
        account = (
            session.execute(
                select(EmailAccount).where(EmailAccount.provider == "gmail", EmailAccount.keychain_ref != "")
            )
            .scalars()
            .first()
        )
    if account is None:
        print("No connected Gmail account found — connect one via Email Access first.", file=sys.stderr)
        sys.exit(1)

    get_token = functools.partial(get_valid_access_token, account.id, "gmail")
    if not get_token():
        print("Could not get a valid Gmail access token for the connected account.", file=sys.stderr)
        sys.exit(1)

    recipient = account.email_address
    print(f"Generating {args.count} personas (seed={args.seed}, ocr_count={args.ocr_count})...")
    personas = generate_personas(args.count, args.seed, args.ocr_count)
    personas_by_idx = {p.idx: p for p in personas}

    args.out.mkdir(parents=True, exist_ok=True)
    smtp_personas = personas[: args.smtp_count]
    api_personas = personas[args.smtp_count :]

    print(f"Building {len(smtp_personas)} single-message applications for the real SMTP batch...")
    smtp_messages = [build_single_application_message(p, args.out, sender_email) for p in smtp_personas]
    print(f"Sending via real SMTP from {sender_email} -> {recipient} ...")
    smtp_subjects = send_batch_via_smtp(smtp_messages, sender_email, sender_password, recipient) if smtp_messages else []

    rng = random.Random(args.seed + 1)
    now = datetime.utcnow()
    print(f"Building journeys for {len(api_personas)} personas (follow-ups, resume updates, check-ins, back-and-forth)...")
    journeys = [generate_journey(p, rng, args.out, now) for p in api_personas]
    total_events = sum(len(j) for j in journeys)
    print(f"Inserting {total_events} total messages across {len(journeys)} journeys via Gmail API into {recipient} (concurrency={args.concurrency})...")
    journey_event_counts = {p.idx: len(j) for p, j in zip(api_personas, journeys)}
    manifest_path = args.out / "manifest.json"
    api_inserted: list = []
    try:
        api_inserted = (
            asyncio.run(insert_journeys_via_gmail_api_async(journeys, personas_by_idx, get_token, recipient, args.concurrency))
            if journeys
            else []
        )
    finally:
        # Always write whatever we have — a partial manifest from a crash
        # mid-run is still needed for cleanup.py to find what got delivered.
        write_manifest(manifest_path, personas, smtp_subjects, api_inserted, journey_event_counts)

    errors = [e for e in api_inserted if "error" in e]
    print(f"Done. Manifest written to {manifest_path}")
    print(
        f"SMTP sent: {len(smtp_subjects)}, API inserted OK: {len(api_inserted) - len(errors)}, "
        f"failed: {len(errors)} (across {len(journeys)} journeys), total personas: {len(personas)}"
    )


if __name__ == "__main__":
    main()
