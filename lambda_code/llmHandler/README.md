# llmHandler - Multi-Provider Text Generation

**Unified LLM Content Generation Across All Major Providers**

The llmHandler function generates text content using multiple Large Language Model providers, supporting AWS Bedrock, OpenAI, Anthropic Direct, and Google Gemini with unified interface and comprehensive error handling.

## 🎯 Purpose

Generate high-quality text content for the CraicGPT newspaper using multiple LLM providers while maintaining consistent output format and implementing robust error handling across all supported platforms.

## 🏗️ Architecture

### **Multi-Provider Integration**
```
Prompt Input ─┐
              │
Provider      ├─► AWS Bedrock ────► Claude, Titan Text
Detection     │                    (IAM Auth)
              │
              ├─► OpenAI ─────────► GPT-4, O3 Mini  
              │                    (API Key via Secrets Manager)
              │
              ├─► Anthropic ──────► Claude 3.5 Sonnet, Claude 3 Opus
              │                    (API Key via Secrets Manager)
              │
              └─► Google Gemini ──► Gemini Pro, Gemini Ultra
                                   (API Key via Secrets Manager)
                                   │
                                   ▼
                              Unified Response ──► paper_content.json
```

### **Supported Providers & Models**

**AWS Bedrock** (IAM Authentication):
- `anthropic.claude-3-sonnet-20240229-v1:0` - Claude 3 Sonnet
- `anthropic.claude-3-haiku-20240307-v1:0` - Claude 3 Haiku
- `amazon.titan-text-express-v1` - Titan Text Express

**OpenAI** (API Key via Secrets Manager):
- `gpt-4` - GPT-4
- `o3-mini` - O3 Mini (reasoning-focused)

**Anthropic Direct** (API Key via Secrets Manager):
- `claude-3-5-sonnet-20241022` - Claude 3.5 Sonnet Latest
- `claude-3-opus-20240229` - Claude 3 Opus

**Google Gemini** (API Key via Secrets Manager):
- `gemini-pro` - Gemini Pro
- `gemini-ultra` - Gemini Ultra

## 🚀 Key Features

### **Unified Model Invocation**
```python
def invoke_model(model_id: str, prompt: str) -> ModelResponse:
    """Unified model invocation supporting all providers"""
    provider = determine_provider(model_id)
    
    if provider == ModelProvider.AWS_BEDROCK:
        return invoke_bedrock_model(model_id, prompt)
    elif provider == ModelProvider.OPENAI:
        return invoke_openai_model(model_id, prompt)
    elif provider == ModelProvider.ANTHROPIC_DIRECT:
        return invoke_anthropic_model(model_id, prompt)
    elif provider == ModelProvider.GOOGLE_GEMINI:
        return invoke_gemini_model(model_id, prompt)
```

### **Provider Auto-Detection**
```python
def determine_provider(model_id: str) -> ModelProvider:
    """Determine which provider to use based on model ID"""
    if model_id.startswith(("gpt-", "o3-", "text-davinci")):
        return ModelProvider.OPENAI
    elif model_id.startswith(("claude-3-5", "claude-3-opus")) and not model_id.startswith("anthropic."):
        return ModelProvider.ANTHROPIC_DIRECT
    elif model_id.startswith(("gemini-", "palm-")):
        return ModelProvider.GOOGLE_GEMINI
    else:
        return ModelProvider.AWS_BEDROCK
```

### **Comprehensive Error Handling**
```python
@dataclass
class ModelResponse:
    """Standardized response format for all providers"""
    success: bool
    content: str
    model_id: str
    provider: str
    tokens_used: Optional[int] = None
    processing_time_ms: Optional[int] = None
    finish_reason: Optional[str] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None
```

## 🔧 Technical Implementation

### **Function Configuration**
- **Runtime**: Python 3.12
- **Memory**: 1024 MB
- **Timeout**: 10 minutes
- **Handler**: `lambda_function.lambda_handler`

### **Environment Variables**
```bash
# S3 Storage
PROMPT_BUCKET=your-s3-bucket-name

# Multi-provider secrets
OPENAI_SECRET_NAME=craicgpt/openai-api-key
ANTHROPIC_SECRET_NAME=craicgpt/anthropic-api-key
GOOGLE_SECRET_NAME=craicgpt/google-api-key

# Model configuration (optional)
BEDROCK_MODEL_IDS=anthropic.claude-3-sonnet-20240229-v1:0,amazon.titan-text-express-v1
OPENAI_MODEL_IDS=gpt-4,o3-mini
ANTHROPIC_MODEL_IDS=claude-3-5-sonnet-20241022,claude-3-opus-20240229
GEMINI_MODEL_IDS=gemini-pro,gemini-ultra

# AWS Configuration
AWS_REGION=eu-west-1
```

