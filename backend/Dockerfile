# Build context must be the monorepo root so shared/ is accessible.
# docker-compose sets context: . and dockerfile: backend/Dockerfile
# Railway: set Root Directory to repo root, Dockerfile path to backend/Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# shared schemas used by backend and agents
COPY shared/ shared/

# backend source
COPY backend/ .

ENV PYTHONPATH=/app

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
