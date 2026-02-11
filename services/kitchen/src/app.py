import json
import boto3
import os

def lambda_handler(event, context):
    """
    Kitchen Service Lambda Handler
    """
    path = event.get('rawPath')
    method = event.get('requestContext', {}).get('http', {}).get('method')
    
    if path == '/v1/kitchen/health':
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Hello from Kitchen Service', 'status': 'healthy'})
        }

    # Placeholder for future logic
    return {
        'statusCode': 404,
        'body': json.dumps({'message': 'Not Found'})
    }
