#!/bin/bash
set -e

COMMAND=$1
REGION=${AWS_REGION:-"us-east-1"}

if [ -z "$COMMAND" ]; then
    echo "Usage: $0 [pause|resume]"
    exit 1
fi

echo "Fetching AADI APIs in $REGION..."
# Find all APIs with name starting with 'aadi-' or part of 'aadi-' stacks
# We use tags to identify them ideally, or just name convention if tags are missing on the API resource itself (SAM httpapi implicit might not have stack tags on the api resource directly? verified in previous step they do).
# Previous step showed tags: aws:cloudformation:stack-name : aadi-orders
APIS=$(aws apigatewayv2 get-apis --region $REGION --query "Items[?contains(Name, 'aadi') || Tags.\"aws:cloudformation:stack-name\" != null && contains(Tags.\"aws:cloudformation:stack-name\", 'aadi')].ApiId" --output text)

if [ -z "$APIS" ]; then
    echo "No APIs found matching 'aadi'."
    exit 0
fi

for API_ID in $APIS; do
    echo "Processing API: $API_ID"
    STAGES=$(aws apigatewayv2 get-stages --api-id $API_ID --region $REGION --query "Items[*].StageName" --output text)
    
    for STAGE in $STAGES; do
        if [ "$STAGE" == "None" ]; then continue; fi
        
        echo "  Stage: $STAGE"
        
        if [ "$COMMAND" == "pause" ]; then
            echo "    -> Throttling to 0..."
            aws apigatewayv2 update-stage --api-id $API_ID --stage-name $STAGE --region $REGION \
                --default-route-settings "ThrottlingBurstLimit=0,ThrottlingRateLimit=0.0" > /dev/null
        elif [ "$COMMAND" == "resume" ]; then
            echo "    -> Restoring throttling (Burst: 5000, Rate: 10000)..."
            # Default or standard deployment values
            aws apigatewayv2 update-stage --api-id $API_ID --stage-name $STAGE --region $REGION \
                --default-route-settings "ThrottlingBurstLimit=5000,ThrottlingRateLimit=10000.0" > /dev/null
        else
            echo "Unknown command: $COMMAND"
            exit 1
        fi
    done
done

echo "Done. Services are now ${COMMAND}d."
