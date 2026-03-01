import json
import unittest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from handlers import users


def _make_event(body=None):
    return {
        'requestContext': {
            'authorizer': {'jwt': {'claims': {'sub': 'user123'}}}
        },
        'headers': {'origin': 'http://localhost:5173'},
        'body': json.dumps(body) if body is not None else None,
    }


class TestUsers(unittest.TestCase):
    def setUp(self):
        self.mock_table = MagicMock()
        self.original_table = users.users_table
        users.users_table = self.mock_table

    def tearDown(self):
        users.users_table = self.original_table

    # ── get_profile ───────────────────────────────────────────────────────────

    def test_get_profile_success(self):
        event = _make_event()
        self.mock_table.get_item.return_value = {
            'Item': {'user_id': 'user123', 'name': 'John Doe'}
        }

        response = users.get_profile(event)

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(body['name'], 'John Doe')

    def test_get_profile_not_found(self):
        event = _make_event()
        self.mock_table.get_item.return_value = {}  # No Item

        response = users.get_profile(event)

        self.assertEqual(response['statusCode'], 404)

    # ── update_profile ────────────────────────────────────────────────────────

    def test_update_profile_success(self):
        event = _make_event({'name': 'Jane Doe', 'phone_number': '555-1234'})
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
        # Existence guard must be present
        self.assertEqual(args['ConditionExpression'], 'attribute_exists(user_id)')

    def test_update_profile_invalid_fields_ignored(self):
        event = _make_event({'role': 'admin', 'name': 'Hacker'})
        self.mock_table.update_item.return_value = {}

        users.update_profile(event)

        args = self.mock_table.update_item.call_args[1]
        self.assertIn('#name = :name', args['UpdateExpression'])
        for key in args['ExpressionAttributeNames'].keys():
            self.assertNotEqual(args['ExpressionAttributeNames'][key], 'role')

    def test_update_profile_not_found(self):
        """update_item raises ConditionalCheckFailedException → 404."""
        event = _make_event({'name': 'Ghost'})
        error = ClientError(
            {'Error': {'Code': 'ConditionalCheckFailedException', 'Message': 'x'}},
            'UpdateItem',
        )
        self.mock_table.update_item.side_effect = error

        response = users.update_profile(event)

        self.assertEqual(response['statusCode'], 404)

    def test_update_profile_picture_valid(self):
        event = _make_event({'picture': 'avatars/user123-1700000000.jpg'})
        self.mock_table.update_item.return_value = {
            'Attributes': {'user_id': 'user123', 'picture': 'avatars/user123-1700000000.jpg'}
        }

        response = users.update_profile(event)

        self.assertEqual(response['statusCode'], 200)
        args = self.mock_table.update_item.call_args[1]
        self.assertIn('#picture = :picture', args['UpdateExpression'])

    def test_update_profile_picture_wrong_user_rejected(self):
        """picture key belonging to another user must be rejected."""
        event = _make_event({'picture': 'avatars/otheruser-1700000000.jpg'})

        response = users.update_profile(event)

        self.assertEqual(response['statusCode'], 400)
        self.mock_table.update_item.assert_not_called()

    def test_update_profile_picture_invalid_format_rejected(self):
        """Malformed picture key must be rejected."""
        event = _make_event({'picture': 'https://evil.com/malware.jpg'})

        response = users.update_profile(event)

        self.assertEqual(response['statusCode'], 400)
        self.mock_table.update_item.assert_not_called()

    # ── create_avatar_upload_url ──────────────────────────────────────────────

    @patch('handlers.users.s3_client')
    @patch('handlers.users.os')
    def test_create_avatar_upload_url(self, mock_os, mock_s3):
        mock_os.environ.get.side_effect = lambda k, d=None: 'test-bucket' if k == 'AVATARS_BUCKET_NAME' else d

        mock_s3.generate_presigned_url.return_value = (
            'https://s3.amazonaws.com/test-bucket/avatars/user123.jpg'
        )

        event = _make_event({'content_type': 'image/jpeg'})

        response = users.create_avatar_upload_url(event)

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(
            body['upload_url'],
            'https://s3.amazonaws.com/test-bucket/avatars/user123.jpg',
        )
        self.assertIn('s3_key', body)
        self.assertTrue(body['s3_key'].startswith('avatars/user123-'))
        self.assertTrue(body['s3_key'].endswith('.jpg'))
        self.assertIn('public_url', body)
        self.assertTrue(
            body['public_url'].startswith('https://test-bucket.s3.us-east-1.amazonaws.com/avatars/user123-')
        )
        self.assertTrue(body['public_url'].endswith('.jpg'))


if __name__ == '__main__':
    unittest.main()
