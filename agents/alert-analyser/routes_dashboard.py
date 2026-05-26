from fastapi import APIRouter

from report_store import get_latest_classified, get_latest_meta
from tools.noise_detector import compute_dashboard_stats

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
async def get_dashboard() -> dict:
    """Return computed stats for the most recently uploaded/generated report."""
    classified = get_latest_classified()
    if classified is None:
        return {"empty": True}
    return {
        "stats": compute_dashboard_stats(classified),
        "report": get_latest_meta(),
    }
