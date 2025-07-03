# AWS Secrets Manager Setup for CraicGPT Multi-Provider Support

## Overview

CraicGPT now supports multiple AI model providers (OpenAI, Anthropic Direct, Google Gemini) in addition to AWS Bedrock. API keys for external providers are securely stored in AWS Secrets Manager.

## Required Secrets

### 1. OpenAI API Key
**Secret Name:** `craicgpt/openai-api-key`
**Secret Value Format:**
```json
{
  "api_key": "sk-your-openai-api-key-here"
}
```

### 2. Anthropic API Key
**Secret Name:** `craicgpt/anthropic-api-key`
**Secret Value Format:**
```json
{
  "api_key": "sk-ant-your-anthropic-api-key-here"
}
```

### 3. Google API Key
**Secret Name:** `craicgpt/google-api-key`
**Secret Value Format:**
```json
{
  "api_key": "your-google-api-key-here"
}
```

## Setup Instructions

### Using AWS CLI

1. **Create OpenAI Secret:**
```bash
aws secretsmanager create-secret \
    --name "craicgpt/openai-api-key" \
    --description "OpenAI API key for CraicGPT multi-provider support" \
    --secret-string '{"api_key":"sk-your-openai-api-key-here"}'
```

2. **Create Anthropic Secret:**
```bash
aws secretsmanager create-secret \
    --name "craicgpt/anthropic-api-key" \
    --description "Anthropic API key for CraicGPT multi-provider support" \
    --secret-string '{"api_key":"sk-ant-your-anthropic-api-key-here"}'
```

3. **Create Google Secret:**
```bash
aws secretsmanager create-secret \
    --name "craicgpt/google-api-key" \
    --description "Google API key for CraicGPT multi-provider support" \
    --secret-string '{"api_key":"your-google-api-key-here"}'
```

### Using AWS Console

1. Navigate to AWS Secrets Manager in the AWS Console
2. Click "Store a new secret"
3. Select "Other type of secret"
4. Choose "Plaintext" and enter the JSON format shown above
5. Set the secret name as specified
6. Complete the wizard with default settings

## Environment Variables

Update your Lambda environment variables to reference the secrets:

```bash
OPENAI_SECRET_NAME=craicgpt/openai-api-key
ANTHROPIC_SECRET_NAME=craicgpt/anthropic-api-key
GOOGLE_SECRET_NAME=craicgpt/google-api-key
```

## IAM Permissions

Ensure your Lambda execution role has the following permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue"
            ],
            "Resource": [
                "arn:aws:secretsmanager:*:*:secret:craicgpt/openai-api-key*",
                "arn:aws:secretsmanager:*:*:secret:craicgpt/anthropic-api-key*",
                "arn:aws:secretsmanager:*:*:secret:craicgpt/google-api-key*"
            ]
        }
    ]
}
```

## API Key Sources

### OpenAI
- Visit [OpenAI API Keys](https://platform.openai.com/api-keys)
- Create a new API key
- Set usage limits as needed

### Anthropic
- Visit [Anthropic Console](https://console.anthropic.com/)
- Go to API Keys section
- Generate a new API key

### Google
- Visit [Google AI Studio](https://aistudio.google.com/app/apikey)
- Create a new API key
- Configure project access as needed

## Security Best Practices

1. **Rotate Keys Regularly**: Set up automatic rotation where possible
2. **Limit Permissions**: Use least privilege access for API keys
3. **Monitor Usage**: Set up billing alerts and usage monitoring
4. **Audit Access**: Review CloudTrail logs for secret access

## Troubleshooting

### Common Issues

1. **"API key not found in secret"**
   - Verify the secret exists and contains the correct JSON structure
   - Check the key name matches exactly: `api_key`

2. **"Failed to retrieve API key"**
   - Verify IAM permissions for `secretsmanager:GetSecretValue`
   - Check the secret name environment variables

3. **"requests library not available"**
   - Ensure the Lambda layer includes the `requests` library
   - For Bedrock-only deployments, this is not required

### Testing Secrets

You can test secret retrieval using AWS CLI:

```bash
aws secretsmanager get-secret-value --secret-id craicgpt/openai-api-key
```

## Cost Considerations

- AWS Secrets Manager charges $0.40 per secret per month
- API calls: $0.05 per 10,000 requests
- External provider costs vary by usage:
  - OpenAI: Pay per token
  - Anthropic: Pay per token  
  - Google: Free tier available, then pay per token

## Integration Notes

The secrets are cached within Lambda execution contexts for performance. The cache is cleared between cold starts, ensuring fresh credentials are retrieved when needed.

All handlers (llmHandler, imageGenHandler, PromptGenerator) support the same secrets management pattern for consistency.