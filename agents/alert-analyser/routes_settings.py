import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from report_store import add_report
from tools.noise_detector import classify_alerts
from tools.source import OpsgenieAPISource

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

_DEFAULTS: dict = {
    "source_type": "file",
    "cloud_id": "",
    "email": "",
    "api_token": "",
    "last_synced": None,
    "alert_count": None,
}

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


async def _run_opsgenie_sync() -> dict:
    """Core sync logic — callable from HTTP handler or lifespan startup."""
    source = OpsgenieAPISource(
        cloud_id=_config["cloud_id"],
        email=_config["email"],
        api_token=_config["api_token"],
    )
    alerts = await source.load_alerts()
    classified = classify_alerts(alerts)

    filename = f"opsgenie-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
    report = add_report(filename, alerts, classified)

    _config["last_synced"] = datetime.now(timezone.utc).isoformat()
    _config["alert_count"] = len(alerts)
    await _upsert("last_synced", _config["last_synced"])
    await _upsert("alert_count", _config["alert_count"])

    return {
        "ok": True,
        "alert_count": len(alerts),
        "last_synced": _config["last_synced"],
        "report": report,
    }


class SettingsPayload(BaseModel):
    source_type: str = "file"
    cloud_id: str = ""
    email: str = ""
    api_token: str = ""


@router.get("")
async def get_settings() -> dict:
    await load_config_from_db()
    return {k: v for k, v in _config.items() if k != "api_token"}


@router.post("")
async def save_settings(payload: SettingsPayload) -> dict:
    data = payload.model_dump()
    _config.update(data)
    for k, v in data.items():
        await _upsert(k, v)
    return {"ok": True}


@router.post("/sync")
async def sync_alerts() -> dict:
    if _config.get("source_type") != "opsgenie":
        raise HTTPException(status_code=400, detail="Source type must be 'opsgenie' to sync")
    for field in ("cloud_id", "email", "api_token"):
        if not _config.get(field):
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
    return await _run_opsgenie_sync()
