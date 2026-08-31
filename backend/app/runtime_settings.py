"""Runtime-mutable mock-mode flags — separate from app/config.py's Settings
(env-loaded once at process startup, effectively frozen thereafter) because
these two specifically need to be flippable live from the UI without
restarting the backend. Initialized from Settings at startup
(init_runtime_settings), then live-updated via PATCH /api/v1/settings/mock-mode
(see routes/mock_mode.py). Same module-global pattern as dependencies.py /
job_registry.py (ADR-008: simple, explicit, testable) — deliberately not
persisted, so a restart falls back to the .env-configured defaults rather
than an unpredictable runtime-toggled state surviving invisibly."""

_use_mock_llm: bool = True
_use_mock_email: bool = True


def init_runtime_settings(use_mock_llm: bool, use_mock_email: bool) -> None:
    global _use_mock_llm, _use_mock_email
    _use_mock_llm = use_mock_llm
    _use_mock_email = use_mock_email


def get_use_mock_llm() -> bool:
    return _use_mock_llm


def get_use_mock_email() -> bool:
    return _use_mock_email


def set_use_mock_llm(value: bool) -> None:
    global _use_mock_llm
    _use_mock_llm = value


def set_use_mock_email(value: bool) -> None:
    global _use_mock_email
    _use_mock_email = value
