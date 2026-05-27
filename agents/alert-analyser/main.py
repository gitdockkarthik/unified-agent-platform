import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Header
from pydantic import BaseModel, Field

from agent import AgentRunner
from config import settings
from routes_dashboard import router as dashboard_router
from routes_reports import router as reports_router
from routes_settings import router as settings_router
from tools.dashboard_builder import DashboardBuilderTool
from tools.noise_detector import NoiseDetectorTool
from tools.source import FileSource
from tools.suppression_advisor import SuppressionAdvisorTool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Alert cache ───────────────────────────────────────────────────────────────
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


# ── Self-registration ─────────────────────────────────────────────────────────


async def _register_self() -> None:
    if not settings.registry_url or not settings.backend_api_key:
        logger.info("Self-registration skipped: REGISTRY_URL or BACKEND_API_KEY not set")
        return

    manifest = json.loads((Path(__file__).parent / "manifest.json").read_text())
    headers = {"X-API-Key": settings.backend_api_key}
    base = settings.registry_url.rstrip("/")

    async with httpx.AsyncClient(timeout=10.0) as client:
        reg_resp = await client.post(
            f"{base}/api/registry/agents",
            json={
                "name": manifest["name"],
                "slug": manifest["slug"],
                "description": manifest.get("description", ""),
                "version": manifest.get("version", "0.1.0"),
                "invoke_url": manifest.get("invoke_url"),
                "tools": manifest.get("tools", []),
            },
            headers=headers,
        )

        if reg_resp.status_code == 201:
            agent_id = reg_resp.json()["id"]
            logger.info("Self-registration: registered as %s", agent_id)
        elif reg_resp.status_code == 409:
            list_resp = await client.get(f"{base}/api/registry/agents", headers=headers)
            list_resp.raise_for_status()
            match = next((a for a in list_resp.json() if a["slug"] == manifest["slug"]), None)
            if not match:
                logger.error("Self-registration: 409 conflict but slug not found in agent list")
                return
            agent_id = match["id"]
            logger.info("Self-registration: already registered as %s", agent_id)
        else:
            logger.error("Self-registration failed: %s — %s", reg_resp.status_code, reg_resp.text)
            return

        pub_resp = await client.post(f"{base}/api/registry/agents/{agent_id}/publish", headers=headers)
        if pub_resp.status_code == 200:
            logger.info("Self-registration: published successfully")
        else:
            logger.error("Self-registration publish failed: %s — %s", pub_resp.status_code, pub_resp.text)


# ── App ───────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await _register_self()
    except Exception:
        logger.exception("Self-registration raised an unexpected exception (agent will still start)")
    yield


app = FastAPI(title=settings.agent_name, version="0.1.0", lifespan=lifespan)
app.include_router(dashboard_router)
app.include_router(reports_router)
app.include_router(settings_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "agent": settings.agent_slug}


@app.post("/invoke", response_model=InvokeResponse)
async def invoke(
    body: InvokeRequest,
    x_anthropic_key: str | None = Header(default=None),
) -> InvokeResponse:
    ctx = body.context

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
