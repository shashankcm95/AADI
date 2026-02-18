import json
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from handlers import users

class TestUsers(unittest.TestCase):
    def setUp(self):
        self.mock_table = MagicMock()
        self.original_table = users.users_table
        users.users_table = self.mock_table

    def tearDown(self):
        users.users_table = self.original_table

    def test_get_profile_success(self):
        event = {
            'requestContext': {
                'authorizer': {'jwt': {'claims': {'sub': 'user123'}}}
            }
        }
        self.mock_table.get_item.return_value = {
            'Item': {'user_id': 'user123', 'name': 'John Doe'}
        }
        
        response = users.get_profile(event)
        
        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(body['name'], 'John Doe')

    def test_get_profile_not_found(self):
        event = {
            'requestContext': {
                'authorizer': {'jwt': {'claims': {'sub': 'user123'}}}
            }
        }
        self.mock_table.get_item.return_value = {} # No Item
        
        response = users.get_profile(event)
        
        self.assertEqual(response['statusCode'], 404)

    def test_update_profile_success(self):
        event = {
            'requestContext': {
                'authorizer': {'jwt': {'claims': {'sub': 'user123'}}}
            },
            'body': json.dumps({'name': 'Jane Doe', 'phone_number': '555-1234'})
        }
        
        self.mock_table.update_item.return_value = {
            'Attributes': {'user_id': 'user123', 'name': 'Jane Doe'}
        }
        
        response = users.update_profile(event)
        
        self.assertEqual(response['statusCode'], 200)
        
        # Verify update call
        args = self.mock_table.update_item.call_args[1]
        self.assertEqual(args['Key'], {'user_id': 'user123'})
        self.assertIn('#name = :name', args['UpdateExpression'])
        self.assertIn('#phone_number = :phone_number', args['UpdateExpression'])
        self.assertEqual(args['ExpressionAttributeValues'][':name'], 'Jane Doe')

    def test_update_profile_invalid_fields_ignored(self):
        event = {
            'requestContext': {
                'authorizer': {'jwt': {'claims': {'sub': 'user123'}}}
            },
            'body': json.dumps({'role': 'admin', 'name': 'Hacker'})
        }
        
        self.mock_table.update_item.return_value = {}
        
        users.update_profile(event)
        
        args = self.mock_table.update_item.call_args[1]
        # Should contain name update
        self.assertIn('#name = :name', args['UpdateExpression'])
        # Should NOT contain role update
        for key in args['ExpressionAttributeNames'].keys():
            self.assertNotEqual(args['ExpressionAttributeNames'][key], 'role')

if __name__ == '__main__':
    unittest.main()
