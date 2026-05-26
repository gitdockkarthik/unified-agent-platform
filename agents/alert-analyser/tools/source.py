import csv
import io
import json
from abc import ABC, abstractmethod


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
    """Phase 2 stub — live OpsGenie API feed (not yet implemented)."""

    def __init__(self, api_key: str, team: str | None = None) -> None:
        self._api_key = api_key
        self._team = team

    async def load_alerts(self) -> list[dict]:
        raise NotImplementedError("OpsGenie live feed is not yet implemented (Phase 2).")
