#!/bin/bash

API_BASE="https://ph8xe60a2e.execute-api.us-east-1.amazonaws.com"
ADMIN_EMAIL="admin@aadi.com"
PASSWORD="Password123!"

USER_POOL_ID=$(aws cloudformation describe-stacks \
  --stack-name arrive-dev \
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" \
  --output text)

if [ -z "$USER_POOL_ID" ] || [ "$USER_POOL_ID" == "None" ]; then
    echo "❌ Error: Could not find UserPoolId from stack arrive-dev"
    exit 1
fi

# 1. Login as Super Admin
echo "🔐 Logging in as Super Admin..."
ADMIN_TOKEN=$(./scripts/dev/get_token.sh "$ADMIN_EMAIL" "$PASSWORD" | tail -n 1)

if [ -z "$ADMIN_TOKEN" ]; then
    echo "❌ Admin Login Failed"
    exit 1
fi

# 2. Create Restaurant with Email
NEW_EMAIL="invite_test_$(date +%s)@example.com"
echo "📧 Creating Restaurant with invite email: $NEW_EMAIL"

CREATE_RES=$(curl -s -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name": "Invite Test Kitchen", "address": "123 Cloud Ln", "contact_email": "'"$NEW_EMAIL"'"}' \
    "$API_BASE/v1/restaurants")

echo "Response: $CREATE_RES"
REST_ID=$(echo "$CREATE_RES" | jq -r '.restaurant_id // .restaurant.restaurant_id')

if [ -z "$REST_ID" ] || [ "$REST_ID" == "null" ]; then
    echo "❌ Failed to create restaurant."
    exit 1
fi

echo "✅ Restaurant Created: $REST_ID"

# 3. Verify Cognito User Creation
echo "🕵️ Checking Cognito for User: $NEW_EMAIL"
USER_INFO=$(aws cognito-idp list-users --user-pool-id "$USER_POOL_ID" --filter "email = \"$NEW_EMAIL\"")
USER_STATUS=$(echo "$USER_INFO" | jq -r '.Users[0].UserStatus')

if [ "$USER_STATUS" == "FORCE_CHANGE_PASSWORD" ]; then
    echo "✅ SUCCESS: User created in Cognito with status FORCE_CHANGE_PASSWORD"
else
    echo "❌ FAILURE: User status is $USER_STATUS (Expected FORCE_CHANGE_PASSWORD)"
    echo "$USER_INFO"
fi
