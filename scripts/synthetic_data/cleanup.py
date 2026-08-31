#!/usr/bin/env python3
"""Safety net for the synthetic Gmail load-test dataset: finds every
Candidate/ResumeSource/Match row created from the synthetic personas (by
matching Candidate.email against the persona emails recorded in one or more
manifest.json files) and deletes them from the local DB.

Does NOT touch the Gmail account itself — deleting/trashing messages needs
gmail.modify, a scope this project deliberately didn't request (see
architecture/project-log.md). To remove the emails themselves, search Gmail
for the tag (default "[SYNTH-DEMO-2026-08-26]") and archive/delete manually.

Usage:
    python scripts/synthetic_data/cleanup.py --manifest path/to/manifest.json [--manifest ...] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT))
os.chdir(REPO_ROOT / "backend")

from sqlalchemy import select  # noqa: E402

from app.config import Settings  # noqa: E402
from app.models.db import Candidate  # noqa: E402
from app.storage.local import LocalStorageBackend  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", action="append", required=True, help="path to a manifest.json (repeatable)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    emails: set[str] = set()
    tags: set[str] = set()
    for manifest_path in args.manifest:
        data = json.loads(Path(manifest_path).read_text())
        tags.add(data["tag"])
        emails.update(p["email"] for p in data["personas"])

    settings = Settings(_env_file=str(REPO_ROOT / ".env"))
    storage = LocalStorageBackend(settings.sqlite_path)

    with storage.session() as session:
        candidates = session.execute(select(Candidate).where(Candidate.email.in_(emails))).scalars().all()
        print(f"Found {len(candidates)} synthetic candidates in the local DB (of {len(emails)} personas tagged).")
        if args.dry_run:
            print("--dry-run: not deleting. Re-run without --dry-run to actually remove them.")
            return
        for c in candidates:
            session.delete(c)  # cascades to ResumeSource + Match rows (see models/db.py)
        session.commit()
        print(f"Deleted {len(candidates)} candidates and their sources/matches.")

    print(
        f"\nGmail itself is untouched (no delete/modify scope granted). To remove the emails, "
        f"search Gmail for: {' OR '.join(sorted(tags))}"
    )


if __name__ == "__main__":
    main()
