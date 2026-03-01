#!/bin/bash
set -e

# Check for AWS credentials
if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "ERROR: AWS credentials are not set. Please export AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY."
    exit 1
fi

# Configuration
# Set these variables or export them before running the script
AWS_REGION=${AWS_REGION:-"us-east-1"}
ADMIN_BUCKET=${ADMIN_BUCKET:-"your-admin-portal-bucket-name"}
STACK_PREFIX=${STACK_PREFIX:-"aadi"}

# 0. Deploy Infrastructure (Buckets, Cognito, WAF)
echo "----------------------------------------------------------------"
echo "Deploying Infrastructure..."
echo "----------------------------------------------------------------"
cd infrastructure
sam build
sam deploy --stack-name ${STACK_PREFIX}-infra \
    --capabilities CAPABILITY_IAM \
    --region $AWS_REGION \
    --resolve-s3 \
    --no-fail-on-empty-changeset

# Fetch Bucket Name
echo "Fetching Admin Portal Bucket Name..."
ADMIN_BUCKET=$(aws cloudformation describe-stacks --stack-name ${STACK_PREFIX}-infra --query "Stacks[0].Outputs[?OutputKey=='AdminPortalBucketName'].OutputValue" --output text)

if [ "$ADMIN_BUCKET" == "None" ] || [ -z "$ADMIN_BUCKET" ]; then
    echo "ERROR: Could not retrieve AdminPortalBucketName from stack ${STACK_PREFIX}-infra"
    exit 1
fi
echo "Target Bucket: $ADMIN_BUCKET"
cd ..

# 1. Deploy Backend Services
echo "----------------------------------------------------------------"
echo "Deploying Backend Services..."
echo "----------------------------------------------------------------"

# Orders Service
echo "[1/2] Deploying Orders Service..."
cd services/orders
sam build
sam deploy --stack-name ${STACK_PREFIX}-orders \
    --capabilities CAPABILITY_IAM \
    --region $AWS_REGION \
    --resolve-s3 \
    --no-fail-on-empty-changeset
cd ../..

# Restaurants Service
echo "[2/2] Deploying Restaurants Service..."
cd services/restaurants
sam build
sam deploy --stack-name ${STACK_PREFIX}-restaurants \
    --capabilities CAPABILITY_IAM \
    --region $AWS_REGION \
    --resolve-s3 \
    --no-fail-on-empty-changeset
cd ../..

# 2. Deploy Frontend
echo "----------------------------------------------------------------"
echo "Deploying Admin Portal Frontend..."
echo "----------------------------------------------------------------"

cd packages/admin-portal
echo "Installing dependencies..."
npm install

echo "Building frontend..."
# Ensure VITE_API_URL is set? For now, using default or assumption.
npm run build

echo "Deploying to S3 ($ADMIN_BUCKET)..."
aws s3 sync dist s3://$ADMIN_BUCKET --delete
echo "Frontend deployed to s3://$ADMIN_BUCKET"

# Get CloudFront URL if available
CLOUDFRONT_URL=$(aws cloudformation describe-stacks --stack-name ${STACK_PREFIX}-infra --query "Stacks[0].Outputs[?OutputKey=='AdminPortalURL'].OutputValue" --output text)
echo "----------------------------------------------------------------"
echo "Deployment Complete!"
echo "Admin Portal URL: $CLOUDFRONT_URL"
echo "----------------------------------------------------------------"