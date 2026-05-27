import json
import logging

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

_DEFAULTS: dict = {"source_type": "file"}

# Write-through in-memory cache; populated from DB on startup.
_config: dict = dict(_DEFAULTS)


async def _upsert(key: str, value) -> None:
    from database import SessionLocal
    from models import AgentConfig

    if SessionLocal is None:
        return
    now = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        stmt = (
            pg_insert(AgentConfig)
            .values(key=key, value=json.dumps(value), updated_at=now)
            .on_conflict_do_update(
                index_elements=["key"],
                set_={"value": json.dumps(value), "updated_at": now},
            )
        )
        await session.execute(stmt)
        await session.commit()


async def load_config_from_db() -> dict:
    """Load all config rows from DB into _config. Returns the raw DB dict (empty if no DB)."""
    from database import SessionLocal
    from models import AgentConfig

    if SessionLocal is None:
        return {}
    try:
        async with SessionLocal() as session:
            rows = (await session.execute(select(AgentConfig))).scalars().all()
        db_cfg = {r.key: json.loads(r.value) for r in rows}
        _config.update(db_cfg)
        return db_cfg
    except Exception:
        logger.exception("Failed to load config from DB")
        return {}


class SettingsPayload(BaseModel):
    source_type: str = "file"


@router.get("")
async def get_settings() -> dict:
    await load_config_from_db()
    return dict(_config)


@router.post("")
async def save_settings(payload: SettingsPayload) -> dict:
    _config["source_type"] = payload.source_type
    await _upsert("source_type", payload.source_type)
    return {"ok": True}
