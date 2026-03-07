#!/bin/bash

# Configuration
STACK_NAME="arrive-dev"
REGION="us-east-1"
USERNAME="${1:-qa_user@aadi.com}"
PASSWORD="${2:-Password123!}"

# Get User Pool ID and Client ID from Stack Outputs
USER_POOL_ID=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" \
  --output text)

CLIENT_ID=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolClientId'].OutputValue" \
  --output text)

if [ -z "$CLIENT_ID" ] || [ "$CLIENT_ID" == "None" ]; then
  echo "❌ Error: Could not find UserPoolClientId for stack $STACK_NAME"
  exit 1
fi

echo "🔑 Authenticating as $USERNAME..."

# Initiate Auth
AUTH_RESULT=$(aws cognito-idp initiate-auth \
  --auth-flow USER_PASSWORD_AUTH \
  --client-id "$CLIENT_ID" \
  --auth-parameters USERNAME="$USERNAME",PASSWORD="$PASSWORD" \
  --region "$REGION")

# Extract ID Token
ID_TOKEN=$(echo "$AUTH_RESULT" | grep -o '"IdToken": "[^"]*' | cut -d'"' -f4)

if [ -n "$ID_TOKEN" ]; then
  echo ""
  echo "✅ Authentication Successful!"
  echo "👇 ID Token (Bearer):"
  echo "$ID_TOKEN"
else
  echo "❌ Authentication Failed."
  echo "$AUTH_RESULT"
  exit 1
fi
