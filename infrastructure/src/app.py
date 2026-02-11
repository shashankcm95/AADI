import json

def lambda_handler(event, context):
    return {
        "statusCode": 200,
        "body": json.dumps({"status": "healthy", "service": "infrastructure"}),
        "headers": {
            "Content-Type": "application/json"
        }
    }