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

        self.mock_s3 = MagicMock()
        self.original_s3 = users.s3_client
        users.s3_client = self.mock_s3

    def tearDown(self):
        users.users_table = self.original_table
        users.s3_client = self.original_s3

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

    def test_get_profile_with_avatar_key_returns_picture_url(self):
        event = _make_event()
        self.mock_table.get_item.return_value = {
            'Item': {'user_id': 'user123', 'picture': 'avatars/user123-1700000000.jpg'}
        }
        self.mock_s3.generate_presigned_url.return_value = 'https://signed.example/avatar.jpg'

        with patch.dict(os.environ, {'AVATARS_BUCKET_NAME': 'test-bucket'}, clear=False):
            response = users.get_profile(event)

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(body['picture'], 'avatars/user123-1700000000.jpg')
        self.assertEqual(body['picture_url'], 'https://signed.example/avatar.jpg')
        self.mock_s3.generate_presigned_url.assert_called_with(
            'get_object',
            Params={'Bucket': 'test-bucket', 'Key': 'avatars/user123-1700000000.jpg'},
            ExpiresIn=900,
        )

    def test_get_profile_normalizes_legacy_s3_url_picture(self):
        event = _make_event()
        self.mock_table.get_item.return_value = {
            'Item': {
                'user_id': 'user123',
                'picture': 'https://test-bucket.s3.us-east-1.amazonaws.com/avatars/user123-1700000000.jpg',
            }
        }
        self.mock_s3.generate_presigned_url.return_value = 'https://signed.example/avatar.jpg'

        with patch.dict(os.environ, {'AVATARS_BUCKET_NAME': 'test-bucket'}, clear=False):
            response = users.get_profile(event)

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(body['picture'], 'avatars/user123-1700000000.jpg')
        self.assertEqual(body['picture_url'], 'https://signed.example/avatar.jpg')

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
        self.mock_s3.generate_presigned_url.return_value = 'https://signed.example/avatar.jpg'

        with patch.dict(os.environ, {'AVATARS_BUCKET_NAME': 'test-bucket'}, clear=False):
            response = users.update_profile(event)

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(body['picture'], 'avatars/user123-1700000000.jpg')
        self.assertEqual(body['picture_url'], 'https://signed.example/avatar.jpg')

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

    def test_create_avatar_upload_url(self):
        self.mock_s3.generate_presigned_url.return_value = (
            'https://s3.amazonaws.com/test-bucket/avatars/user123.jpg'
        )

        event = _make_event({'content_type': 'image/jpeg'})

        with patch.dict(os.environ, {'AVATARS_BUCKET_NAME': 'test-bucket'}, clear=False):
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
        self.assertEqual(body['expires_in'], 300)
        self.assertNotIn('public_url', body)


    # ── get_profile error paths ──────────────────────────────────────────────

    def test_get_profile_missing_user_id(self):
        """Missing user_id in claims → 401."""
        event = {
            'requestContext': {
                'authorizer': {'jwt': {'claims': {}}}  # No 'sub'
            },
            'headers': {'origin': 'http://localhost:5173'},
        }
        response = users.get_profile(event)
        self.assertEqual(response['statusCode'], 401)

    def test_get_profile_table_is_none(self):
        """users_table is None → 500."""
        original = users.users_table
        users.users_table = None
        try:
            event = _make_event()
            response = users.get_profile(event)
            self.assertEqual(response['statusCode'], 500)
            self.assertIn('Database', json.loads(response['body']).get('error', ''))
        finally:
            users.users_table = original

    def test_get_profile_dynamodb_exception(self):
        """DynamoDB exception on get_item → 500."""
        self.mock_table.get_item.side_effect = Exception("DDB timeout")
        event = _make_event()
        response = users.get_profile(event)
        self.assertEqual(response['statusCode'], 500)

    # ── update_profile error paths ─────────────────────────────────────────

    def test_update_profile_missing_user_id(self):
        """Missing user_id → 401."""
        event = {
            'requestContext': {
                'authorizer': {'jwt': {'claims': {}}}
            },
            'headers': {'origin': 'http://localhost:5173'},
            'body': json.dumps({'name': 'Test'}),
        }
        response = users.update_profile(event)
        self.assertEqual(response['statusCode'], 401)

    def test_update_profile_no_body(self):
        """Missing body → 400."""
        event = _make_event()
        event['body'] = None
        response = users.update_profile(event)
        self.assertEqual(response['statusCode'], 400)
        self.assertIn('Missing', json.loads(response['body']).get('error', ''))

    def test_update_profile_invalid_json(self):
        """Invalid JSON → 400."""
        event = _make_event()
        event['body'] = '{invalid_json'
        response = users.update_profile(event)
        self.assertEqual(response['statusCode'], 400)
        self.assertIn('Invalid JSON', json.loads(response['body']).get('error', ''))

    def test_update_profile_name_not_string(self):
        """name as non-string → 400."""
        event = _make_event({'name': 12345})
        response = users.update_profile(event)
        self.assertEqual(response['statusCode'], 400)
        self.assertIn('name', json.loads(response['body']).get('error', '').lower())

    def test_update_profile_name_empty(self):
        """Empty name → 400."""
        event = _make_event({'name': '   '})
        response = users.update_profile(event)
        self.assertEqual(response['statusCode'], 400)

    def test_update_profile_name_too_long(self):
        """Name > 255 chars → 400."""
        event = _make_event({'name': 'A' * 256})
        response = users.update_profile(event)
        self.assertEqual(response['statusCode'], 400)

    def test_update_profile_phone_too_long(self):
        """phone_number > 30 chars → 400."""
        event = _make_event({'phone_number': '1' * 31})
        response = users.update_profile(event)
        self.assertEqual(response['statusCode'], 400)

    def test_update_profile_no_valid_fields(self):
        """Only invalid fields → 400."""
        event = _make_event({'role': 'admin', 'email': 'hack@evil.com'})
        response = users.update_profile(event)
        self.assertEqual(response['statusCode'], 400)
        self.assertIn('No valid fields', json.loads(response['body']).get('error', ''))

    def test_update_profile_dynamodb_exception(self):
        """General DynamoDB exception → 500."""
        event = _make_event({'name': 'Valid Name'})
        self.mock_table.update_item.side_effect = Exception("DDB timeout")
        response = users.update_profile(event)
        self.assertEqual(response['statusCode'], 500)

    # ── create_avatar_upload_url error paths ───────────────────────────────

    def test_create_avatar_upload_url_missing_user_id(self):
        """Missing user_id → 401."""
        event = {
            'requestContext': {
                'authorizer': {'jwt': {'claims': {}}}
            },
            'headers': {'origin': 'http://localhost:5173'},
        }
        response = users.create_avatar_upload_url(event)
        self.assertEqual(response['statusCode'], 401)

    def test_create_avatar_upload_url_no_bucket(self):
        """AVATARS_BUCKET_NAME not set → 500."""
        event = _make_event({'content_type': 'image/jpeg'})
        with patch.dict(os.environ, {}, clear=True):
            # Remove AVATARS_BUCKET_NAME from env
            os.environ.pop('AVATARS_BUCKET_NAME', None)
            response = users.create_avatar_upload_url(event)
        self.assertEqual(response['statusCode'], 500)
        self.assertIn('Storage', json.loads(response['body']).get('error', ''))

    def test_create_avatar_upload_url_s3_exception(self):
        """S3 presigned URL exception → 500."""
        event = _make_event({'content_type': 'image/jpeg'})
        self.mock_s3.generate_presigned_url.side_effect = Exception("S3 error")
        with patch.dict(os.environ, {'AVATARS_BUCKET_NAME': 'test-bucket'}, clear=False):
            response = users.create_avatar_upload_url(event)
        self.assertEqual(response['statusCode'], 500)


if __name__ == '__main__':
    unittest.main()
