import json
from typing import Any

from fastapi import FastAPI, Header
from pydantic import BaseModel, Field

from agent import AgentRunner
from config import settings
from tools.dashboard_builder import DashboardBuilderTool
from tools.noise_detector import NoiseDetectorTool
from tools.source import FileSource
from tools.suppression_advisor import SuppressionAdvisorTool

# ── Alert cache ───────────────────────────────────────────────────────────────
# Keyed by session_id. Populated at invoke time from context so all tools can
# read the alert data without re-loading on every tool call.
_alert_cache: dict[str, list[dict]] = {}

# ── Agent setup ───────────────────────────────────────────────────────────────
_runner = AgentRunner(
    tools=[
        NoiseDetectorTool(_alert_cache),
        DashboardBuilderTool(_alert_cache),
        SuppressionAdvisorTool(_alert_cache),
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

    # Load alert data into cache for this session
    if "raw_data" in ctx:
        source = FileSource(ctx["raw_data"], ctx.get("format", "json"))
        _alert_cache[body.session_id] = await source.load_alerts()
    elif "alerts" in ctx:
        _alert_cache[body.session_id] = ctx["alerts"]

    has_data = bool(_alert_cache.get(body.session_id))
    alert_count = len(_alert_cache.get(body.session_id, []))

    response_text, tokens = await _runner.run(
        user_message=body.user_message,
        context={"session_id": body.session_id, "has_data": has_data, "alert_count": alert_count},
        history=body.history,
        api_key=x_anthropic_key,
    )

    # Extract optional chart block from response text
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
