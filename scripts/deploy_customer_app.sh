#!/bin/bash
set -e

# Configuration
CUSTOMER_BUCKET=${CUSTOMER_BUCKET:-"your-customer-app-bucket-name"}

echo "Deploying Customer App..."
echo "Target Bucket: $CUSTOMER_BUCKET"

echo "----------------------------------------------------------------"
echo "Building Customer App (Web)..."
echo "----------------------------------------------------------------"

cd packages/customer-web

if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
fi

echo "Building production bundle..."
npm run build

echo "----------------------------------------------------------------"
echo "Deploying to S3..."
echo "----------------------------------------------------------------"

# Fetch Bucket Name from Infra Stack
STACK_PREFIX=${STACK_PREFIX:-"aadi"}
echo "Fetching Customer Web Bucket Name from stack ${STACK_PREFIX}-infra..."
CUSTOMER_BUCKET=$(aws cloudformation describe-stacks --stack-name ${STACK_PREFIX}-infra --query "Stacks[0].Outputs[?OutputKey=='CustomerWebBucketName'].OutputValue" --output text)

if [ "$CUSTOMER_BUCKET" == "None" ] || [ -z "$CUSTOMER_BUCKET" ]; then
    echo "ERROR: Could not retrieve CustomerWebBucketName from stack ${STACK_PREFIX}-infra. Ensure infra is deployed."
    exit 1
fi
echo "Target Bucket: $CUSTOMER_BUCKET"

echo "----------------------------------------------------------------"
echo "Deploying to S3..."
echo "----------------------------------------------------------------"

aws s3 sync dist s3://$CUSTOMER_BUCKET --delete
echo "App deployed to s3://$CUSTOMER_BUCKET"

# Get CloudFront URL if available
CLOUDFRONT_URL=$(aws cloudformation describe-stacks --stack-name ${STACK_PREFIX}-infra --query "Stacks[0].Outputs[?OutputKey=='CustomerWebURL'].OutputValue" --output text)
echo "----------------------------------------------------------------"
echo "Deployment Complete!"
echo "Customer App URL: $CLOUDFRONT_URL"
echo "----------------------------------------------------------------"

cd ../..

echo "Deployment Complete!"
