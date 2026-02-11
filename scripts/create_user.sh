#!/bin/bash

# Configuration
STACK_NAME="arrive-dev"
REGION="us-east-1"
USERNAME="${1:-qa_user@aadi.com}"
PASSWORD="${2:-Password123!}"

echo "🔍 Finding User Pool ID for stack: $STACK_NAME..."

# Get User Pool ID from Stack Outputs
USER_POOL_ID=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" \
  --output text)

if [ -z "$USER_POOL_ID" ] || [ "$USER_POOL_ID" == "None" ]; then
  echo "❌ Error: Could not find UserPoolId for stack $STACK_NAME"
  exit 1
fi

echo "✅ Found User Pool: $USER_POOL_ID"

# Create User
echo "👤 Creating user: $USERNAME..."
aws cognito-idp admin-create-user \
  --user-pool-id "$USER_POOL_ID" \
  --username "$USERNAME" \
  --user-attributes Name=email,Value="$USERNAME" Name=email_verified,Value=true Name=custom:role,Value=customer \
  --message-action SUPPRESS \
  --region "$REGION" > /dev/null 2>&1

if [ $? -eq 0 ]; then
  echo "✅ User created."
else
  echo "⚠️  User might already exist. Attempting to reset password..."
fi

# Set Password (Permanent)
echo "🔑 Setting password to: $PASSWORD"
aws cognito-idp admin-set-user-password \
  --user-pool-id "$USER_POOL_ID" \
  --username "$USERNAME" \
  --password "$PASSWORD" \
  --permanent \
  --region "$REGION"

echo ""
echo "🎉 Success! You can now login with:"
echo "   Email:    $USERNAME"
echo "   Password: $PASSWORD"
