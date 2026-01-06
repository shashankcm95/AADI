import json

def lambda_handler(event, context):
    path = event.get("rawPath") or event.get("path")
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"ok": True, "path": path}),
    }

