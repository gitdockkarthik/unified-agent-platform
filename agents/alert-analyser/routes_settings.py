from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from report_store import add_report
from tools.noise_detector import classify_alerts
from tools.source import OpsgenieAPISource

router = APIRouter(prefix="/settings", tags=["settings"])

_config: dict = {
    "source_type": "file",
    "cloud_id": "",
    "email": "",
    "api_token": "",
    "last_synced": None,
    "alert_count": None,
}


class SettingsPayload(BaseModel):
    source_type: str = "file"
    cloud_id: str = ""
    email: str = ""
    api_token: str = ""


@router.get("")
async def get_settings() -> dict:
    return {k: v for k, v in _config.items() if k != "api_token"}


@router.post("")
async def save_settings(payload: SettingsPayload) -> dict:
    _config.update({
        "source_type": payload.source_type,
        "cloud_id": payload.cloud_id,
        "email": payload.email,
        "api_token": payload.api_token,
    })
    return {"ok": True}


@router.post("/sync")
async def sync_alerts() -> dict:
    if _config.get("source_type") != "opsgenie":
        raise HTTPException(status_code=400, detail="Source type must be 'opsgenie' to sync")

    for field in ("cloud_id", "email", "api_token"):
        if not _config.get(field):
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

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

    return {
        "ok": True,
        "alert_count": len(alerts),
        "last_synced": _config["last_synced"],
        "report": report,
    }
