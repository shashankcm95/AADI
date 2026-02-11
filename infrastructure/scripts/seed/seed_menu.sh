#!/usr/bin/env bash
set -e

TABLE_NAME="arrive-dev-MenusTable-YEYCNI468M1P"
ITEM_FILE="$(dirname "$0")/menu_item.json"

aws dynamodb put-item \
  --table-name "$TABLE_NAME" \
  --item "file://$ITEM_FILE"

echo "Menu seeded successfully."

