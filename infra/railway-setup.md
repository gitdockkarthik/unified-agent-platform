# Railway Deployment — Step-by-Step Setup Guide

This guide deploys the Unified Agent Platform to a **new** Railway project.
Do not reuse the existing `unified-ai-portal` project — keep them separate.

Prerequisites:
- Railway CLI installed: `npm i -g @railway/cli`
- Logged in: `railway login`
- This repo pushed to GitHub

---

## 1. Create a new Railway project

1. Open [railway.app](https://railway.app) → **New Project**.
2. Name it `unified-agent-platform`.
3. Do **not** deploy anything yet — you will add services manually in the steps below.

---

## 2. Add the PostgreSQL plugin

1. Inside the new project, click **New** → **Database** → **PostgreSQL**.
2. Railway provisions the database and auto-sets `DATABASE_URL`, `PGHOST`, `PGPORT`,
   `PGUSER`, `PGPASSWORD`, `PGDATABASE` on the postgres service itself.
3. You do **not** need to copy these — Railway injects them as reference variables
   (see Step 5 for how the backend wires to postgres).

---

## 3. Create one Railway service per folder

Create four services, in this order. For each: **New** → **GitHub Repo** →
select this repo → configure the settings below before deploying.

### 3a. backend

| Setting | Value |
|---|---|
| Service name | `backend` |
| Root Directory | `backend/` |
| Dockerfile Path | `Dockerfile` |
| Watch Paths | `**` |

Railway reads `backend/railway.toml` automatically for this service — but the
live file is `railway.toml` at the repo root (Railway uses whichever `railway.toml`
it finds in the configured Root Directory).

### 3b. alert-analyser

| Setting | Value |
|---|---|
| Service name | `alert-analyser` |
| Root Directory | `agents/alert-analyser/` |
| Dockerfile Path | `Dockerfile` |

Railway reads `agents/alert-analyser/railway.toml` automatically.

### 3c. cur-analyser

| Setting | Value |
|---|---|
| Service name | `cur-analyser` |
| Root Directory | `agents/cur-analyser/` |
| Dockerfile Path | `Dockerfile` |

Railway reads `agents/cur-analyser/railway.toml` automatically.

### 3d. portal

| Setting | Value |
|---|---|
| Service name | `portal` |
| Root Directory | `portal/` |
| Dockerfile Path | `Dockerfile` |

Railway reads `portal/railway.toml` automatically.

> **Do not click Deploy yet for any service.** Set all env vars first (Step 4).

---

## 4. Set env vars in Railway dashboard

Open each service → **Variables** tab. Set exactly the variables listed below.
Never set a variable that belongs to a different service.

### postgres (Railway-managed — no manual vars needed)

Railway auto-provides connection variables. You will reference them from the
backend using Railway's `${{Postgres.DATABASE_URL}}` reference syntax (Step 5).

### backend

| Variable | Value | Notes |
|---|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | Railway reference — auto-resolves to the postgres plugin URL |
| `ANTHROPIC_API_KEY` | `sk-ant-api03-...` | Your Anthropic key — only the backend holds this |
| `BACKEND_API_KEY` | *(random 32+ char string)* | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `SECRET_KEY` | *(random 64-char hex)* | Same generator as above |
| `CORS_ORIGINS` | `https://portal-<hash>.up.railway.app` | Portal's public URL (fill in after portal is created) |

### alert-analyser

| Variable | Value | Notes |
|---|---|---|
| `AGENT_ID` | *(leave blank)* | Filled in after `make register` (Step 7) |
| `AGENT_SLUG` | `alert-analyser` | |
| `AGENT_NAME` | `Alert Analyser` | |
| `MODEL` | `claude-sonnet-4-6` | Override to use a different model |
| `NOISE_THRESHOLD_REPEAT` | `3` | Alerts firing >N times in 1 h = noise |
| `NOISE_THRESHOLD_CLOSE_SECS` | `300` | Auto-close in <N seconds = noise |

> **No ANTHROPIC_API_KEY here.** The backend injects it via `X-Anthropic-Key`
> header on every `/invoke` call.

### cur-analyser

| Variable | Value | Notes |
|---|---|---|
| `AGENT_ID` | *(leave blank)* | Filled in after `make register` (Step 7) |
| `AGENT_SLUG` | `cur-analyser` | |
| `AGENT_NAME` | `CUR Analyser` | |
| `MODEL` | `claude-sonnet-4-6` | |

> **No ANTHROPIC_API_KEY here** — same reason as alert-analyser.

### portal

| Variable | Value | Notes |
|---|---|---|
| `BACKEND_URL` | `http://backend.railway.internal:${{backend.PORT}}` | Railway private network URL |
| `BACKEND_API_KEY` | *(same value as backend's BACKEND_API_KEY)* | Copied from the backend service |

> The portal knows only `BACKEND_URL` and `BACKEND_API_KEY`. No Anthropic key,
> no database URL, no agent URLs.

---

## 5. Wire services using Railway private networking

Railway services in the same project communicate over a private network without
going through the public internet. Use these hostnames:

| Caller | Target | Private URL |
|---|---|---|
| backend | postgres | `${{Postgres.DATABASE_URL}}` (reference var, auto-resolved) |
| backend → portal request | — | portal has no inbound from backend |
| portal | backend | `http://backend.railway.internal:${{backend.PORT}}` |
| backend orchestrator | alert-analyser | `http://alert-analyser.railway.internal:${{alert-analyser.PORT}}` |
| backend orchestrator | cur-analyser | `http://cur-analyser.railway.internal:${{cur-analyser.PORT}}` |

> **Important:** The `invoke_url` you register for each agent (Step 7) must use
> the Railway private URL, not the public one. The backend calls agents
> internally — they do not need public endpoints.

---

## 6. Deploy in order

Deploy services one at a time and wait for each to show **Active** before
proceeding.

### Step 6a — postgres

Already running (Railway auto-deployed it in Step 2). Verify it shows **Active**.

### Step 6b — backend

1. In Railway: select the `backend` service → **Deploy**.
2. Watch the build log — it should pip install, copy `shared/`, and start uvicorn.
3. Once Active, open a one-off shell and run Alembic migrations:

   ```bash
   # From your local machine, using Railway CLI:
   railway run --service backend alembic upgrade head
   ```

   Or use Railway's **Shell** tab in the dashboard and run:
   ```bash
   alembic upgrade head
   ```

4. Confirm: `GET https://backend-<hash>.up.railway.app/api/health` → `{"status":"ok"}`.

### Step 6c — alert-analyser

1. Deploy the `alert-analyser` service.
2. Confirm: `GET https://alert-analyser-<hash>.up.railway.app/health` → `{"status":"ok","agent":"alert-analyser"}`.

### Step 6d — cur-analyser

1. Deploy the `cur-analyser` service.
2. Confirm: `GET https://cur-analyser-<hash>.up.railway.app/health` → `{"status":"ok","agent":"cur-analyser"}`.

### Step 6e — portal

1. Deploy the `portal` service.
2. Confirm: `GET https://portal-<hash>.up.railway.app/healthz` → `ok`.
3. Copy the portal's public URL and update `CORS_ORIGINS` on the backend service.
   Railway will redeploy the backend automatically.

---

## 7. Seed both agents into the registry

Once backend is live, run `make register` pointed at the production backend.
This registers and publishes both agents so the portal can discover them.

```bash
# Point make register at the live backend
BACKEND_URL=https://backend-<hash>.up.railway.app \
BACKEND_API_KEY=<your-backend-api-key> \
  make register
```

Expected output:
```
[ok]   alert-analyser registered → <uuid>
[ok]   alert-analyser published
[ok]   cur-analyser registered → <uuid>
[ok]   cur-analyser published
```

After `make register` completes, copy the two UUIDs printed and set them as
`AGENT_ID` in the `alert-analyser` and `cur-analyser` Railway services.
(This allows each agent to self-identify in future health payloads.)

Update the `invoke_url` for each agent to use the Railway private URL:

```bash
# Update alert-analyser invoke_url to the private network address
curl -sX PUT https://backend-<hash>.up.railway.app/api/registry/agents/<alert-analyser-uuid> \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-backend-api-key>" \
  -d '{"invoke_url": "http://alert-analyser.railway.internal:8001"}'

# Update cur-analyser invoke_url
curl -sX PUT https://backend-<hash>.up.railway.app/api/registry/agents/<cur-analyser-uuid> \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-backend-api-key>" \
  -d '{"invoke_url": "http://cur-analyser.railway.internal:8002"}'
```

---

## 8. Smoke test

### 8a. Open the portal

Navigate to `https://portal-<hash>.up.railway.app`.

**Expected:** The agent catalogue page loads and shows two cards:
- **Alert Analyser** — capabilities: alert-triage, noise-classification, suppression-recommendations, trend-analysis
- **CUR Analyser** — capabilities: cost-breakdown, trend-analysis, anomaly-detection, savings-recommendations

If cards are missing, check that `make register` completed successfully and that
`BACKEND_URL` in the portal is pointing to the correct backend URL.

### 8b. Chat with Alert Analyser

1. Click **Alert Analyser** → **Chat**.
2. Send: `"What types of alerts do you classify as noise?"`
3. **Expected:** Claude responds explaining the noise classification rules
   (fires >3× in 1 h, auto-closes in <300s, never acknowledged, etc.).

### 8c. Chat with CUR Analyser

1. Click **CUR Analyser** → **Chat**.
2. Send: `"What CUR columns do you use for cost analysis?"`
3. **Expected:** Claude responds describing `line_item_unblended_cost`,
   `line_item_product_code`, `line_item_usage_start_date`, etc.

### 8d. Full invoke smoke test (CLI)

```bash
# Test full chain through production backend
make test \
  BACKEND_URL=https://backend-<hash>.up.railway.app \
  BACKEND_API_KEY=<your-backend-api-key>
```

Both agents should return non-empty `response` fields. Any `502` or `504` means
the backend cannot reach the agent over the private network — recheck Step 5.

---

## Troubleshooting

| Symptom | Check |
|---|---|
| Backend build fails | Confirm Root Directory is `/` (not `backend/`) |
| `shared/` not found | Same root directory issue — Dockerfile path must be `backend/Dockerfile` with root `/` |
| Agent returns 500 on invoke | Missing `X-Anthropic-Key` — verify backend has `ANTHROPIC_API_KEY` set |
| Portal shows empty catalogue | `CORS_ORIGINS` on backend doesn't include the portal URL |
| `make register` returns 403 | `BACKEND_API_KEY` mismatch between backend service and your local env |
| Private URL unreachable | Services must be in the same Railway project; different projects cannot use `.railway.internal` |
| Migration fails | Run `railway run --service backend alembic upgrade head` after backend is Active |
