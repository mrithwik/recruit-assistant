"""
Central settings for the single-process backend, read from environment / .env.

Everything the app needs at startup lives here so config stays 12-factor
(fail-fast type validation instead of runtime KeyErrors), mirroring the
Pydantic Settings pattern used across Prodigon's services.
"""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "recruit-assistant"
    environment: str = "development"
    log_level: str = "INFO"

    # Mock mode bypasses external LLM + email API calls entirely, using
    # MockLLMClient / MockEmailIngestor fixtures — lets the whole app run
    # offline with zero API keys, which is also what CI/golden tests use.
    # Split into two independent flags (previously one USE_MOCK covering
    # both) — a real-Gmail scan needs use_mock_email=false, but that
    # shouldn't force every resume's parsing/summarization/embedding onto a
    # real, paid LLM call too. These are just the startup defaults; both are
    # live-toggleable at runtime without a restart — see app/runtime_settings.py
    # and routes/mock_mode.py.
    use_mock_llm: bool = True
    use_mock_email: bool = True

    # Whether the mock/real toggle is exposed in the UI at all (Scan
    # Sources page) — default on since this is a single-user local tool, but
    # gives anyone who hands this app to someone else a way to hide a
    # control that can incur real API cost.
    expose_mock_mode_toggle: bool = True

    # Points MockEmailIngestor at a generated dataset (see
    # scripts/generate_sample_data.py) so "Scan email" is testable at volume
    # with zero OAuth setup. Ignored unless use_mock_email is true. A demo
    # mailbox is auto-seeded in EmailAccount when this is set (see main.py
    # lifespan).
    mock_email_fixtures_path: str = ""

    # LLM (OpenRouter primary, OpenAI fallback)
    openrouter_api_key: str = ""
    openai_api_key: str = ""
    llm_triage_model: str = "openrouter/meta-llama/llama-3.1-8b-instruct"
    llm_scoring_model: str = "openrouter/openai/gpt-4.1-mini"
    llm_judge_model: str = "openrouter/anthropic/claude-3.5-sonnet"
    embedding_model: str = "openrouter/openai/text-embedding-3-small"

    # Caps in-flight LLM calls during matching/embedding (asyncio.gather runs
    # them concurrently instead of one-at-a-time) — high enough to actually
    # speed things up, low enough not to trip provider rate limits.
    max_concurrent_llm_calls: int = 8

    # Caps in-flight Gmail/Outlook API calls during an email scan — same
    # bounded-concurrency pattern as max_concurrent_llm_calls above. Found
    # via load testing (see project-log): Gmail's per-user rate limit starts
    # rejecting requests with 429s somewhere around 25 concurrent, so this
    # stays comfortably under that with retry/backoff handling the rest.
    max_concurrent_email_fetches: int = 15

    # Email OAuth
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    ms_oauth_client_id: str = ""
    ms_oauth_client_secret: str = ""
    ms_oauth_tenant_id: str = "common"
    oauth_redirect_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:5173"

    # Storage
    data_dir: str = "./data"
    sqlite_path: str = "./data/recruit_assistant.db"

    api_port: int = 8000

    # Off by default — nightly auto-scanning is opt-in per source (see
    # ScheduledSource / the Scan Sources page toggle), and this is the master
    # switch: even with sources marked for auto-scan, nothing runs unless
    # this is also true. scheduler_hour is a 0-23 local-time hour.
    scheduler_enabled: bool = False
    scheduler_hour: int = 2

    # Auth — signs session tokens (see app/auth/security.py). If left blank,
    # a random key is generated on first run and persisted to
    # DATA_DIR/.secret_key so sessions survive restarts without requiring
    # the user to configure anything; set SECRET_KEY explicitly in .env for
    # a stable key across environments (e.g. before a production deploy).
    secret_key: str = ""
    # "Keep me signed in" (default, since this is a personal local app) vs a
    # short session for a shared/borrowed machine — see routes/auth.py.
    session_ttl_hours_remembered: int = 24 * 30
    session_ttl_hours_short: int = 12

    model_config = {
        "env_file": "../.env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def data_dir_path(self) -> Path:
        p = Path(self.data_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def resolved_secret_key(self) -> str:
        if self.secret_key:
            return self.secret_key
        key_path = self.data_dir_path / ".secret_key"
        if key_path.exists():
            return key_path.read_text().strip()
        import secrets

        key = secrets.token_hex(32)
        key_path.write_text(key)
        return key

    @property
    def candidates_dir(self) -> Path:
        p = self.data_dir_path / "candidates"
        p.mkdir(parents=True, exist_ok=True)
        return p
