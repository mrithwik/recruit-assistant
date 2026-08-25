"""Regression test for the exact bug that broke every existing database when
`Candidate.embedding` was added: `Base.metadata.create_all()` only creates
tables that don't exist yet, it never alters an existing table to add a
column a newer model version introduced. `LocalStorageBackend` now runs
`_add_missing_columns()` on startup to auto-migrate — this pins that it
actually adds the column and the row stays queryable afterward."""

import sqlite3
import uuid
from datetime import datetime


def test_missing_column_is_added_on_startup(tmp_sqlite_path):
    from app.storage.local import LocalStorageBackend

    # Simulate an "old" database: create the candidates table without the
    # embedding column a newer model version expects, exactly like a real
    # database created before that column existed.
    conn = sqlite3.connect(tmp_sqlite_path)
    conn.execute(
        """
        CREATE TABLE candidates (
            id VARCHAR PRIMARY KEY,
            identity_fingerprint VARCHAR UNIQUE,
            legal_first_name VARCHAR,
            legal_middle_name VARCHAR,
            legal_last_name VARCHAR,
            email VARCHAR,
            phone VARCHAR,
            employment_status VARCHAR,
            work_visa_status VARCHAR,
            skills JSON,
            experience_years FLOAT,
            education JSON,
            raw_parsed_profile JSON,
            semantic_summary TEXT,
            date_submitted DATETIME,
            primary_file_path VARCHAR,
            linkedin_url VARCHAR,
            github_url VARCHAR,
            portfolio_url VARCHAR,
            history JSON,
            created_at DATETIME,
            updated_at DATETIME
        )
        """
    )
    candidate_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO candidates (id, identity_fingerprint, date_submitted) VALUES (?, ?, ?)",
        (candidate_id, "email:pre-migration@example.com", datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()

    cols_before = {r[1] for r in sqlite3.connect(tmp_sqlite_path).execute("PRAGMA table_info(candidates)")}
    assert "embedding" not in cols_before

    # Instantiating the backend is what ran the broken startup path before —
    # this must not raise, and must leave the pre-existing row intact.
    storage = LocalStorageBackend(tmp_sqlite_path)

    cols_after = {r[1] for r in sqlite3.connect(tmp_sqlite_path).execute("PRAGMA table_info(candidates)")}
    assert "embedding" in cols_after

    from app.models.db import Candidate

    with storage.session() as session:
        candidate = session.get(Candidate, candidate_id)
        assert candidate is not None
        assert candidate.embedding == []
