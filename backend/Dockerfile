FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Build context is backend/ — no shared/ dependency after inlining InvokeRequest/InvokeResponse
# into orchestrator/schemas.py.
COPY . .

ENV PYTHONPATH=/app

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
# Railway deploy Tue May 26 16:20:27 IST 2026
