"""FastAPI entrypoint — single process, modular internally (see
architecture/design-decisions.md ADR on backend shape)."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.dependencies import require_auth
from app.dependencies import get_settings, init_dependencies
from app.logging import configure_logging, get_logger
from app.routes import (
    auth,
    candidates,
    criteria,
    dashboard,
    dev_tools,
    draft_email,
    email_accounts,
    health,
    history,
    jobs,
    matches,
    scan,
    scheduled_sources,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.dependencies import get_llm_client, get_storage

    settings = get_settings()
    configure_logging(settings.log_level)
    init_dependencies(settings)
    logger.info("startup", use_mock=settings.use_mock, data_dir=str(settings.data_dir_path))

    scheduler = None
    if settings.scheduler_enabled:
        from app.scheduler import start_scheduler

        scheduler = start_scheduler(get_storage(), get_llm_client(), settings)

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Recruit Assistant API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public — no session required.
app.include_router(health.router)
app.include_router(auth.router)

# Everything else requires a valid session (require_auth). email_accounts is
# intentionally excluded here: its OAuth connect/callback endpoints are
# plain-link browser redirects that can't carry a Bearer header, so that
# router applies auth per-route instead (see routes/email_accounts.py).
protected = [Depends(require_auth)]
app.include_router(dashboard.router, dependencies=protected)
app.include_router(jobs.router, dependencies=protected)
app.include_router(scan.router, dependencies=protected)
app.include_router(candidates.router, dependencies=protected)
app.include_router(matches.router, dependencies=protected)
app.include_router(criteria.router, dependencies=protected)
app.include_router(history.router, dependencies=protected)
app.include_router(draft_email.router, dependencies=protected)
app.include_router(dev_tools.router, dependencies=protected)
app.include_router(scheduled_sources.router, dependencies=protected)
app.include_router(email_accounts.router)
