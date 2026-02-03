#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

# -----------------------------
# Config (override via env)
# -----------------------------
API="${API:-http://127.0.0.1:3000}"
RID="${RID:-rst_001}"

CFG_TABLE="${CFG_TABLE:-arrive-dev-RestaurantConfigTable-4CJXU663PPYC}"
ORDERS_TABLE="${ORDERS_TABLE:-arrive-dev-OrdersTable-1NZGZZ1LUTWVV}"
CAPACITY_TABLE="${CAPACITY_TABLE:-arrive-dev-CapacityTable-P79F5A2T9RZ3}"
IDEMPOTENCY_TABLE="${IDEMPOTENCY_TABLE:-arrive-dev-IdempotencyTable-VUBEBNT8L1N6}"


ITEM_ID="${ITEM_ID:-it_001}"
ITEM_NAME="${ITEM_NAME:-Turkey Sandwich}"
PRICE_CENTS="${PRICE_CENTS:-1099}"
PREP_UNITS="${PREP_UNITS:-2}"
CAP_TABLE="${CAP_TABLE:-arrive-dev-CapacityTable-P79F5A2T9RZ3}"
WINDOW_SECONDS="${WINDOW_SECONDS:-600}"

fail() {
  echo "❌ FAIL: $*" >&2
  exit 1
}

