#!/usr/bin/env bash
set -e

REGION="${REGION:-us-east-1}"
TABLE_NAME="${TABLE_NAME:-$(aws dynamodb list-tables --region "$REGION" \
  --query "TableNames[?contains(@, 'MenusTable')]|[0]" --output text 2>/dev/null)}"

if [ -z "$TABLE_NAME" ] || [ "$TABLE_NAME" = "None" ]; then
  echo "ERROR: Could not find MenusTable. Set TABLE_NAME env var."
  exit 1
fi

ITEM_FILE="$(dirname "$0")/menu_item.json"

aws dynamodb put-item \
  --table-name "$TABLE_NAME" \
  --item "file://$ITEM_FILE"

echo "Menu seeded successfully."

