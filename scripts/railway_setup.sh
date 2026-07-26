#!/usr/bin/env bash
# Configure the Railway service: persistent volume + required variables.
#
# Auth first (interactive, needs your terminal — a TTY is required):
#   railway login                      # sign in as falgunitripathi
# or, non-interactively, create a project token in the Railway dashboard
# (Project → Settings → Tokens) and:
#   export RAILWAY_TOKEN=<token>
#
# Then run this script. It is idempotent: re-running only fills in what is missing.
set -euo pipefail

PROJECT="${PROJECT:-c7dde329-6a33-4e50-ac61-e098961076ba}"
ENVIRONMENT="${ENVIRONMENT:-af87ac2a-dd2f-4e19-a3b3-42141ddc93c0}"
SERVICE="${SERVICE:-f9027eba-6907-4479-9233-30db6a8979e7}"
MOUNT="${MOUNT:-/data}"

RAILWAY="${RAILWAY:-$HOME/.hermes/node/bin/railway}"
command -v "$RAILWAY" >/dev/null 2>&1 || RAILWAY=railway

echo "==> whoami"
"$RAILWAY" whoami

echo "==> linking project"
"$RAILWAY" link --project "$PROJECT" --environment "$ENVIRONMENT" --service "$SERVICE"

echo "==> adding volume at $MOUNT (skip if it already exists)"
"$RAILWAY" volume add --mount-path "$MOUNT" || echo "    volume already present, continuing"

echo "==> setting variables"
# the catalog lives on the volume so visitor-submitted analyses survive a redeploy
"$RAILWAY" variables --set "CUTSENSE_DB=${MOUNT}/cutsense.sqlite"
# VIDEO_DB_API_KEY is a secret: set it yourself rather than committing it here
if [ -n "${VIDEO_DB_API_KEY:-}" ]; then
  "$RAILWAY" variables --set "VIDEO_DB_API_KEY=${VIDEO_DB_API_KEY}"
else
  echo "    VIDEO_DB_API_KEY not exported — set it in the dashboard or:"
  echo "    railway variables --set VIDEO_DB_API_KEY=sk-..."
fi

echo "==> current variables"
"$RAILWAY" variables

echo "==> deploying"
"$RAILWAY" up --detach

echo "==> done. Generate a public domain if the service has none:"
echo "    railway domain"
