#!/bin/sh
set -e

# Inject runtime env vars into the JS config file.
# BACKEND_URL and BACKEND_API_KEY must be set in the environment.
# If not set, defaults are used so the portal still loads in dev.
export BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
export BACKEND_API_KEY="${BACKEND_API_KEY:-}"

envsubst '${BACKEND_URL} ${BACKEND_API_KEY}' \
  < /etc/nginx/templates/config.template.js \
  > /usr/share/nginx/html/js/config.js

echo "Portal config written:"
echo "  BACKEND_URL      = $BACKEND_URL"
echo "  BACKEND_API_KEY  = ${BACKEND_API_KEY:+[set]}"

exec nginx -g "daemon off;"
