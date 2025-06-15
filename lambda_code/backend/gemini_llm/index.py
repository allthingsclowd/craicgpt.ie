import json

def handler(event, context):
    print(f"Received event: {json.dumps(event)}")
    # Placeholder response
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Lambda function executed successfully!',
            'input_event': event
        })
    }
