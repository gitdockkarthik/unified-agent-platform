from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from agent import AgentRunner
from config import settings
from tools.echo import EchoTool

# ── Register tools ────────────────────────────────────────────────────────────
# Add or remove ToolExecutor instances here. Pass an empty list to disable
# tool use entirely (Claude will only respond with text).
_runner = AgentRunner(tools=[EchoTool()])

# ── Schemas ───────────────────────────────────────────────────────────────────
# Defined locally so this service is fully self-contained with no dependency
# on the monorepo's shared/ package.


class InvokeRequest(BaseModel):
    session_id: str
    user_message: str
    context: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list)


class InvokeResponse(BaseModel):
    response: str
    session_id: str
    agent_id: str
    tokens_used: int


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title=settings.agent_name, version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "agent": settings.agent_slug}


@app.post("/invoke", response_model=InvokeResponse)
async def invoke(body: InvokeRequest) -> InvokeResponse:
    response_text, tokens = await _runner.run(
        user_message=body.user_message,
        context=body.context,
        history=body.history,
    )
    return InvokeResponse(
        response=response_text,
        session_id=body.session_id,
        agent_id=settings.agent_id,
        tokens_used=tokens,
    )
