"""In-memory CUR report store — shared between routes_reports and routes_dashboard.

State is process-scoped and resets on restart. Suitable for single-instance
Railway deployment.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

_lock = threading.Lock()
_reports: list[dict[str, Any]] = []
_counter = 0


def add_report(filename: str, csv_text: str, row_count: int, total_cost: float, file_size: int) -> dict[str, Any]:
    global _counter
    with _lock:
        _counter += 1
        report: dict[str, Any] = {
            "id": _counter,
            "filename": filename,
            "_csv": csv_text,
            "row_count": row_count,
            "total_cost": round(total_cost, 4),
            "file_size": file_size,
            "status": "ready",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _reports.insert(0, report)
    return _public(report)


def list_reports() -> list[dict[str, Any]]:
    with _lock:
        return [_public(r) for r in _reports]


def get_latest_csv() -> str | None:
    with _lock:
        return _reports[0]["_csv"] if _reports else None


def get_latest_meta() -> dict[str, Any] | None:
    with _lock:
        return _public(_reports[0]) if _reports else None


def _public(r: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in r.items() if not k.startswith("_")}
