from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import models  # noqa: F401 — registers all ORM models with Base metadata
from core.config import settings
from core.database import Base, engine
from orchestrator.router import router as orchestrator_router
from registry.router import router as registry_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # create_all is a dev convenience fallback; production uses `make migrate`
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


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
