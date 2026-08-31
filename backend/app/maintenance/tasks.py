"""The maintenance-task registry — the reusable half of this pattern.

The problem this solves: a feature that reads a field on existing rows
(email_link, or the next one) only works going forward once shipped —
existing candidates/sources predate it and stay blank until *something*
touches those rows again, and a plain rescan usually doesn't (dedup skips
already-seen sources). Every time that happens, it either needs its own
one-off script (easy to forget, easy to lose track of) or gets shipped as
"you'll need to rescan" — which quietly doesn't work, exactly what happened
with email_link.

Instead: a feature that needs this ships its backfill as one more entry
here (id, label, description, the async function to run) and gets, for
free, a background job (app/scanning/job_registry.py — same one scans use,
so progress polling/dedup-guard/pruning are already solved), a route
(routes/maintenance.py), and a "Data maintenance" panel in the UI
(scan-page.tsx) listing every registered task with a Run button — so the
next feature that needs this doesn't reinvent it, and the user has one
place to check for "did this apply to my existing data" instead of that
being buried in a chat transcript."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.maintenance.email_link_backfill import backfill_email_links
from app.models.db import ResumeSource
from app.models.schemas import ScanResult

TaskFn = Callable[[Session, Settings, Callable[[ScanResult], None]], Awaitable[ScanResult]]
PendingCountFn = Callable[[Session], int]


@dataclass
class MaintenanceTask:
    id: str
    label: str
    description: str
    run: TaskFn
    # How many existing rows this task would still touch right now — lets
    # the Dashboard show "3,200 resumes affected" and only surface an
    # "Updates available" banner for tasks that actually have pending work,
    # instead of every registered task always showing up regardless of
    # whether it already ran to completion last time.
    pending_count: PendingCountFn


def _email_link_pending_count(session: Session) -> int:
    return session.execute(
        select(func.count()).select_from(ResumeSource).where(ResumeSource.origin == "email", ResumeSource.email_link == "")
    ).scalar_one()


TASKS: dict[str, MaintenanceTask] = {
    "email_link_backfill": MaintenanceTask(
        id="email_link_backfill",
        label="Backfill email links",
        description=(
            "Adds a direct link to the source email for candidates scanned before that feature existed. "
            "Only touches resumes with no link yet — safe to run repeatedly."
        ),
        run=backfill_email_links,
        pending_count=_email_link_pending_count,
    ),
}
