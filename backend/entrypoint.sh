#!/bin/sh
echo "PORT is: $PORT"
echo "All env vars:"
env
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
