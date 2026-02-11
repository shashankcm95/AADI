#!/bin/bash

# verify_stage.sh
# Verifies that the deployed API is correctly protected by Cognito.
# Usage: ./scripts/verify_stage.sh <API_URL> [TOKEN]

API_URL=$1
TOKEN=$2

if [ -z "$API_URL" ]; then
    echo "Usage: $0 <API_URL> [OPTIONAL_TOKEN]"
    echo "Example: $0 https://xyz.execute-api.us-east-1.amazonaws.com"
    exit 1
fi

echo "---------------------------------------------------"
echo "🔍 Verifying API Security: $API_URL"
echo "---------------------------------------------------"

# 1. Test Public Endpoint (Health)
echo ""
echo "1️⃣  Testing Public Endpoint (Health Check)..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/v1/health")

if [ "$HTTP_CODE" == "200" ]; then
    echo "✅ PASS: Health check is PUBLIC (200 OK)"
else
    echo "❌ FAIL: Health check failed ($HTTP_CODE)"
fi

# 2. Test Protected Endpoint (Orders) - NO TOKEN
echo ""
echo "2️⃣  Testing Protected Endpoint (Create Order) - WITHOUT TOKEN..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/v1/orders" -d '{}')

if [ "$HTTP_CODE" == "401" ]; then
    echo "✅ PASS: Protected endpoint rejected request (401 Unauthorized)"
else
    echo "❌ FAIL: Endpoint did NOT return 401. It returned $HTTP_CODE. Is Auth enabled?"
fi

# 3. Test Protected Endpoint - WITH TOKEN (If provided)
if [ ! -z "$TOKEN" ]; then
    echo ""
    echo "3️⃣  Testing Protected Endpoint - WITH TOKEN..."
    # We expect 400 (if body bad) or 201 (if success), but NOT 401.
    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/v1/orders" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"restaurant_id": "rst_001", "items": [{"id": "item_1", "quantity": 1}]}')
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | sed '$d')

    if [ "$HTTP_CODE" == "401" ]; then
        echo "❌ FAIL: Token was rejected (401). Token might be expired or invalid scope."
    elif [ "$HTTP_CODE" == "403" ]; then
        echo "❌ FAIL: Token accepted but permission denied (403)."
    else
        echo "✅ PASS: Token accepted! (Code: $HTTP_CODE)"
        echo "   Response: $BODY"
    fi
else
    echo ""
    echo "ℹ️  Skipping authenticated test (No token provided)."
    echo "   To test success: ./scripts/verify_stage.sh $API_URL <ID_TOKEN>"
fi

echo ""
echo "---------------------------------------------------"
