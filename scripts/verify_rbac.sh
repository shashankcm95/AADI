#!/bin/bash

# Configuration
API_URL=$(aws cloudformation describe-stacks --stack-name arrive-restaurants-dev --query "Stacks[0].Outputs[?OutputKey=='RestaurantsApi'].OutputValue" --output text)

if [ -z "$API_URL" ] || [ "$API_URL" == "None" ]; then
    echo "❌ Error: Could not find RestaurantsApi output from stack arrive-restaurants-dev"
    exit 1
fi

ADMIN_EMAIL="admin@aadi.com"
REST_EMAIL="restaurant@aadi.com"
PASSWORD="Password123!"

echo "🔗 API URL: $API_URL"

# 1. Get Tokens
echo "🔑 Getting token for ADMIN..."
ADMIN_TOKEN=$(./scripts/get_token.sh "$ADMIN_EMAIL" "$PASSWORD" | tail -n 1)

echo "🔑 Getting token for RESTAURANT ADMIN..."
REST_TOKEN=$(./scripts/get_token.sh "$REST_EMAIL" "$PASSWORD" | tail -n 1)

if [ -z "$ADMIN_TOKEN" ] || [ -z "$REST_TOKEN" ]; then
    echo "❌ Failed to get tokens"
    exit 1
fi

# 2. Test: List Restaurants (Admin)
echo -e "\n🧪 Test 1: Admin Listing Restaurants (Should see all)"
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" "$API_URL/v1/restaurants" | jq .

# 3. Test: List Restaurants (Restaurant Admin)
echo -e "\n🧪 Test 2: Restaurant Admin Listing Restaurants (Should see ONE)"
curl -s -H "Authorization: Bearer $REST_TOKEN" "$API_URL/v1/restaurants" | jq .

# 4. Test: Create Restaurant (Restaurant Admin)
echo -e "\n🧪 Test 3: Restaurant Admin Creating Restaurant (Should FAIL 403)"
curl -s -X POST -H "Authorization: Bearer $REST_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name": "Hacker Kitchen", "address": "Nowhere"}' \
    "$API_URL/v1/restaurants" | jq .

# 5. Test: Create Restaurant (Admin)
echo -e "\n🧪 Test 4: Admin Creating Restaurant (Should SUCCEED 201)"
curl -s -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name": "Admin Created Kitchen", "address": "Somewhere"}' \
    "$API_URL/v1/restaurants" | jq .