pass() {
  echo "✅ PASS: $*"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

json_get() {
  # usage: json_get '<json>' '<key>'
  python3 - "$2" <<'PY'
import json, sys
key = sys.argv[1]
data = json.loads(sys.stdin.read())
if key not in data:
    raise SystemExit(2)
print(data[key])
PY
}

http_get() {
  curl -sS "$1"
}

http_post_json() {
  local url="$1"
  local body="$2"
  curl -sS -X POST "$url" -H "Content-Type: application/json" -d "$body"
}

http_post_json_with_header() {
  local url="$1"
  local header="$2"
  local body="$3"
  curl -sS -X POST "$url" -H "Content-Type: application/json" -H "$header" -d "$body"
}

http_post_json_with_header_i() {
  local url="$1"
  local header="$2"
  local body="$3"
  curl -sS -i -X POST "$url" -H "Content-Type: application/json" -H "$header" -d "$body"
}

http_post_json_i() {
  # prints headers + body (curl -i)
  local url="$1"
  local body="$2"
  curl -sS -i -X POST "$url" -H "Content-Type: application/json" -d "$body"
}

http_status() {
  # usage: http_status "$raw"
  echo "$1" | head -n 1 | tr -d '\r' | awk '{print $2}'
}

http_body() { 
  # usage: http_body "$raw"
  # strip headers
  echo "$1" | tr -d '\r' | awk 'BEGIN{h=1} { if(h && $0=="") {h=0; next} if(!h) print }'
}


set_capacity() {
  local max="$1"
  aws dynamodb update-item \
    --table-name "$CFG_TABLE" \
    --key "{\"restaurant_id\":{\"S\":\"$RID\"}}" \
    --update-expression "SET max_prep_units_per_window = :m" \
    --expression-attribute-values "{\":m\":{\"N\":\"$max\"}}" >/dev/null
}

create_order() {
  http_post_json "$API/v1/orders" \
    "{\"restaurant_id\":\"$RID\",\"customer_name\":\"SmokeTest\",\"items\":[{\"id\":\"$ITEM_ID\",\"qty\":1,\"name\":\"$ITEM_NAME\",\"price_cents\":$PRICE_CENTS,\"prep_units\":$PREP_UNITS}]}"
}

set_vicinity_true() {
  local oid="$1"
  http_post_json "$API/v1/orders/$oid/vicinity" '{"vicinity": true}'
}

ack_hard() {
  local oid="$1"
  http_post_json "$API/v1/restaurants/$RID/orders/$oid/ack" '{"mode":"HARD"}'
}

cancel_order() {
  local oid="$1"
  http_post_json "$API/v1/orders/$oid/cancel" '{}'
}

set_status() {
  local oid="$1"
  local st="$2"
  http_post_json "$API/v1/restaurants/$RID/orders/$oid/status" "{\"status\":\"$st\"}"
}


reset_capacity_window() {
  local now ws
  now=$(date +%s)
  ws=$(( now - (now % WINDOW_SECONDS) ))

  aws dynamodb delete-item \
    --table-name "$CAP_TABLE" \
    --key "{\"restaurant_id\":{\"S\":\"$RID\"},\"window_start\":{\"N\":\"$ws\"}}" >/dev/null 2>&1 || true
}

# -----------------------------
# Start
# -----------------------------
echo "Running smoke test against API=$API RID=$RID"
require_cmd curl
require_cmd aws
require_cmd python3

# 1) Health
HEALTH="$(http_get "$API/v1/health" || true)"
echo "health=$HEALTH"
echo "$HEALTH" | grep -q '"ok": true' || fail "health check failed"

pass "health check"
reset_capacity_window
pass "capacity window reset"


# -----------------------------
# Test A: capacity available -> SENT
# -----------------------------
set_capacity 20
pass "set capacity=20"

ORDER_JSON="$(create_order)"
echo "orderA=$ORDER_JSON"
OID_A="$(echo "$ORDER_JSON" | python3 -c 'import sys,json; print(json.load(sys.stdin)["order_id"])')"
[ -n "$OID_A" ] || fail "missing order_id from create_order"

RESP_A="$(set_vicinity_true "$OID_A")"
echo "vicinityA=$RESP_A"
echo "$RESP_A" | grep -q '"status": "SENT_TO_RESTAURANT"' || fail "expected SENT_TO_RESTAURANT for orderA"

pass "orderA dispatched (PENDING->SENT)"

# -----------------------------
# Test A-idem: POST /v1/orders Idempotency-Key (same payload => same order_id)
# -----------------------------
IDEM_KEY="idem_smoke_$(date +%s)"
ORDER_BODY="{\"restaurant_id\":\"$RID\",\"customer_name\":\"IdemSmoke\",\"items\":[{\"id\":\"$ITEM_ID\",\"qty\":1,\"name\":\"$ITEM_NAME\",\"price_cents\":$PRICE_CENTS,\"prep_units\":$PREP_UNITS}]}"
IDEM1="$(http_post_json_with_header "$API/v1/orders" "Idempotency-Key: $IDEM_KEY" "$ORDER_BODY")"
echo "idem1=$IDEM1"
OID_I1="$(echo "$IDEM1" | python3 -c 'import sys,json; print(json.load(sys.stdin)["order_id"])')"
[ -n "$OID_I1" ] || fail "missing order_id from idempotent create (1)"

IDEM2="$(http_post_json_with_header "$API/v1/orders" "Idempotency-Key: $IDEM_KEY" "$ORDER_BODY")"
echo "idem2=$IDEM2"
OID_I2="$(echo "$IDEM2" | python3 -c 'import sys,json; print(json.load(sys.stdin)["order_id"])')"
[ -n "$OID_I2" ] || fail "missing order_id from idempotent create (2)"

[ "$OID_I1" = "$OID_I2" ] || fail "idempotency failed: order_id mismatch for same Idempotency-Key"
pass "idempotency returns same order_id"

# Same key + different payload => 409 conflict
ORDER_BODY2="{\"restaurant_id\":\"$RID\",\"customer_name\":\"IdemSmoke_CHANGED\",\"items\":[{\"id\":\"$ITEM_ID\",\"qty\":1,\"name\":\"$ITEM_NAME\",\"price_cents\":$PRICE_CENTS,\"prep_units\":$PREP_UNITS}]}"
IDEM3_RAW="$(http_post_json_with_header_i "$API/v1/orders" "Idempotency-Key: $IDEM_KEY" "$ORDER_BODY2")"
IDEM3_STATUS="$(http_status "$IDEM3_RAW")"
IDEM3_BODY="$(http_body "$IDEM3_RAW")"
echo "idem3_status=$IDEM3_STATUS"
echo "idem3_body=$IDEM3_BODY"

[ "$IDEM3_STATUS" = "409" ] || fail "expected 409 for Idempotency-Key reuse with different payload"
echo "$IDEM3_BODY" | grep -q 'IDEMPOTENCY_KEY_REUSED' || fail "expected IDEMPOTENCY_KEY_REUSED in conflict response"
pass "idempotency key reuse with different payload rejected (409)"

# -----------------------------
# Test A0: ACK before send => INVALID_STATE
# -----------------------------
ORDER_JSON0="$(create_order)"
echo "orderA0=$ORDER_JSON0"
OID_A0="$(echo "$ORDER_JSON0" | python3 -c 'import sys,json; print(json.load(sys.stdin)["order_id"])')"

ACK0="$(ack_hard "$OID_A0")"
echo "ack0=$ACK0"
echo "$ACK0" | grep -q '"code": "INVALID_STATE"' || fail "expected INVALID_STATE when ack before send"

pass "ack before send rejected (INVALID_STATE)"

# -----------------------------
# Test A1: vicinity false is a NO-OP
# -----------------------------
RESP_NOOP="$(http_post_json "$API/v1/orders/$OID_A0/vicinity" '{"vicinity": false}')"
echo "vicinity_noop=$RESP_NOOP"
echo "$RESP_NOOP" | grep -q '"status": "PENDING_NOT_SENT"' || fail "expected PENDING_NOT_SENT when vicinity=false before send"

pass "vicinity=false no-op"

# Now send it so we can test wrong-RID ack
RESP_SEND0="$(set_vicinity_true "$OID_A0")"
echo "vicinity_send0=$RESP_SEND0"
echo "$RESP_SEND0" | grep -q '"status": "SENT_TO_RESTAURANT"' || fail "expected SENT_TO_RESTAURANT after vicinity=true"

pass "orderA0 dispatched for auth tests"

# -----------------------------
# Test A2: wrong restaurant => 404 NOT_FOUND (and NOT a routing 403)
# -----------------------------
ACK_WRONG_RAW="$(http_post_json_i "$API/v1/restaurants/WRONG/orders/$OID_A0/ack" '{"mode":"HARD"}')"
ACK_WRONG_STATUS="$(http_status "$ACK_WRONG_RAW")"
ACK_WRONG_BODY="$(http_body "$ACK_WRONG_RAW")"
echo "ack_wrong_status=$ACK_WRONG_STATUS"
echo "ack_wrong_body=$ACK_WRONG_BODY"

[ "$ACK_WRONG_STATUS" = "404" ] || fail "expected HTTP 404 for WRONG restaurant ack"
echo "$ACK_WRONG_BODY" | grep -q '"code": "NOT_FOUND"' || fail "expected NOT_FOUND body for WRONG restaurant ack"

pass "wrong restaurant ack rejected (404 NOT_FOUND)"

# -----------------------------
# Test B: capacity blocked -> WAITING then retry -> SENT
# -----------------------------
set_capacity 0
pass "set capacity=0"

ORDER_JSON_B="$(create_order)"
echo "orderB=$ORDER_JSON_B"
OID_B="$(echo "$ORDER_JSON_B" | python3 -c 'import sys,json; print(json.load(sys.stdin)["order_id"])')"
[ -n "$OID_B" ] || fail "missing order_id from create_order (B)"

RESP_B1="$(set_vicinity_true "$OID_B")"
echo "vicinityB1=$RESP_B1"
echo "$RESP_B1" | grep -q '"status": "WAITING_FOR_CAPACITY"' || fail "expected WAITING_FOR_CAPACITY for orderB first attempt"

pass "orderB blocked (PENDING->WAITING)"

set_capacity 20
pass "set capacity=20 (retry)"

RESP_B2="$(set_vicinity_true "$OID_B")"
echo "vicinityB2=$RESP_B2"
echo "$RESP_B2" | grep -q '"status": "SENT_TO_RESTAURANT"' || fail "expected SENT_TO_RESTAURANT for orderB retry"

pass "orderB dispatched (WAITING->SENT)"

# Cancel should fail if already SENT
CANCEL_SENT="$(cancel_order "$OID_A")"
echo "cancel_sent=$CANCEL_SENT"
echo "$CANCEL_SENT" | grep -q '"code": "INVALID_STATE"' && pass "cancel SENT rejected (INVALID_STATE)" || true
# (Depending on your error shape, adjust this grep to match map_core_error)

#create a PENDING order and cancel it
ORDER_CAN="$(create_order)"
OID_CAN="$(echo "$ORDER_CAN" | python3 -c 'import sys,json; print(json.load(sys.stdin)["order_id"])')"
CANCEL1="$(cancel_order "$OID_CAN")"
echo "cancel1=$CANCEL1"
echo "$CANCEL1" | grep -q '"status": "CANCELED"' || fail "expected CANCELED"
pass "cancel PENDING -> CANCELED"



# -----------------------------
# Test C: ACK hard + idempotent
# -----------------------------
ACK1="$(ack_hard "$OID_A")"
echo "ack1=$ACK1"
echo "$ACK1" | grep -q '"receipt_mode": "HARD"' || fail "expected receipt_mode HARD on first ack"

pass "ack upgraded to HARD"

ACK2="$(ack_hard "$OID_A")"
echo "ack2=$ACK2"
echo "$ACK2" | grep -q '"receipt_mode": "HARD"' || fail "expected receipt_mode HARD on idempotent ack"

pass "ack idempotent"

# -----------------------------
# Test D: Status transitions
# -----------------------------

S1="$(set_status "$OID_A" "IN_PROGRESS")"
echo "status1=$S1"
echo "$S1" | grep -q '"status": "IN_PROGRESS"' || fail "expected IN_PROGRESS"
pass "status SENT->IN_PROGRESS"

S2="$(set_status "$OID_A" "READY")"
echo "status2=$S2"
echo "$S2" | grep -q '"status": "READY"' || fail "expected READY"
pass "status IN_PROGRESS->READY"

S3="$(set_status "$OID_A" "COMPLETED")"
echo "status3=$S3"
echo "$S3" | grep -q '"status": "COMPLETED"' || fail "expected COMPLETED"
pass "status READY->COMPLETED"


echo
echo "🎉 SMOKE TEST PASSED"

