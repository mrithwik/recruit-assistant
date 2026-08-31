#!/usr/bin/env python3
"""Creates job postings spanning the synthetic-candidate role mix, via the
real POST /api/v1/jobs endpoint (so parsed_requirements goes through the
app's normal triage path, not a hand-rolled duplicate). Mints a session
token the same way login does (create_session_token) instead of asking for
the account password.

Usage:
    python scripts/synthetic_data/generate_jobs.py [--base-url http://localhost:8000]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))
# Settings.data_dir_path / sqlite_path are relative paths the real app only
# resolves correctly because uvicorn runs with cwd=backend/ — match that so
# resolved_secret_key reads the same key file the running backend uses.
os.chdir(REPO_ROOT / "backend")

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.auth.security import create_session_token  # noqa: E402
from app.config import Settings  # noqa: E402
from app.models.db import User  # noqa: E402
from app.storage.local import LocalStorageBackend  # noqa: E402

JOB_POSTINGS = [
    (
        "Senior Backend Engineer",
        "Vertex Systems",
        "We're hiring a Senior Backend Engineer to own core services. Requirements: 5+ years "
        "with Python (FastAPI or Django), PostgreSQL, and container orchestration (Kubernetes/Docker). "
        "Experience with gRPC or Kafka a plus. Must be authorized to work in the US.",
    ),
    (
        "Frontend Engineer",
        "Cascade Digital",
        "Looking for a Frontend Engineer skilled in React and TypeScript, with experience building "
        "accessible, performant UIs. 2-5 years experience. Familiarity with Next.js and Tailwind CSS preferred.",
    ),
    (
        "AI Engineer",
        "Fathom AI",
        "AI Engineer to build and ship LLM-powered features. Requirements: hands-on experience with "
        "LangChain or LlamaIndex, RAG pipeline design, vector databases (Pinecone/Weaviate/pgvector), "
        "and production Python. Prompt engineering and eval-harness experience a strong plus.",
    ),
    (
        "AI Forward Deployed Engineer",
        "Fathom AI",
        "Forward Deployed Engineer working directly with enterprise customers to prototype and ship "
        "LLM-based solutions on-site. Needs strong Python, RAG/LangChain experience, and comfort presenting "
        "to non-technical stakeholders. Heavy travel-adjacent, customer-facing role.",
    ),
    (
        "Machine Learning Engineer",
        "Redwood Analytics",
        "ML Engineer to build and maintain production model-serving infrastructure. Requirements: "
        "PyTorch or TensorFlow, MLflow/Kubeflow, distributed training experience, strong Python.",
    ),
    (
        "DevOps / Site Reliability Engineer",
        "Nimbus Cloud",
        "SRE to own our Kubernetes platform and CI/CD pipelines. Requirements: Terraform, AWS or GCP, "
        "Prometheus/Grafana, incident response experience. CKA certification a plus.",
    ),
    (
        "Product Manager",
        "Bluepeak",
        "Product Manager to own our core platform roadmap. Requirements: 3+ years PM experience, "
        "strong SQL, experience running A/B tests, comfortable working cross-functionally with engineering.",
    ),
    (
        "Product Owner",
        "Ironleaf",
        "Product Owner to manage the backlog for an agile engineering team. Requirements: Scrum experience, "
        "strong stakeholder communication, CSPO certification preferred, Jira fluency.",
    ),
    (
        "Business Analyst",
        "Quartz Financial",
        "Business Analyst to gather requirements and map processes across finance operations. Requirements: "
        "strong SQL, experience writing BRDs, stakeholder interviewing, Tableau or Power BI.",
    ),
    (
        "Technical Program Manager",
        "Harbor Robotics",
        "TPM to coordinate cross-functional engineering programs. Requirements: PMP or equivalent experience, "
        "risk management, Agile/Scrum fluency, comfort driving alignment across engineering teams.",
    ),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    settings = Settings(_env_file=str(REPO_ROOT / ".env"))
    storage = LocalStorageBackend(settings.sqlite_path)

    with storage.session() as session:
        user = session.execute(select(User)).scalars().first()
    if user is None:
        print("No user found in the DB — set up the app's login first.", file=sys.stderr)
        sys.exit(1)

    token = create_session_token(user.id, settings.resolved_secret_key, settings.session_ttl_hours_short)
    headers = {"Authorization": f"Bearer {token}"}

    created = []
    with httpx.Client(base_url=args.base_url, headers=headers, timeout=60.0) as client:
        for title, company, raw_text in JOB_POSTINGS:
            resp = client.post("/api/v1/jobs", json={"title": title, "company": company, "raw_text": raw_text})
            if resp.status_code >= 400:
                print(f"Failed to create '{title}': {resp.status_code} {resp.text[:300]}", file=sys.stderr)
                continue
            job = resp.json()
            created.append(job["id"])
            print(f"Created: {title} @ {company} ({job['id']})")

    print(f"\nDone. Created {len(created)}/{len(JOB_POSTINGS)} jobs.")


if __name__ == "__main__":
    main()
