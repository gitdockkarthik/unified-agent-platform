from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import anthropic

from core.config import settings
from core.database import get_db
from core.security import require_api_key
from models.agent import Agent, AgentStatus

router = APIRouter(prefix="/api/platform", tags=["platform"])

_VERSION = "0.2.0"
_DEFAULT_MODEL = "claude-sonnet-4-6"


@router.get("/status", dependencies=[Depends(require_api_key)])
async def platform_status(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(
        select(func.count()).select_from(Agent).where(Agent.status == AgentStatus.published)
    )
    agent_count = result.scalar() or 0

    return {
        "anthropic_connected": bool(settings.anthropic_api_key),
        "agent_count": agent_count,
        "model": _DEFAULT_MODEL,
        "version": _VERSION,
    }


class TestAnthropicRequest(BaseModel):
    api_key: str


@router.post("/test-anthropic")
async def test_anthropic(body: TestAnthropicRequest) -> dict:
    """Test an Anthropic API key with a minimal call. No auth required (used by setup wizard)."""
    try:
        client = anthropic.AsyncAnthropic(api_key=body.api_key)
        await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            messages=[{"role": "user", "content": "Hi"}],
        )
        return {"success": True, "model": "claude-haiku-4-5-20251001"}
    except anthropic.AuthenticationError:
        return {"success": False, "error": "Invalid API key — check it and try again"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
