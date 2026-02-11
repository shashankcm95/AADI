#!/bin/bash
# Seed test restaurants and menus for Arrive MVP testing
# Usage: ./scripts/seed_test_data.sh

set -e

# Get table names from CloudFormation outputs
STACK_NAME="arrive-dev"
REGION="us-east-1"

echo "🌱 Seeding test data for Arrive MVP..."

# Get table names
RESTAURANTS_TABLE=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`RestaurantsTableName`].OutputValue' --output text)
MENUS_TABLE=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`MenusTableName`].OutputValue' --output text)
CONFIG_TABLE=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`RestaurantConfigTableName`].OutputValue' --output text)

echo "📋 Tables:"
echo "  Restaurants: $RESTAURANTS_TABLE"
echo "  Menus: $MENUS_TABLE"
echo "  Config: $CONFIG_TABLE"

# Seed Restaurants
echo ""
echo "🏪 Creating restaurants..."

aws dynamodb put-item --table-name $RESTAURANTS_TABLE --region $REGION --item '{
  "restaurant_id": {"S": "rst_001"},
  "name": {"S": "Burger Palace"},
  "cuisine": {"S": "American"},
  "address": {"S": "123 Main St, Austin, TX"},
  "active": {"BOOL": true}
}'
echo "  ✓ Burger Palace (rst_001)"

aws dynamodb put-item --table-name $RESTAURANTS_TABLE --region $REGION --item '{
  "restaurant_id": {"S": "rst_002"},
  "name": {"S": "Pizza Heaven"},
  "cuisine": {"S": "Italian"},
  "address": {"S": "456 Oak Ave, Austin, TX"},
  "active": {"BOOL": true}
}'
echo "  ✓ Pizza Heaven (rst_002)"

aws dynamodb put-item --table-name $RESTAURANTS_TABLE --region $REGION --item '{
  "restaurant_id": {"S": "rst_003"},
  "name": {"S": "Sushi Express"},
  "cuisine": {"S": "Japanese"},
  "address": {"S": "789 Elm Blvd, Austin, TX"},
  "active": {"BOOL": true}
}'
echo "  ✓ Sushi Express (rst_003)"

# Seed Restaurant Configs (capacity settings)
echo ""
echo "⚙️ Creating restaurant configs..."

for rst in rst_001 rst_002 rst_003; do
  aws dynamodb put-item --table-name $CONFIG_TABLE --region $REGION --item "{
    \"restaurant_id\": {\"S\": \"$rst\"},
    \"active_menu_version\": {\"S\": \"v1\"},
    \"window_seconds\": {\"N\": \"600\"},
    \"max_prep_units\": {\"N\": \"20\"}
  }"
  echo "  ✓ Config for $rst"
done

# Seed Menus
echo ""
echo "📜 Creating menus..."

# Burger Palace Menu
aws dynamodb put-item --table-name $MENUS_TABLE --region $REGION --item '{
  "restaurant_id": {"S": "rst_001"},
  "menu_version": {"S": "v1"},
  "menu": {"M": {
    "items": {"L": [
      {"M": {"id": {"S": "burger"}, "name": {"S": "Classic Burger"}, "price_cents": {"N": "999"}, "prep_units": {"N": "2"}}},
      {"M": {"id": {"S": "cheeseburger"}, "name": {"S": "Cheeseburger"}, "price_cents": {"N": "1099"}, "prep_units": {"N": "2"}}},
      {"M": {"id": {"S": "fries"}, "name": {"S": "Fries"}, "price_cents": {"N": "399"}, "prep_units": {"N": "1"}}},
      {"M": {"id": {"S": "soda"}, "name": {"S": "Soda"}, "price_cents": {"N": "199"}, "prep_units": {"N": "0"}}},
      {"M": {"id": {"S": "shake"}, "name": {"S": "Milkshake"}, "price_cents": {"N": "499"}, "prep_units": {"N": "1"}}}
    ]}
  }}
}'
echo "  ✓ Burger Palace menu"

# Pizza Heaven Menu
aws dynamodb put-item --table-name $MENUS_TABLE --region $REGION --item '{
  "restaurant_id": {"S": "rst_002"},
  "menu_version": {"S": "v1"},
  "menu": {"M": {
    "items": {"L": [
      {"M": {"id": {"S": "margherita"}, "name": {"S": "Margherita Pizza"}, "price_cents": {"N": "1299"}, "prep_units": {"N": "3"}}},
      {"M": {"id": {"S": "pepperoni"}, "name": {"S": "Pepperoni Pizza"}, "price_cents": {"N": "1499"}, "prep_units": {"N": "3"}}},
      {"M": {"id": {"S": "garlic_bread"}, "name": {"S": "Garlic Bread"}, "price_cents": {"N": "499"}, "prep_units": {"N": "1"}}},
      {"M": {"id": {"S": "caesar_salad"}, "name": {"S": "Caesar Salad"}, "price_cents": {"N": "799"}, "prep_units": {"N": "1"}}}
    ]}
  }}
}'
echo "  ✓ Pizza Heaven menu"

# Sushi Express Menu
aws dynamodb put-item --table-name $MENUS_TABLE --region $REGION --item '{
  "restaurant_id": {"S": "rst_003"},
  "menu_version": {"S": "v1"},
  "menu": {"M": {
    "items": {"L": [
      {"M": {"id": {"S": "salmon_roll"}, "name": {"S": "Salmon Roll"}, "price_cents": {"N": "899"}, "prep_units": {"N": "2"}}},
      {"M": {"id": {"S": "tuna_roll"}, "name": {"S": "Tuna Roll"}, "price_cents": {"N": "999"}, "prep_units": {"N": "2"}}},
      {"M": {"id": {"S": "edamame"}, "name": {"S": "Edamame"}, "price_cents": {"N": "399"}, "prep_units": {"N": "1"}}},
      {"M": {"id": {"S": "miso_soup"}, "name": {"S": "Miso Soup"}, "price_cents": {"N": "299"}, "prep_units": {"N": "1"}}}
    ]}
  }}
}'
echo "  ✓ Sushi Express menu"

echo ""
echo "✅ Test data seeded successfully!"
echo ""
echo "🍔 Burger Palace (rst_001) - 5 menu items"
echo "🍕 Pizza Heaven (rst_002) - 4 menu items"
echo "🍣 Sushi Express (rst_003) - 4 menu items"
