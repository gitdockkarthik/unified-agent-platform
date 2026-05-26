from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from core.config import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


async def require_api_key(api_key: str = Security(_api_key_header)) -> None:
    if api_key != settings.backend_api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
