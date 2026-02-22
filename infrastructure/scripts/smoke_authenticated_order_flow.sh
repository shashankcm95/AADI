#!/usr/bin/env bash

set -euo pipefail

if [ "$#" -lt 3 ]; then
  echo "Usage: $0 <ORDERS_API_URL> <RESTAURANTS_API_URL> <ID_TOKEN>"
  exit 1
fi

ORDERS_API_URL="${1%/}"
RESTAURANTS_API_URL="${2%/}"
ID_TOKEN="$3"

if [ -z "$ID_TOKEN" ] || [ "$ID_TOKEN" = "None" ]; then
  echo "ERROR: Missing or invalid ID token."
  exit 1
fi

request() {
  local method="$1"
  local url="$2"
  local body="${3:-}"

  if [ -n "$body" ]; then
    curl -sS -X "$method" "$url" \
      -H "Authorization: Bearer $ID_TOKEN" \
      -H "Content-Type: application/json" \
      -H "Idempotency-Key: smoke-$(date +%s)-$RANDOM" \
      -d "$body" \
      -w "\n%{http_code}"
  else
    curl -sS -X "$method" "$url" \
      -H "Authorization: Bearer $ID_TOKEN" \
      -w "\n%{http_code}"
  fi
}

parse_body() {
  printf '%s\n' "$1" | sed '$d'
}

parse_status() {
  printf '%s\n' "$1" | tail -n1
}

extract_json_field() {
  local body="$1"
  local expr="$2"
  python3 - "$body" "$expr" <<'PY'
import json
import sys

payload = sys.argv[1]
expr = sys.argv[2]

try:
    data = json.loads(payload) if payload else {}
except Exception:
    print("")
    raise SystemExit(0)

if expr == "first_restaurant_id":
    restaurants = data.get("restaurants") if isinstance(data, dict) else None
    if isinstance(restaurants, list) and restaurants:
        first = restaurants[0] if isinstance(restaurants[0], dict) else {}
        print(str(first.get("restaurant_id") or first.get("destination_id") or "").strip())
    else:
        print("")
elif expr == "order_id":
    if isinstance(data, dict):
        print(str(data.get("order_id") or data.get("session_id") or "").strip())
    else:
        print("")
else:
    print("")
PY
}

assert_status() {
  local status="$1"
  local expected="$2"
  local label="$3"
  local body="$4"
  if [ "$status" != "$expected" ]; then
    echo "ERROR: $label failed. Expected HTTP $expected, got $status"
    echo "Response body: $body"
    exit 1
  fi
}

echo "Running authenticated smoke flow against:"
echo "  Orders API: $ORDERS_API_URL"
echo "  Restaurants API: $RESTAURANTS_API_URL"

RESTAURANTS_RESP="$(request GET "$RESTAURANTS_API_URL/v1/restaurants")"
RESTAURANTS_BODY="$(parse_body "$RESTAURANTS_RESP")"
RESTAURANTS_STATUS="$(parse_status "$RESTAURANTS_RESP")"
assert_status "$RESTAURANTS_STATUS" "200" "List restaurants" "$RESTAURANTS_BODY"

RESTAURANT_ID="$(extract_json_field "$RESTAURANTS_BODY" "first_restaurant_id")"
if [ -z "$RESTAURANT_ID" ]; then
  echo "ERROR: Could not determine restaurant_id from restaurants response."
  echo "Response body: $RESTAURANTS_BODY"
  exit 1
fi

CREATE_PAYLOAD="$(python3 - "$RESTAURANT_ID" <<'PY'
import json
import sys

restaurant_id = sys.argv[1]
print(json.dumps({
    "restaurant_id": restaurant_id,
    "customer_name": "CI Smoke",
    "items": [{"id": "ci-smoke-item", "qty": 1, "price_cents": 100}]
}))
PY
)"

CREATE_RESP="$(request POST "$ORDERS_API_URL/v1/orders" "$CREATE_PAYLOAD")"
CREATE_BODY="$(parse_body "$CREATE_RESP")"
CREATE_STATUS="$(parse_status "$CREATE_RESP")"
assert_status "$CREATE_STATUS" "201" "Create order" "$CREATE_BODY"

ORDER_ID="$(extract_json_field "$CREATE_BODY" "order_id")"
if [ -z "$ORDER_ID" ]; then
  echo "ERROR: Could not determine order_id from create-order response."
  echo "Response body: $CREATE_BODY"
  exit 1
fi

GET_RESP="$(request GET "$ORDERS_API_URL/v1/orders/$ORDER_ID")"
GET_BODY="$(parse_body "$GET_RESP")"
GET_STATUS="$(parse_status "$GET_RESP")"
assert_status "$GET_STATUS" "200" "Get order" "$GET_BODY"

VICINITY_RESP="$(request POST "$ORDERS_API_URL/v1/orders/$ORDER_ID/vicinity" '{"event":"EXIT_VICINITY"}')"
VICINITY_BODY="$(parse_body "$VICINITY_RESP")"
VICINITY_STATUS="$(parse_status "$VICINITY_RESP")"
assert_status "$VICINITY_STATUS" "200" "Vicinity update (EXIT_VICINITY)" "$VICINITY_BODY"

NOW_SECONDS="$(date +%s)"
LOCATION_PAYLOAD="$(python3 - "$NOW_SECONDS" <<'PY'
import json
import sys

sample_time = int(sys.argv[1])
print(json.dumps({
    "latitude": 30.2672,
    "longitude": -97.7431,
    "accuracy_m": 15,
    "speed_mps": 0.0,
    "sample_time": sample_time
}))
PY
)"

LOCATION_RESP="$(request POST "$ORDERS_API_URL/v1/orders/$ORDER_ID/location" "$LOCATION_PAYLOAD")"
LOCATION_BODY="$(parse_body "$LOCATION_RESP")"
LOCATION_STATUS="$(parse_status "$LOCATION_RESP")"
assert_status "$LOCATION_STATUS" "202" "Location ingest" "$LOCATION_BODY"

ADVISORY_RESP="$(request GET "$ORDERS_API_URL/v1/orders/$ORDER_ID/advisory")"
ADVISORY_BODY="$(parse_body "$ADVISORY_RESP")"
ADVISORY_STATUS="$(parse_status "$ADVISORY_RESP")"
assert_status "$ADVISORY_STATUS" "200" "Leave advisory" "$ADVISORY_BODY"

echo "Authenticated smoke flow passed for order_id=$ORDER_ID restaurant_id=$RESTAURANT_ID"
