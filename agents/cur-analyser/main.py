import json
from typing import Any

from fastapi import FastAPI, Header
from pydantic import BaseModel, Field

from agent import AgentRunner
from config import settings
from tools.dashboard_builder import DashboardBuilderTool
from tools.duckdb_engine import CurQueryTool
from tools.source import FileSource

# ── CUR CSV cache ─────────────────────────────────────────────────────────────
# Keyed by session_id. Populated at invoke time from context so both tools can
# query the same CSV text without re-loading on every tool call.
_cur_cache: dict[str, str] = {}

# ── Agent setup ───────────────────────────────────────────────────────────────
_runner = AgentRunner(
    tools=[
        CurQueryTool(_cur_cache),
        DashboardBuilderTool(_cur_cache),
    ]
)

# ── Schemas ───────────────────────────────────────────────────────────────────


class InvokeRequest(BaseModel):
    session_id: str
    user_message: str
    context: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list)


class InvokeResponse(BaseModel):
    session_id: str
    response: str
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title=settings.agent_name, version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "agent": settings.agent_slug}


@app.post("/invoke", response_model=InvokeResponse)
async def invoke(
    body: InvokeRequest,
    x_anthropic_key: str | None = Header(default=None),
) -> InvokeResponse:
    ctx = body.context

    # Load CUR CSV into cache for this session
    if "raw_data" in ctx:
        source = FileSource(ctx["raw_data"])
        _cur_cache[body.session_id] = await source.load_csv()
    elif "cur_csv" in ctx:
        _cur_cache[body.session_id] = ctx["cur_csv"]

    has_data = bool(_cur_cache.get(body.session_id))

    response_text, tokens = await _runner.run(
        user_message=body.user_message,
        context={"session_id": body.session_id, "has_data": has_data},
        history=body.history,
        api_key=x_anthropic_key,
    )

    # Extract optional chart block embedded in Claude's response
    chart_data = None
    if "```chart" in response_text:
        try:
            start = response_text.index("```chart") + 8
            end = response_text.index("```", start)
            chart_data = json.loads(response_text[start:end].strip())
            response_text = response_text[: response_text.index("```chart")].strip()
        except Exception:
            pass

    metadata: dict[str, Any] = {"tokens_used": tokens}
    if chart_data is not None:
        metadata["chart"] = chart_data

    return InvokeResponse(
        session_id=body.session_id,
        response=response_text,
        metadata=metadata,
    )
