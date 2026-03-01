#!/bin/bash
# Usage:
#   export API_BASE=https://<restaurants-api-id>.execute-api.us-east-1.amazonaws.com
#   export ORDERS_API=https://<orders-api-id>.execute-api.us-east-1.amazonaws.com
#   export ADMIN_EMAIL=admin@example.com
#   export CUST_EMAIL=customer@example.com
#   export E2E_PASSWORD=<test-account-password>
#   ./scripts/test_e2e_flow.sh

set -euo pipefail

# Configuration — all values must be supplied via environment variables.
# No defaults are provided to prevent accidental use of a wrong environment.
: "${API_BASE:?Set API_BASE to the Restaurants API Gateway base URL}"
: "${ORDERS_API:?Set ORDERS_API to the Orders API Gateway base URL}"
: "${ADMIN_EMAIL:?Set ADMIN_EMAIL to the test admin account email}"
: "${CUST_EMAIL:?Set CUST_EMAIL to the test customer account email}"
: "${E2E_PASSWORD:?Set E2E_PASSWORD to the test account password}"

PASSWORD="$E2E_PASSWORD"

# Helper Functions
get_token() {
    ./scripts/get_token.sh "$1" "$PASSWORD" | tail -n 1
}

echo "🚀 Starting End-to-End Test Automation..."

# 1. Login as Super Admin
echo -e "\n🔐 Logging in as Super Admin..."
ADMIN_TOKEN=$(get_token "$ADMIN_EMAIL")
if [ -z "$ADMIN_TOKEN" ]; then echo "❌ Admin Login Failed"; exit 1; fi
echo "✅ Admin Logged In"

# 2. Create New Restaurant (Test Case 1)
echo -e "\n🏗️ Creating 'Auto Test Kitchen'..."
REST_NAME="Auto Test Kitchen $(date +%s)"
CREATE_RES=$(curl -s -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name": "'"$REST_NAME"'", "address": "123 Automation Ln", "operating_hours": "10:00-22:00"}' \
    "$API_BASE/v1/restaurants")

REST_ID=$(echo "$CREATE_RES" | jq -r '.restaurant.restaurant_id')

if [ -z "$REST_ID" ] || [ "$REST_ID" == "null" ]; then
    echo "❌ Failed to create restaurant. Response:"
    echo "$CREATE_RES"
    exit 1
fi
echo "✅ Created Restaurant: $REST_NAME (ID: $REST_ID)"

# 3. Customer Verifies Restaurant (Test Case 2)
echo -e "\n👀 Customer Checking Restaurant List..."
CUST_TOKEN=$(get_token "$CUST_EMAIL")
LIST_RES=$(curl -s -H "Authorization: Bearer $CUST_TOKEN" "$API_BASE/v1/restaurants")

if echo "$LIST_RES" | grep -q "$REST_ID"; then
    echo "✅ Customer sees the new restaurant!"
else
    echo "❌ Customer cannot see the new restaurant."
    echo "$LIST_RES"
    exit 1
fi

# 4. Customer Places Order (Test Case 3)
echo -e "\n🍔 Customer Placing Order..."
ORDER_Payload='{
    "restaurant_id": "'"$REST_ID"'",
    "items": [
        {"id": "auto_burger", "qty": 2, "name": "Auto Burger", "price_cents": 1200},
        {"id": "auto_fries", "qty": 1, "name": "Auto Fries", "price_cents": 400}
    ]
}'

ORDER_RES=$(curl -s -X POST -H "Authorization: Bearer $CUST_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$ORDER_Payload" \
    "$ORDERS_API/v1/orders")

ORDER_ID=$(echo "$ORDER_RES" | jq -r '.order_id')

if [ -z "$ORDER_ID" ] || [ "$ORDER_ID" == "null" ]; then
    echo "❌ Failed to place order."
    echo "$ORDER_RES"
    exit 1
fi
echo "✅ Order Placed! ID: $ORDER_ID"

# 5. Restaurant Admin Verification (Test Case 4)
echo -e "\n👨‍🍳 Restaurant Admin Checking Orders..."
# Note: In a real scenario, we'd need a specific user assigned to this new restaurant.
# For this test, we'll check if the *existing* restaurant admin (who is assigned to Test Kitchen 1)
# CANNOT see this order (RBAC test), OR we can simulate a Super Admin checking the order via the restaurant view.
# Let's verify via Super Admin for now as we haven't created a user for this specific new restaurant dynamically.

ADMIN_VIEW_ORDERS=$(curl -s -H "Authorization: Bearer $ADMIN_TOKEN" "$ORDERS_API/v1/restaurants/$REST_ID/orders")

if echo "$ADMIN_VIEW_ORDERS" | grep -q "$ORDER_ID"; then
    echo "✅ Super Admin confirmed order exists in restaurant queue."
else
    echo "❌ Order not found in restaurant queue."
    echo "$ADMIN_VIEW_ORDERS"
    exit 1
fi

echo -e "\n🎉 AUTOMATED E2E TEST PASSED! 🎉"
echo "Note: UX flows verified via API logic."
