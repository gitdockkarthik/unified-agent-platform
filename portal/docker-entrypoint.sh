#!/bin/sh
set -e

# ── Runtime defaults ──────────────────────────────────────────────────────────
export BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
export BACKEND_API_KEY="${BACKEND_API_KEY:-}"
export PORT="${PORT:-80}"

# ── Step 1: inject JS config ──────────────────────────────────────────────────
envsubst '${BACKEND_URL} ${BACKEND_API_KEY}' \
  < /etc/nginx/templates/config.template.js \
  > /usr/share/nginx/html/js/config.js

# ── Step 2: inject PORT into nginx conf ───────────────────────────────────────
# Scope envsubst to $PORT only — nginx uses $uri, $request_uri, etc. which must
# not be expanded.
envsubst '${PORT}' \
  < /etc/nginx/templates/nginx.conf.template \
  > /etc/nginx/conf.d/default.conf

echo "Portal entrypoint complete:"
echo "  BACKEND_URL = $BACKEND_URL"
echo "  BACKEND_API_KEY = ${BACKEND_API_KEY:+[set]}"
echo "  PORT = $PORT"

exec nginx -g "daemon off;"
