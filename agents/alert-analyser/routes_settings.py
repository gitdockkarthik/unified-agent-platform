import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from encryption import decrypt, encrypt, is_secret_key
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
    "sync_interval_minutes": 0,
}

# Write-through in-memory cache; populated from DB on startup.
_config: dict = dict(_DEFAULTS)

# Fired whenever settings are saved so the background sync loop re-evaluates immediately.
_sync_changed = asyncio.Event()


async def _upsert(key: str, value) -> None:
    from database import SessionLocal
    from models import AgentConfig

    if SessionLocal is None:
        return
    now = datetime.now(timezone.utc)
    raw = json.dumps(value)
    stored = encrypt(raw) if is_secret_key(key) else raw
    async with SessionLocal() as session:
        stmt = (
            pg_insert(AgentConfig)
            .values(key=key, value=stored, updated_at=now)
            .on_conflict_do_update(
                index_elements=["key"],
                set_={"value": stored, "updated_at": now},
            )
        )
        await session.execute(stmt)
        await session.commit()


async def load_config_from_db() -> dict:
    """Load all config rows from DB into _config. Returns the raw DB dict (empty if no DB)."""
    from database import SessionLocal
    from models import AgentConfig

    if SessionLocal is None:
        logger.warning("load_config_from_db: DATABASE_URL not set — no DB session available")
        return {}
    try:
        async with SessionLocal() as session:
            rows = (await session.execute(select(AgentConfig))).scalars().all()

        logger.info(
            "load_config_from_db: found %d row(s) in agent_config — keys: %s",
            len(rows),
            [r.key for r in rows],
        )

        if not rows:
            return {}

        db_cfg: dict = {}
        for r in rows:
            secret = is_secret_key(r.key)
            try:
                raw = decrypt(r.value) if secret else r.value
                db_cfg[r.key] = json.loads(raw)
                logger.debug("load_config_from_db: loaded key=%r (secret=%s)", r.key, secret)
            except Exception as exc:
                logger.error(
                    "load_config_from_db: failed to decode key=%r (secret=%s, "
                    "stored_prefix=%r): %s",
                    r.key,
                    secret,
                    r.value[:20] if r.value else "",
                    exc,
                )

        _config.update(db_cfg)
        logger.info("load_config_from_db: successfully loaded keys: %s", list(db_cfg))

        # Re-encrypt any secrets stored with a previous key (or stored plaintext).
        # Idempotent: if already encrypted with the current key this is a no-op in terms of data.
        secret_keys = [k for k in db_cfg if is_secret_key(k) and db_cfg[k]]
        if secret_keys:
            for key in secret_keys:
                await _upsert(key, db_cfg[key])
            logger.info("load_config_from_db: re-encrypted %d secret key(s)", len(secret_keys))

        return db_cfg
    except Exception:
        logger.exception("load_config_from_db: DB query failed")
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
    sync_interval_minutes: int = 0


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
    _sync_changed.set()  # wake the background loop to re-evaluate interval immediately
    return {"ok": True}


@router.post("/sync")
async def sync_alerts() -> dict:
    if _config.get("source_type") != "opsgenie":
        raise HTTPException(status_code=400, detail="Source type must be 'opsgenie' to sync")
    for field in ("cloud_id", "email", "api_token"):
        if not _config.get(field):
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
    return await _run_opsgenie_sync()
