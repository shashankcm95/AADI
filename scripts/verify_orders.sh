#!/bin/bash

# Configuration
ORDERS_API_URL="https://5fnj76yo6i.execute-api.us-east-1.amazonaws.com"
RESTAURANTS_API_URL="https://ph8xe60a2e.execute-api.us-east-1.amazonaws.com"
CUSTOMER_EMAIL="customer@aadi.com"
PASSWORD="Password123!"

echo "🔗 Orders API: $ORDERS_API_URL"
echo "🔗 Restaurants API: $RESTAURANTS_API_URL"

# 1. Get Token
echo "🔑 Getting token for CUSTOMER..."
TOKEN=$(./scripts/get_token.sh "$CUSTOMER_EMAIL" "$PASSWORD" | tail -n 1)

if [ -z "$TOKEN" ]; then
    echo "❌ Failed to get token"
    exit 1
fi

# 2. Get Restaurant ID (First one)
echo -e "\n🧪 Test 1: Fetching Restaurants..."
REST_ID=$(curl -s -H "Authorization: Bearer $TOKEN" "$RESTAURANTS_API_URL/v1/restaurants" | jq -r '.restaurants[0].restaurant_id')

if [ -z "$REST_ID" ] || [ "$REST_ID" == "null" ]; then
    echo "❌ Failed to get restaurant ID"
    exit 1
fi
echo "📍 Using Restaurant ID: $REST_ID"

# 3. Create Order
echo -e "\n🧪 Test 2: Creating Order..."
ORDER_Payload='{
    "restaurant_id": "'"$REST_ID"'",
    "items": [
        {"id": "item1", "qty": 2, "name": "Burger", "price_cents": 1000},
        {"id": "item2", "qty": 1, "name": "Fries", "price_cents": 500}
    ]
}'

ORDER_RES=$(curl -s -X POST -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$ORDER_Payload" \
    "$ORDERS_API_URL/v1/orders")

echo "$ORDER_RES" | jq .
ORDER_ID=$(echo "$ORDER_RES" | jq -r '.order_id')

if [ -z "$ORDER_ID" ] || [ "$ORDER_ID" == "null" ]; then
    echo "❌ Failed to create order"
    exit 1
fi

# 4. Get Order Status
echo -e "\n🧪 Test 3: Checking Order Status..."
curl -s -H "Authorization: Bearer $TOKEN" "$ORDERS_API_URL/v1/orders/$ORDER_ID" | jq .

# 5. List My Orders
echo -e "\n🧪 Test 4: Listing Customer Orders..."
curl -s -H "Authorization: Bearer $TOKEN" "$ORDERS_API_URL/v1/orders" | jq .

# 6. Verify Restaurant Admin Sees Order
echo -e "\n🧪 Test 5: Restaurant Admin Checking Orders..."
REST_EMAIL="restaurant@aadi.com"
REST_TOKEN=$(./scripts/get_token.sh "$REST_EMAIL" "$PASSWORD" | tail -n 1)

if [ -n "$REST_TOKEN" ]; then
    echo "🔑 Got Restaurant Admin Token"
    ORDERS=$(curl -s -H "Authorization: Bearer $REST_TOKEN" "$ORDERS_API_URL/v1/restaurants/$REST_ID/orders")
    echo "$ORDERS" | jq .
    
    # Check if order exists
    if echo "$ORDERS" | grep -q "$ORDER_ID"; then
        echo "✅ SUCCESS: Restaurant Admin found the order!"
    else
        echo "❌ FAILURE: Restaurant Admin could NOT find the order."
    fi
else
    echo "⚠️ Skipping Restaurant Admin check (failed to get token)"
fi
