#!/bin/bash

API_BASE="https://ph8xe60a2e.execute-api.us-east-1.amazonaws.com"
ADMIN_EMAIL="admin@aadi.com"
PASSWORD="Password123!"

# 1. Login as Super Admin
echo "🔐 Logging in as Super Admin..."
ADMIN_TOKEN=$(./scripts/get_token.sh "$ADMIN_EMAIL" "$PASSWORD" | tail -n 1)

if [ -z "$ADMIN_TOKEN" ]; then
    echo "❌ Admin Login Failed"
    exit 1
fi

# 2. Create Restaurant with Known Address
NEW_EMAIL="geo_test_$(date +%s)@example.com"
echo "📧 Creating Restaurant with properties at: Empire State Building"

# Using Empire State Building address: 20 W 34th St, New York, NY 10001
CREATE_RES=$(curl -s -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "Empire Eats",
        "street": "20 W 34th St",
        "city": "New York",
        "state": "NY",
        "zip": "10001",
        "contact_email": "'"$NEW_EMAIL"'"
    }' \
    "$API_BASE/v1/restaurants")

echo "Response: $CREATE_RES"
REST_ID=$(echo "$CREATE_RES" | jq -r '.restaurant.restaurant_id')
LAT=$(echo "$CREATE_RES" | jq -r '.restaurant.location.lat')
LON=$(echo "$CREATE_RES" | jq -r '.restaurant.location.lon')

if [ -z "$REST_ID" ] || [ "$REST_ID" == "null" ]; then
    echo "❌ Failed to create restaurant."
    exit 1
fi

echo "✅ Restaurant Created: $REST_ID"

# 3. Verify Coordinates
# Approx Lat: 40.748, Lon: -73.985
echo "📍 Coordinates: $LAT, $LON"

if [[ "$LAT" != "null" && "$LON" != "null" ]]; then
    echo "✅ SUCCESS: Geocoding successful!"
else
    echo "❌ FAILURE: Geocoding failed (Coordinates are null)."
    exit 1
fi
