import json
import uuid
import time
from unittest.mock import MagicMock, patch
import sys
import os

# Add service src to path
sys.path.append('/Users/shashankchandrashekarmurigappa/Documents/AADI/services/restaurants/src')

# Mock environment variables before importing app
os.environ['RESTAURANTS_TABLE'] = 'Restaurants'
os.environ['MENUS_TABLE'] = 'Menus'
os.environ['RESTAURANT_CONFIG_TABLE'] = 'Config'

# Mock boto3 before importing app
with patch('boto3.resource') as mock_boto:
    import app

    # Setup mock tables
    mock_dynamodb = MagicMock()
    mock_boto.return_value = mock_dynamodb
    
    mock_restaurants_table = MagicMock()
    mock_config_table = MagicMock()
    
    app.restaurants_table = mock_restaurants_table
    app.config_table = mock_config_table

    def test_create_restaurant():
        print("Testing create_restaurant...")
        
        event = {
            'routeKey': 'POST /v1/restaurants',
            'body': json.dumps({
                'name': 'Test Bistro',
                'address': '123 Test St',
                'contact_email': 'test@example.com',
                'operating_hours': '10:00-23:00'
            })
        }

        response = app.lambda_handler(event, None)
        
        print(f"Response Status: {response['statusCode']}")
        body = json.loads(response['body'])
        print(f"Response Body: {body}")

        if response['statusCode'] == 201:
            print("SUCCESS: Restaurant created.")
            print(f"Restaurant ID: {body['restaurant']['restaurant_id']}")
            
            # Verify calls
            mock_restaurants_table.put_item.assert_called_once()
            mock_config_table.put_item.assert_called_once()
            
            args, _ = mock_restaurants_table.put_item.call_args
            item = _['Item']
            assert item['name'] == 'Test Bistro'
            assert item['active'] == True
            print("Verified DynamoDB put_item called with correct data.")
            
        else:
            print("FAILURE: Did not get 201 created.")
            exit(1)

    if __name__ == "__main__":
        try:
            test_create_restaurant()
            print("\nAll tests passed!")
        except Exception as e:
            print(f"\nTest failed: {e}")
            exit(1)
