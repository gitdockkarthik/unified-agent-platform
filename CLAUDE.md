# Unified Agent Platform

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, Python 3.11 |
| Database | PostgreSQL (async via asyncpg + SQLAlchemy 2) |
| Migrations | Alembic |
| AI | Anthropic SDK (claude-sonnet-4-6 default) |
| Portal | Vanilla HTML + CSS + JS — no framework, no build step |
| Infra | Docker Compose (local), Railway (production) |

## Repository Layout

```
unified-agent-platform/
├── backend/        # FastAPI app — agent registry + orchestration
├── portal/         # Static frontend — no framework, no build step
├── agents/         # One subfolder per agent, each is a standalone FastAPI service
├── shared/         # Shared Pydantic schemas and AgentManifest model
└── infra/          # Docker configs, Railway config, future K8s manifests
```

## Python Conventions

- `async`/`await` everywhere — no sync DB calls, no sync HTTP calls
- All models typed with Pydantic v2 (`model_config`, not `class Config`)
- App settings via `pydantic-settings` — `Settings` class reads from env
- All credentials from env vars only — **never hardcoded**
- Use `httpx.AsyncClient` for outbound HTTP (agent invocations)
- SQLAlchemy 2 declarative style with `DeclarativeBase`

## Agent Contract

Every agent exposes exactly two endpoints:

```
GET  /health          → {"status": "ok"}
POST /invoke          → InvokeRequest → InvokeResponse
```

### InvokeRequest body

```json
{
  "session_id": "string",
  "user_message": "string",
  "context": {},
  "history": [{"role": "user|assistant", "content": "string"}]
}
```

### InvokeResponse body

```json
{
  "session_id": "string",
  "response": "string",
  "metadata": {}
}
```

Schemas are defined once in `shared/schemas.py` and imported by both the backend and each agent.

## Agent Design Rules

- **Stateless** — no internal state; all context is injected per request via `context` and `history`
- **Standalone** — each agent is a complete FastAPI app that can be deployed independently
- **Plugin model** — agent repos are delivered as standalone repos to clients; the platform discovers them via `manifest.json`
- **Named by product** — agent folders use kebab-case product names (e.g. `alert-analyser`, `cur-analyser`)

## Agent Manifest

Each agent ships a `manifest.json` at its root:

```json
{
  "name": "Alert Analyser",
  "slug": "alert-analyser",
  "description": "Analyses cloud infrastructure alerts and suggests remediation",
  "version": "0.1.0",
  "invoke_url": "http://alert-analyser:8001",
  "capabilities": ["alert-triage", "root-cause-analysis"]
}
```

The backend registry reads this manifest when an agent registers itself on startup.

## Environment Variables

All required vars are documented in `.env.example`. Never commit `.env`.

## Deployment

- **Railway** is the permanent production platform — it is never decommissioned
- Each service (backend + each agent) is a separate Railway service within one project
- `infra/railway.toml` defines the project topology

## Local Development

```bash
make dev        # spin up postgres + backend via docker compose
make migrate    # run alembic migrations inside the backend container
make test       # run pytest inside the backend container
make logs       # tail compose logs
```
