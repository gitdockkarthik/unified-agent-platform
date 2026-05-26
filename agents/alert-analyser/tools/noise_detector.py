import json
from datetime import datetime, timedelta
from typing import Any, ClassVar

from config import settings
from tools.base import ToolExecutor


# ── Core classification logic ─────────────────────────────────────────────────

def classify_alerts(alerts: list[dict]) -> list[dict]:
    """Classify each alert as noise or genuine using rule-based scoring.

    Scoring (thresholds read from settings / env vars):
      +2  alias fires >NOISE_THRESHOLD_REPEAT times within any 1-hour window
      +2  auto-closes in <NOISE_THRESHOLD_CLOSE_SECS seconds without acknowledgement
      +1  never acknowledged
      -3  priority is P1 or P2
      -2  open >1800 seconds
    classification = 'noise' if noise_score > 0 else 'genuine'
    """
    repeat_threshold: int = settings.noise_threshold_repeat
    close_secs_threshold: int = settings.noise_threshold_close_secs

    # Build alias → [datetime] map for sliding-window repeat detection
    alias_windows: dict[str, list[datetime]] = {}
    for alert in alerts:
        alias = alert.get("alias", "")
        try:
            created = datetime.fromisoformat(alert["createdAt"].replace("Z", ""))
        except Exception:
            created = datetime.utcnow()
        alias_windows.setdefault(alias, []).append(created)

    # Identify aliases that fire >repeat_threshold times in any 1-hour window
    frequent_aliases: set[str] = set()
    for alias, times in alias_windows.items():
        times_sorted = sorted(times)
        for i, t in enumerate(times_sorted):
            window_end = t + timedelta(hours=1)
            count_in_window = sum(1 for tt in times_sorted[i:] if tt <= window_end)
            if count_in_window > repeat_threshold:
                frequent_aliases.add(alias)
                break

    # Per-source auto-resolve rate (supplementary metadata, not used for scoring)
    source_stats: dict[str, dict[str, int]] = {}
    for alert in alerts:
        src = alert.get("source", "unknown")
        close_time = alert.get("report", {}).get("closeTime", 9999)
        auto_resolved = (
            close_time < close_secs_threshold and not alert.get("acknowledged", False)
        )
        s = source_stats.setdefault(src, {"total": 0, "auto_resolved": 0})
        s["total"] += 1
        if auto_resolved:
            s["auto_resolved"] += 1

    auto_resolve_rates: dict[str, float] = {
        src: round(v["auto_resolved"] / v["total"], 2) if v["total"] else 0.0
        for src, v in source_stats.items()
    }

    classified: list[dict] = []
    for alert in alerts:
        noise_score = 0
        noise_reasons: list[str] = []
        genuine_reasons: list[str] = []

        alias = alert.get("alias", "")
        src = alert.get("source", "unknown")
        close_time = alert.get("report", {}).get("closeTime", 9999)
        acknowledged = alert.get("acknowledged", False)
        priority = alert.get("priority", "P5")

        if alias in frequent_aliases:
            noise_score += 2
            noise_reasons.append(f"fires >{repeat_threshold}x within 1 hour")
        if close_time < close_secs_threshold and not acknowledged:
            noise_score += 2
            noise_reasons.append(f"auto-closes in <{close_secs_threshold}s without ACK")
        if not acknowledged:
            noise_score += 1
            noise_reasons.append("never acknowledged")
        if priority in ("P1", "P2"):
            noise_score -= 3
            genuine_reasons.append(f"{priority} priority")
        if close_time > 1800:
            noise_score -= 2
            genuine_reasons.append("open >1800s")

        classified.append(
            {
                **alert,
                "noise_score": noise_score,
                "classification": "noise" if noise_score > 0 else "genuine",
                "noise_reasons": noise_reasons,
                "genuine_reasons": genuine_reasons,
                "close_time_seconds": close_time,
                "auto_resolve_rate": auto_resolve_rates.get(src, 0.0),
            }
        )

    return classified


# ── ToolExecutor wrapper ──────────────────────────────────────────────────────

class NoiseDetectorTool(ToolExecutor):
    """Classify cached alerts as noise or genuine and return the split with scores."""

    name: ClassVar[str] = "classify_alerts"
    description: ClassVar[str] = (
        "Classify OpsGenie alerts as noise or genuine using rule-based scoring. "
        "Returns total counts, noise ratio percentage, and per-alert classification "
        "with noise_score, classification label, noise_reasons, and genuine_reasons."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "session_id": {
                "type": "string",
                "description": "Session whose cached alert data should be classified.",
            }
        },
        "required": ["session_id"],
    }

    def __init__(self, cache: dict[str, list[dict]]) -> None:
        self._cache = cache

    async def execute(self, session_id: str) -> str:  # type: ignore[override]
        alerts = self._cache.get(session_id, [])
        if not alerts:
            return json.dumps({"error": "No alert data loaded for this session."})

        classified = classify_alerts(alerts)
        noise = [a for a in classified if a["classification"] == "noise"]
        genuine = [a for a in classified if a["classification"] == "genuine"]
        total = len(classified)

        return json.dumps(
            {
                "total": total,
                "noise_count": len(noise),
                "genuine_count": len(genuine),
                "noise_ratio_pct": round(len(noise) / total * 100, 1) if total else 0,
                "noise": noise[:50],
                "genuine": genuine[:50],
            },
            default=str,
        )
