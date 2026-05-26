import asyncio
import logging
import sys
import traceback
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
    try:
        logger.info("Startup: beginning migration step")
        await asyncio.get_event_loop().run_in_executor(None, _run_migrations)
        logger.info("Startup: migrations done — application ready")
    except Exception:
        logger.critical("Startup failed:\n%s", traceback.format_exc())
        sys.exit(1)

    yield

    try:
        await engine.dispose()
        logger.info("Shutdown: database engine disposed")
    except Exception:
        logger.error("Shutdown error:\n%s", traceback.format_exc())


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
