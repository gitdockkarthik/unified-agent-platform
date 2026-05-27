import base64
import csv
import io
import json
from abc import ABC, abstractmethod
from datetime import datetime


class AlertSource(ABC):
    @abstractmethod
    async def load_alerts(self) -> list[dict]:
        ...


class FileSource(AlertSource):
    """Reads alert data from an uploaded CSV or JSON string (stored in DB as TEXT)."""

    def __init__(self, raw_data: str, fmt: str = "json") -> None:
        self._raw_data = raw_data
        self._fmt = fmt.lower()

    async def load_alerts(self) -> list[dict]:
        if self._fmt == "csv":
            reader = csv.DictReader(io.StringIO(self._raw_data))
            return [dict(row) for row in reader]
        return json.loads(self._raw_data)


class OpsgenieAPISource(AlertSource):
    """Fetches live alerts from the Atlassian JSM Ops API and maps them to internal format."""

    def __init__(self, cloud_id: str, email: str, api_token: str) -> None:
        self._cloud_id = cloud_id
        self._email = email
        self._api_token = api_token

    async def load_alerts(self) -> list[dict]:
        import httpx

        url = f"https://api.atlassian.com/jsm/ops/api/{self._cloud_id}/v1/alerts?limit=100"
        credentials = base64.b64encode(f"{self._email}:{self._api_token}".encode()).decode()
        headers = {
            "Authorization": f"Basic {credentials}",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        raw_alerts = data.get("values", data) if isinstance(data, dict) else data
        return [self._map(a) for a in raw_alerts]

    def _map(self, a: dict) -> dict:
        created_at = a.get("createdAt", "")
        updated_at = a.get("updatedAt", "")
        status = a.get("status", "")

        close_time = 0
        if status == "closed" and created_at and updated_at:
            try:
                created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                close_time = max(0, int((updated - created).total_seconds()))
            except Exception:
                pass

        responders = a.get("responders", [])
        teams = [
            r.get("name", str(r)) if isinstance(r, dict) else str(r)
            for r in responders
        ]

        return {
            "id": a.get("id", ""),
            "alias": a.get("alias", a.get("id", "")),
            "message": a.get("message", ""),
            "status": status,
            "priority": a.get("priority", "P5"),
            "source": a.get("source", "unknown"),
            "createdAt": created_at,
            "acknowledged": a.get("acknowledged", False),
            "count": a.get("count", 1),
            "teams": teams[:1] or ["Unknown"],
            "report": {"closeTime": close_time},
        }
