#!/usr/bin/env bash

set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 <API_URL> <ROUTE_KEY_1> [ROUTE_KEY_2 ...]"
  echo "Example: $0 https://abc123.execute-api.us-east-1.amazonaws.com 'POST /v1/orders/{order_id}/location'"
  exit 1
fi

API_URL="$1"
shift

HOST="$(echo "$API_URL" | sed -E 's#https?://([^/]+)/?.*#\1#')"
API_ID="${HOST%%.*}"

if [ -z "$API_ID" ] || [ "$API_ID" = "$HOST" ]; then
  echo "ERROR: Failed to parse API id from URL: $API_URL"
  exit 1
fi

ROUTES_RAW="$(aws apigatewayv2 get-routes --api-id "$API_ID" --query 'Items[].RouteKey' --output text)"
ROUTES="$(echo "$ROUTES_RAW" | tr '\t' '\n' | sed '/^$/d')"

echo "Checking route contract for API $API_ID ($API_URL)"
echo "Discovered routes:"
echo "$ROUTES"

MISSING=0
for REQUIRED_ROUTE in "$@"; do
  if ! printf '%s\n' "$ROUTES" | grep -Fxq "$REQUIRED_ROUTE"; then
    echo "ERROR: Missing required route: $REQUIRED_ROUTE"
    MISSING=1
  fi
done

if [ "$MISSING" -ne 0 ]; then
  exit 1
fi

echo "Route contract check passed."