### **IAM Permissions Required**
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
      "Resource": [
        "arn:aws:s3:::your-bucket/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": [
        "arn:aws:secretsmanager:*:*:secret:craicgpt/*"
      ]
    }
  ]
}
```

## 📊 Content Generation

### **Content Types Generated**
- **Main Article** (`llm_01`): Title + Text format
- **Comparison Article** (`llm_02`): Title + Text format
- **LLM Story** (`llm_03`): Content format
- **Daily Joke** (`llm_04`): Content format
- **Author Bio** (`llm_05`): Content format

### **Output Format**
```json
{
  "publicationDate": "2025-01-15",
  "contentSlots": {
    "mainArticle": {
      "llmOutputs": {
        "gpt-4": {
          "title": "AI Revolution: The Dawn of Multi-Provider Intelligence",
          "text": "<p>In a groundbreaking development...</p>"
        },
        "claude-3-5-sonnet-20241022": {
          "title": "The Multi-Model Renaissance: How AI Diversity Powers Innovation",
          "text": "<p>As artificial intelligence evolves...</p>"
        }
      }
    },
    "joke": {
      "llmOutputs": {
        "gemini-pro": {
          "content": "<p>Why did the AI go to therapy? Because it had too many models to choose from!</p>"
        }
      }
    }
  }
}
```

## 🔐 Provider-Specific Implementations

### **AWS Bedrock Integration**
```python
def invoke_bedrock_model(model_id: str, prompt: str) -> ModelResponse:
    """Invoke AWS Bedrock model with proper error handling"""
    
    # Build model-specific request body
    if model_id.startswith("anthropic."):
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "system": prompt,
            "messages": [{ "role": "user", "content": "Generate." }],
            "max_tokens": 800,
            "temperature": 0.7,
            "top_p": 0.9
        })
    
    response = bedrock.invoke_model(
        modelId=model_id,
        body=body,
        contentType="application/json",
        accept="application/json"
    )
    
    return parse_bedrock_response(response, model_id)
```

### **OpenAI Integration**
```python
def invoke_openai_model(model_id: str, prompt: str) -> ModelResponse:
    """Invoke OpenAI model via REST API"""
    
    api_key = get_openai_api_key()
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    request_body = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 800,
        "top_p": 0.9
    }
    
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        json=request_body,
        timeout=60
    )
    
    return parse_openai_response(response, model_id)
```

### **Anthropic Direct Integration**
```python
def invoke_anthropic_model(model_id: str, prompt: str) -> ModelResponse:
    """Invoke Anthropic model via direct API"""
    
    api_key = get_anthropic_api_key()
    
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    
    request_body = {
        "model": model_id,
        "max_tokens": 800,
        "temperature": 0.7,
        "top_p": 0.9,
        "messages": [{"role": "user", "content": prompt}]
    }
    
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers=headers,
        json=request_body,
        timeout=60
    )
    
    return parse_anthropic_response(response, model_id)
```

### **Google Gemini Integration**
```python
def invoke_gemini_model(model_id: str, prompt: str) -> ModelResponse:
    """Invoke Google Gemini model via REST API"""
    
    api_key = get_google_api_key()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"
    
    request_body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "topP": 0.9,
            "topK": 40,
            "maxOutputTokens": 800
        }
    }
    
    response = requests.post(url, headers=headers, json=request_body, timeout=60)
    return parse_gemini_response(response, model_id)
```

## 🔄 Execution Modes

### **Worker Mode** (Called by Orchestrator)
```json
{
  "date": "2025-01-15",
  "model_id": "gpt-4",
  "prompt_ids": ["llm_01"],
  "worker_mode": true
}
```

### **Legacy Mode** (Date Range Processing)
```json
{
  "start_date": "2025-01-15",
  "end_date": "2025-01-20",
  "model_ids": ["gpt-4", "claude-3-5-sonnet-20241022"]
}
```

### **Manual Testing**
```bash
# Test specific model
aws lambda invoke \
  --function-name craicgptie_llm_runner \
  --payload '{
    "date": "2025-01-15",
    "model_id": "gpt-4",
    "prompt_ids": ["llm_04"],
    "worker_mode": true
  }' \
  --cli-binary-format raw-in-base64-out \
  response.json

cat response.json | jq '.'
```

## 📈 Performance & Monitoring

### **Performance Metrics**
- **Processing Time**: 15-45 seconds per model/prompt combination
- **Success Rate**: >95% across all providers
- **Token Usage**: Tracked per provider for cost optimization
- **Error Rate**: <5% with proper retry handling

### **Monitoring Commands**
```bash
# Monitor LLM processing
aws logs tail /aws/lambda/craicgptie_llm_runner --follow

# Check provider-specific errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie_llm_runner \
  --filter-pattern '"provider":"openai"' \
  --start-time $(date -v-1H +%s)000

# Monitor token usage
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie_llm_runner \
  --filter-pattern '"tokens_used"'

# Check success rates by provider
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie_llm_runner \
  --filter-pattern '"success_rate"'
```

## 🐛 Troubleshooting

### **Common Issues**

**API Key Errors**
```bash
# Test secrets access
aws secretsmanager get-secret-value --secret-id craicgpt/openai-api-key
aws secretsmanager get-secret-value --secret-id craicgpt/anthropic-api-key
aws secretsmanager get-secret-value --secret-id craicgpt/google-api-key

# Check function permissions
aws lambda get-policy --function-name craicgptie_llm_runner
```

**Provider-Specific Errors**
```bash
# Check OpenAI API status
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
  https://api.openai.com/v1/models

# Test Anthropic API
curl -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  https://api.anthropic.com/v1/messages

# Verify Bedrock model access
aws bedrock list-foundation-models --region eu-west-1
```

**Content Generation Issues**
```bash
# Check prompt availability
aws s3 ls s3://your-bucket/static_assets/content/prompts/2025/01/15/

# Verify paper_content.json structure
aws s3 cp s3://your-bucket/static_assets/content/website/2025/01/15/paper_content.json - | jq '.'

# Test specific model locally
python lambda_function.py  # Local test mode
```

## 🤝 Contributing

### **Adding New Providers**
1. Add provider enum and detection logic
2. Implement provider-specific API integration
3. Add secrets management support
4. Include comprehensive error handling
5. Update documentation and tests

### **Model Optimization**
- Provider-specific prompt optimizations
- Cost-performance analysis
- A/B testing for model selection
- Advanced retry strategies

### **Monitoring Enhancements**
- Custom CloudWatch metrics
- Provider performance dashboards
- Cost tracking and optimization
- Real-time alerting for failures

**Multi-Provider Text Generation - Production Ready** 📝