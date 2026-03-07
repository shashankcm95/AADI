#!/bin/bash
# Wipe all DynamoDB tables for a fresh beta testing start.
# Usage: ./scripts/wipe_tables.sh
#
# This script deletes ALL items from the Orders, Restaurants, Menus,
# RestaurantConfig, Capacity, and Idempotency tables.
# It does NOT delete the tables themselves.

set -e

REGION="us-east-1"
STACK_NAME="arrive-dev"

echo "🧹 Wiping DynamoDB tables for fresh beta testing..."
echo ""

# Get table names from CloudFormation
get_table() {
  aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION \
    --query "Stacks[0].Outputs[?OutputKey==\`$1\`].OutputValue" --output text 2>/dev/null || echo ""
}

# Wipe a table by scanning and batch-deleting all items
wipe_table() {
  local TABLE_NAME=$1
  local PARTITION_KEY=$2
  local SORT_KEY=$3

  if [ -z "$TABLE_NAME" ] || [ "$TABLE_NAME" = "None" ]; then
    echo "  ⏭️  Skipping $PARTITION_KEY table (not found in stack)"
    return
  fi

  echo "  🗑️  Wiping $TABLE_NAME..."

  if [ -z "$SORT_KEY" ]; then
    # Simple primary key
    KEYS=$(aws dynamodb scan --table-name "$TABLE_NAME" --region "$REGION" \
      --projection-expression "$PARTITION_KEY" \
      --query "Items[].$PARTITION_KEY.S" --output text 2>/dev/null)

    for KEY in $KEYS; do
      aws dynamodb delete-item --table-name "$TABLE_NAME" --region "$REGION" \
        --key "{\"$PARTITION_KEY\": {\"S\": \"$KEY\"}}" 2>/dev/null
    done
  else
    # Composite key — need both partition and sort
    aws dynamodb scan --table-name "$TABLE_NAME" --region "$REGION" \
      --projection-expression "$PARTITION_KEY, $SORT_KEY" \
      --output json 2>/dev/null | \
    python3 -c "
import sys, json
data = json.load(sys.stdin)
for item in data.get('Items', []):
    pk = item['$PARTITION_KEY']
    sk = item['$SORT_KEY']
    key = json.dumps({'$PARTITION_KEY': pk, '$SORT_KEY': sk})
    print(key)
" | while read -r KEY_JSON; do
      aws dynamodb delete-item --table-name "$TABLE_NAME" --region "$REGION" \
        --key "$KEY_JSON" 2>/dev/null
    done
  fi

  COUNT=$(aws dynamodb scan --table-name "$TABLE_NAME" --region "$REGION" \
    --select COUNT --query "Count" --output text 2>/dev/null)
  echo "    ✅ $TABLE_NAME now has $COUNT items"
}

# --- Orders Service Tables ---
echo "📦 Orders Service"
ORDERS_TABLE=$(aws dynamodb list-tables --region $REGION --query "TableNames[?contains(@, 'OrdersTable')]|[0]" --output text 2>/dev/null)
CAPACITY_TABLE=$(aws dynamodb list-tables --region $REGION --query "TableNames[?contains(@, 'CapacityTable')]|[0]" --output text 2>/dev/null)
IDEMPOTENCY_TABLE=$(aws dynamodb list-tables --region $REGION --query "TableNames[?contains(@, 'IdempotencyTable')]|[0]" --output text 2>/dev/null)

wipe_table "$ORDERS_TABLE" "order_id"
wipe_table "$CAPACITY_TABLE" "restaurant_id" "window_start"
wipe_table "$IDEMPOTENCY_TABLE" "idempotency_key"

echo ""

# --- Restaurants Service Tables ---
echo "🏪 Restaurants Service"
RESTAURANTS_TABLE=$(aws dynamodb list-tables --region $REGION --query "TableNames[?contains(@, 'RestaurantsTable')]|[0]" --output text 2>/dev/null)
MENUS_TABLE=$(aws dynamodb list-tables --region $REGION --query "TableNames[?contains(@, 'MenusTable')]|[0]" --output text 2>/dev/null)
CONFIG_TABLE=$(aws dynamodb list-tables --region $REGION --query "TableNames[?contains(@, 'RestaurantConfigTable')]|[0]" --output text 2>/dev/null)

wipe_table "$RESTAURANTS_TABLE" "restaurant_id"
wipe_table "$MENUS_TABLE" "restaurant_id" "menu_version"
wipe_table "$CONFIG_TABLE" "restaurant_id"

echo ""
echo "✅ All tables wiped! Ready for fresh beta testing."
echo ""
echo "Next steps:"
echo "  1. Run ./infrastructure/scripts/dev/seed_test_data.sh to seed fresh restaurant data"
echo "  2. Or add restaurants manually through the admin portal"
echo "  3. Start testing features end-to-end"
