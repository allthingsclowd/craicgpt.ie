# Lambda Code - Serverless Backend Functions

**Multi-Provider AI Content Generation Pipeline**

This directory contains the serverless backend functions that power the CraicGPT.ie content generation system. The pipeline supports multiple AI model providers and implements advanced orchestration with strict concurrency controls.

## 🏗️ Architecture Overview

### **Four-Function Pipeline**
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│                 │    │                 │    │                 │
│ PromptGenerator │───▶│ Orchestrator    │───▶│ Content Workers │
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                      │
                                                      ├─ llmHandler
                                                      └─ imageGenHandler
```

### **Execution Flow**
1. **PromptGenerator**: Creates optimized prompts for all providers and dates
2. **Orchestrator**: Coordinates execution with 10 Lambda concurrency limit
3. **llmHandler**: Generates text content using multiple LLM providers  
4. **imageGenHandler**: Generates images using multiple image providers

## 📁 Directory Structure

```
lambda_code/
├── PromptGenerator/           # Multi-provider prompt generation
│   ├── lambda_function.py     # Main handler
│   └── README.md              # Component documentation
├── orchestrator/              # Workflow coordination
│   ├── lambda_function.py     # Main handler  
│   └── README.md              # Component documentation
├── llmHandler/                # Text generation
│   ├── lambda_function.py     # Main handler
│   └── README.md              # Component documentation
├── imageGenHandler/           # Image generation
│   ├── lambda_function.py     # Main handler
│   └── README.md              # Component documentation
└── README.md                  # This file
```

## 🚀 Key Features

### **Multi-Provider Support**
- ✅ **Unified Interface**: Single codebase supporting all major AI providers
- ✅ **Provider Detection**: Automatic routing based on model IDs
- ✅ **Secrets Management**: Secure API key handling via AWS Secrets Manager
- ✅ **Error Handling**: Comprehensive retry logic and fallback mechanisms

### **Supported Providers**

**Text Generation (LLM)**:
- **AWS Bedrock**: Claude Sonnet/Haiku, Titan Text (IAM authentication)
- **OpenAI**: GPT-4, O3 Mini (API key via Secrets Manager)
- **Anthropic Direct**: Claude 3.5 Sonnet, Claude 3 Opus (API key via Secrets Manager)
- **Google Gemini**: Gemini Pro, Gemini Ultra (API key via Secrets Manager)

**Image Generation**:
- **AWS Bedrock**: Titan Image Generator, Nova Canvas (IAM authentication)
- **OpenAI**: DALL-E 3 (API key via Secrets Manager)

### **Advanced Orchestration**
- ✅ **10 Lambda Limit**: Hard enforcement (orchestrator + 9 workers max)
- ✅ **CloudWatch Monitoring**: Real-time concurrency tracking
- ✅ **Dependency Management**: LLM completion before image generation
- ✅ **Idempotent Execution**: Safe to rerun on failures
- ✅ **Rate Limiting**: Provider-specific throttling controls

## 🔧 Function Specifications

### **PromptGenerator Function**
- **Purpose**: Generate prompts optimized for all AI providers
- **Runtime**: Python 3.12
- **Memory**: 512 MB
- **Timeout**: 5 minutes
- **Trigger**: EventBridge Scheduler (daily) or manual invocation
- **Output**: 13 prompts per date (5 LLM + 8 Image) stored in S3

### **Orchestrator Function**  
- **Purpose**: Coordinate workflow execution with concurrency control
- **Runtime**: Python 3.12
- **Memory**: 1024 MB
- **Timeout**: 15 minutes
- **Trigger**: EventBridge Scheduler (after prompt generation) or manual
- **Concurrency**: Limited to ensure max 10 total Lambda executions

### **llmHandler Function**
- **Purpose**: Generate text content using multiple LLM providers
- **Runtime**: Python 3.12
- **Memory**: 1024 MB
- **Timeout**: 10 minutes
- **Invocation**: Synchronous via orchestrator
- **Output**: Text content stored in paper_content.json

### **imageGenHandler Function**
- **Purpose**: Generate images using multiple image providers
- **Runtime**: Python 3.12  
- **Memory**: 2048 MB
- **Timeout**: 15 minutes (images take longer)
- **Invocation**: Synchronous via orchestrator
- **Output**: Images and metadata in paper_content.json

## 🔐 Security & Secrets Management

### **AWS Secrets Manager Integration**
All functions use centralized secret management:

```python
# Example secret retrieval (implemented in all handlers)
def get_api_key(secret_name: str, cache_key: str) -> str:
    """Get API key from AWS Secrets Manager with caching"""
    response = secrets.get_secret_value(SecretId=secret_name)
    secret_data = json.loads(response['SecretString'])
    return secret_data.get('api_key')
