"""In-memory CUR report store — shared between routes_reports and routes_dashboard.

State is process-scoped and resets on restart. Suitable for single-instance
Railway deployment.
"""
from __future__ import annotations

import csv
import io
import threading
from datetime import datetime, timezone
from typing import Any

_lock = threading.Lock()
_reports: list[dict[str, Any]] = []
_counter = 0


def _parse_rows(csv_text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(csv_text))
    return [dict(row) for row in reader]


def add_report(filename: str, csv_text: str, row_count: int, total_cost: float, file_size: int) -> dict[str, Any]:
    global _counter
    rows = _parse_rows(csv_text)
    with _lock:
        _counter += 1
        report: dict[str, Any] = {
            "id": _counter,
            "filename": filename,
            "_csv": csv_text,
            "_rows": rows,
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


def get_report_rows(report_id: int) -> list[dict[str, str]] | None:
    with _lock:
        for r in _reports:
            if r["id"] == report_id:
                return r["_rows"]
        return None


def get_latest_csv() -> str | None:
    with _lock:
        return _reports[0]["_csv"] if _reports else None


def get_latest_meta() -> dict[str, Any] | None:
    with _lock:
        return _public(_reports[0]) if _reports else None


def _public(r: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in r.items() if not k.startswith("_")}
