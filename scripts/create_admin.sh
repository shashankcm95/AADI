#!/bin/bash

# Configuration
STACK_NAME="arrive-dev"
REGION="us-east-1"
USERNAME="${1}"
PASSWORD="${2}"
RESTAURANT_ID="${3}"

if [ -z "$USERNAME" ] || [ -z "$PASSWORD" ] || [ -z "$RESTAURANT_ID" ]; then
  echo "Usage: ./create_admin.sh <email> <password> <restaurant_id>"
  exit 1
fi

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
echo "👤 Creating ADMIN user: $USERNAME for Restaurant: $RESTAURANT_ID..."

aws cognito-idp admin-create-user \
  --user-pool-id "$USER_POOL_ID" \
  --username "$USERNAME" \
  --user-attributes \
    Name=email,Value="$USERNAME" \
    Name=email_verified,Value=true \
    Name=custom:role,Value="admin" \
    Name="custom:restaurant_id",Value="$RESTAURANT_ID" \
  --message-action SUPPRESS \
  --region "$REGION" > /dev/null 2>&1

if [ $? -eq 0 ]; then
  echo "✅ Admin User created."
else
  echo "⚠️  User might already exist. Updating attributes..."
  aws cognito-idp admin-update-user-attributes \
    --user-pool-id "$USER_POOL_ID" \
    --username "$USERNAME" \
    --user-attributes \
        Name=custom:role,Value="admin" \
        Name="custom:restaurant_id",Value="$RESTAURANT_ID" \
    --region "$REGION"
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
echo "🎉 Admin Ready! Login with:"
echo "   User:     $USERNAME"
echo "   Pass:     $PASSWORD"
echo "   Role:     admin"
echo "   RestID:   $RESTAURANT_ID"
