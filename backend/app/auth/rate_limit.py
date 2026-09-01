"""In-memory login-attempt limiter — single-process state, same pattern as
scanning/job_registry.py, rather than pulling in Redis for a tool meant to
run as one process on one laptop. Keyed by the attempted email (lowercased),
not IP: this app is reached from at most one machine's own network
interface (see API_HOST in .env.example), so IP doesn't distinguish
anything email doesn't already.

Resets on process restart — acceptable here; the goal is raising the cost
of online credential-stuffing against a login form that's reachable at
all, not surviving a determined attacker across restarts."""

import time
from dataclasses import dataclass, field

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60


@dataclass
class _AttemptState:
    count: int = 0
    window_started_at: float = field(default_factory=time.monotonic)


_attempts: dict[str, _AttemptState] = {}


def seconds_until_unlocked(email: str) -> float:
    """0.0 if this email isn't currently locked out, else how many seconds
    remain before another attempt is allowed."""
    state = _attempts.get(email.lower())
    if state is None or state.count < MAX_FAILED_ATTEMPTS:
        return 0.0
    remaining = LOCKOUT_SECONDS - (time.monotonic() - state.window_started_at)
    return max(0.0, remaining)


def record_failure(email: str) -> None:
    key = email.lower()
    now = time.monotonic()
    state = _attempts.get(key)
    if state is None or now - state.window_started_at > LOCKOUT_SECONDS:
        state = _AttemptState(count=0, window_started_at=now)
    state.count += 1
    _attempts[key] = state


def record_success(email: str) -> None:
    # A correct login clears whatever failure count preceded it — the
    # lockout is about slowing down guessing, not punishing the account
    # once the right password shows up.
    _attempts.pop(email.lower(), None)


def reset_all() -> None:
    """Test-only — clears all in-memory attempt state between test runs
    that share this module-level dict across a single test process."""
    _attempts.clear()