```

### **Required Secrets**
- `craicgpt/openai-api-key`: OpenAI API key
- `craicgpt/anthropic-api-key`: Anthropic API key  
- `craicgpt/google-api-key`: Google API key

### **IAM Permissions**
Each function requires:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::bucket-name/*"
    },
    {
      "Effect": "Allow", 
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:*:*:secret:craicgpt/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": "*"
    }
  ]
}
```

## 📊 Monitoring & Logging

### **CloudWatch Integration**
All functions implement comprehensive logging:

```python
# Standardized logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("function_name")
```

### **Key Metrics**
- **Processing Time**: Track execution duration per model/date
- **Success Rate**: Monitor completion rates across providers
- **Error Patterns**: Identify common failure modes
- **Concurrency Usage**: Track Lambda concurrency consumption
- **Token Usage**: Monitor AI provider API consumption

### **Monitoring Commands**
```bash
# Monitor all functions
aws logs tail /aws/lambda/craicgptie_prompt_generator --follow
aws logs tail /aws/lambda/craicgptie-orchestrator --follow  
aws logs tail /aws/lambda/craicgptie_llm_runner --follow
aws logs tail /aws/lambda/craicgptie_image_runner --follow

# Check for errors across all functions
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie-orchestrator \
  --filter-pattern 'ERROR' \
  --start-time $(date -v-1H +%s)000

# Monitor concurrency compliance
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie-orchestrator \
  --filter-pattern '"CRITICAL: 10 Lambda limit"'
```

## 🔄 Deployment

### **Terraform Deployment** (Recommended)
```bash
cd terraform/backend
terraform init
terraform plan
terraform apply
```

### **Manual Deployment**
Each function can be deployed individually:

```bash
# Create deployment package
cd lambda_code/PromptGenerator
zip -r function.zip lambda_function.py

# Update function code
aws lambda update-function-code \
  --function-name craicgptie_prompt_generator \
  --zip-file fileb://function.zip

# Update environment variables
aws lambda update-function-configuration \
  --function-name craicgptie_prompt_generator \
  --environment Variables='{
    "PROMPT_BUCKET":"your-bucket-name",
    "OPENAI_SECRET_NAME":"craicgpt/openai-api-key"
  }'
```

## 🧪 Testing

### **Unit Testing**
Each function includes test utilities:

```bash
# Test prompt generation
cd lambda_code/PromptGenerator
python lambda_function.py  # Local test mode

# Test with specific date range
aws lambda invoke \
  --function-name craicgptie_prompt_generator \
  --payload '{"START_DATE":"2025-01-15","END_DATE":"2025-01-15"}' \
  response.json
```

### **Integration Testing** 
```bash
# Test complete pipeline
cd /Users/graz/repos/craicgpt.ie
python test_date_range.py  # End-to-end test
python test_idempotent_processing.py  # Idempotency test
```

## 🐛 Troubleshooting

### **Common Issues**

**Concurrency Limits**
- Check orchestrator environment variables
- Monitor CloudWatch concurrency metrics
- Adjust `MAX_ACCOUNT_CONCURRENT` if needed

**API Key Issues**
- Verify secrets exist in AWS Secrets Manager
- Check IAM permissions for secret access
- Validate secret JSON format

**Provider Errors**
- Check provider-specific error codes
- Verify API quotas and rate limits
- Review model availability in regions

**S3 Permissions**
- Verify bucket permissions for read/write
- Check CORS configuration for frontend access
- Validate S3 key naming conventions

### **Debug Tools**
```bash
# Check function configuration
aws lambda get-function-configuration --function-name craicgptie-orchestrator

# Test specific provider
aws lambda invoke \
  --function-name craicgptie_llm_runner \
  --payload '{"date":"2025-01-15","model_id":"gpt-4","worker_mode":true}' \
  debug.json

# Monitor real-time logs
aws logs tail /aws/lambda/craicgptie-orchestrator --follow --filter-pattern 'ERROR'
```

## 🤝 Contributing

### **Development Guidelines**
- Follow Python PEP 8 style guidelines
- Include comprehensive error handling
- Add detailed logging for debugging
- Implement proper retry mechanisms
- Write unit tests for new features

### **Adding New Providers**
1. Update provider detection logic
2. Add provider-specific API integration
3. Include secrets management configuration
4. Update environment variable documentation
5. Add comprehensive error handling

### **Performance Optimization**
- Minimize cold start times
- Optimize memory allocation
- Implement efficient caching
- Reduce external API calls
- Profile execution times

**Serverless Backend - Production Ready** ⚡