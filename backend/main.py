import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import models  # noqa: F401 — registers all ORM models with Base metadata
from core.config import settings
from core.database import engine
from orchestrator.router import router as orchestrator_router
from registry.router import router as registry_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def _run_migrations() -> None:
    logger.info("Running Alembic migrations…")
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    logger.info("Alembic migrations complete.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Step 1: Alembic migrations ───────────────────────────────────────────
    try:
        logger.info("Startup [1/2]: running Alembic migrations")
        await asyncio.get_event_loop().run_in_executor(None, _run_migrations)
        logger.info("Startup [1/2]: migrations complete")
    except Exception:
        logger.exception("Startup [1/2] FAILED: Alembic migration raised an exception")
        sys.exit(1)

    # ── Step 2: verify SQLAlchemy engine can reach the database ─────────────
    try:
        logger.info("Startup [2/2]: verifying database connectivity (engine.connect)")
        async with engine.connect() as conn:
            logger.info("Startup [2/2]: connection acquired — %r", conn)
        logger.info("Startup [2/2]: database connectivity OK")
    except Exception:
        logger.exception("Startup [2/2] FAILED: SQLAlchemy engine could not connect to the database")
        sys.exit(1)

    logger.info("Startup complete — application is ready to serve requests")
    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    try:
        logger.info("Shutdown: disposing SQLAlchemy engine")
        await engine.dispose()
        logger.info("Shutdown: engine disposed cleanly")
    except Exception:
        logger.exception("Shutdown error: engine.dispose() raised an exception")


app = FastAPI(
    title="Unified Agent Platform — Backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(registry_router)
app.include_router(orchestrator_router)
