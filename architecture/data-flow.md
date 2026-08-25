<!-- Version: v0 | Last updated: 2026-08-01 | Status: current -->

# Data Flow

## Ingestion (folder or email — same pipeline)

```mermaid
sequenceDiagram
    participant UI as Frontend
    participant API as /scan/*
    participant Ing as ResumeIngestor
    participant Parser as parser.py
    participant ID as identity_resolution.py
    participant Mirror as mirror_writer.py
    participant DB as SQLite

    UI->>API: POST /scan/folders or /scan/email-accounts
    API->>Ing: scan(date_start, date_end)
    loop each resume found
        Ing-->>API: IngestedResume
        API->>Parser: parse_resume(bytes, filename)
        Parser-->>API: CandidateProfile
        API->>ID: compute_fingerprint + merge_into_candidate
        ID-->>API: Candidate (new or updated)
        API->>Mirror: write_mirror(...)
        Mirror-->>API: file_path
        API->>DB: upsert Candidate + ResumeSource
    end
    API-->>UI: ScanResult
```

## Matching

```mermaid
sequenceDiagram
    participant UI as Frontend
    participant API as POST /matches/run/{job_id}
    participant Emb as embeddings.py
    participant LLM as LLMClient
    participant Judge as judge_score()

    UI->>API: run matching, top_n
    API->>Emb: embed job + every candidate
    Emb-->>API: shortlist (top_n * 3 by similarity)
    loop each shortlisted candidate
        API->>LLM: deep_score(job, resume, profile)
        LLM-->>API: {score, matched, gaps, missing_info}
        alt score is borderline (40-70)
            API->>Judge: judge_score(...)
            Judge-->>API: corrected score + notes
        end
    end
    API->>API: score_to_tier() per result
    API-->>UI: ranked Match list, persisted
```

## Draft email

`POST /draft-email {match_id}` reads the persisted `Match` (job + candidate + reasons),
checks the four required fields on the candidate, and asks the LLM to write a draft
referencing the specific matched strengths — not a generic template.
