import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import models  # noqa: F401 — registers all ORM models with Base metadata
from core.config import settings
from core.database import Base, engine
from orchestrator.router import router as orchestrator_router
from registry.router import router as registry_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Step 1: create tables from ORM metadata ──────────────────────────────
    try:
        logger.info("Startup [1/2]: running Base.metadata.create_all")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Startup [1/2]: schema ready")
    except Exception:
        logger.exception("Startup [1/2] FAILED: create_all raised an exception")
        sys.exit(1)

    # ── Step 2: verify connectivity with a live connection ───────────────────
    try:
        logger.info("Startup [2/2]: verifying database connectivity")
        async with engine.connect() as conn:
            logger.info("Startup [2/2]: connection acquired — %r", conn)
        logger.info("Startup [2/2]: database connectivity OK")
    except Exception:
        logger.exception("Startup [2/2] FAILED: engine could not connect to the database")
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
