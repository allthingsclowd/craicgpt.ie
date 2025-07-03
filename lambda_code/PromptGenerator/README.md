# PromptGenerator - Multi-Provider Prompt Generation

**Unified Prompt Engineering for All AI Providers**

The PromptGenerator function creates optimized prompts for all supported AI model providers, implementing explicit prompt engineering parameters and educational best practices. This is the first step in the content generation pipeline.

## 🎯 Purpose

Generate high-quality prompts optimized for different AI providers while maintaining consistency across models. The function creates 13 prompts per date (5 LLM + 8 Image) with provider-specific optimizations and explicit prompt engineering parameters.

## 🏗️ Architecture

### **Multi-Provider Prompt Engineering**
```
Input (Date Range) ──┐
                     │
Context Gathering ───┼──► Prompt Templates ──► Provider Optimization ──► S3 Storage
│                    │
├─ Weather Data      │
├─ News Headlines    │
├─ Family Context    │
├─ Tech Trends       │
└─ Local Events      │
```

### **Supported Providers**
- **AWS Bedrock**: Claude, Titan Text/Image, Nova Canvas (IAM authentication)
- **OpenAI**: GPT-4, O3 Mini, DALL-E 3 (API key via Secrets Manager)
- **Anthropic Direct**: Claude 3.5 Sonnet with vision (API key via Secrets Manager)
- **Google Gemini**: Gemini Pro, Pro Vision, Ultra (API key via Secrets Manager)

## 🚀 Key Features

### **Explicit Prompt Engineering Parameters**
All prompts include visible parameters showing best practices:

```python
class PromptParameters:
    # Temperature: Controls randomness/creativity
    TEMP_FACTUAL = 0.2      # For technical comparisons
    TEMP_BALANCED = 0.6     # For articles, stories
    TEMP_CREATIVE = 0.9     # For diary entries, jokes
    
    # Max tokens: Controls response length
    TOKENS_SHORT = 150      # For jokes, headlines
    TOKENS_MEDIUM = 500     # For stories, bios
    TOKENS_LONG = 800       # For articles
    
    # Top-p: Controls diversity via nucleus sampling
    TOP_P_FOCUSED = 0.3     # Formal content
    TOP_P_BALANCED = 0.7    # General content
    TOP_P_CREATIVE = 0.95   # Creative content
```

### **Component Influence Mapping**
Clear relationships between context and generated content:

- **Weather Context** → Natural mood setting and opening material
- **News Headlines** → "Headline hijacking" for personal connection
- **Family Context** → Content for "family follies" section
- **Tech Trends** → Work-related anecdotes and technical context
- **Local Events** → Community-based story material

### **Provider-Specific Optimization**
```python
def get_model_configs() -> Dict[str, ModelConfig]:
    configs = {}
    
    # AWS Bedrock models
    configs["claude-3-sonnet-bedrock"] = ModelConfig(
        provider=ModelProvider.AWS_BEDROCK,
        model_id="anthropic.claude-3-sonnet-20240229-v1:0",
        temperature=0.7,
        max_tokens=1000,
        top_p=0.9
    )
    
    # OpenAI models  
    configs["gpt-4"] = ModelConfig(
        provider=ModelProvider.OPENAI,
        model_id="gpt-4",
        temperature=0.7,
        max_tokens=1500,
        top_p=0.9,
        presence_penalty=0.1,
        frequency_penalty=0.1,
        api_endpoint="https://api.openai.com/v1/chat/completions"
    )
```

## 📁 Generated Content Types

### **LLM Prompts (5 per date)**
- **llm_01**: Main Article (title + text)
- **llm_02**: Comparison Article (title + text)  
- **llm_03**: LLM Story (content)
- **llm_04**: Daily Joke (content)
- **llm_05**: Author Bio (content)

### **Image Prompts (8 per date)**
- **img_01**: Main Article illustration
- **img_02**: Comparison Article illustration
- **img_03-06**: Advertisement content (4 slots)
- **img_07**: LLM Story illustration
- **img_08**: Joke illustration

## 🔧 Technical Implementation

### **Function Configuration**
- **Runtime**: Python 3.12
- **Memory**: 512 MB
- **Timeout**: 5 minutes
- **Handler**: `lambda_function.lambda_handler`

### **Environment Variables**
```bash
# Required
PROMPT_BUCKET=your-s3-bucket-name
START_DATE=2025-01-15  # Optional: defaults to current date
END_DATE=2025-01-15    # Optional: defaults to START_DATE

# Multi-provider secrets (optional for external providers)
OPENAI_SECRET_NAME=craicgpt/openai-api-key
ANTHROPIC_SECRET_NAME=craicgpt/anthropic-api-key
GOOGLE_SECRET_NAME=craicgpt/google-api-key
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
        "secretsmanager:GetSecretValue"
      ],
      "Resource": [
        "arn:aws:secretsmanager:*:*:secret:craicgpt/*"
      ]
    }
  ]
}
```

## 📊 Output Format

### **S3 Storage Structure**
```
s3://bucket/static_assets/content/prompts/YYYY/MM/DD/
├── llm_01.json    # Main article prompt
├── llm_02.json    # Comparison article prompt
├── llm_03.json    # LLM story prompt
├── llm_04.json    # Joke prompt
├── llm_05.json    # Author bio prompt
├── img_01.json    # Main article image prompt
├── img_02.json    # Comparison image prompt
├── img_03.json    # Advertisement 1 prompt
├── img_04.json    # Advertisement 2 prompt
├── img_05.json    # Advertisement 3 prompt
├── img_06.json    # Advertisement 4 prompt
├── img_07.json    # LLM story image prompt
└── img_08.json    # Joke image prompt
```

### **Prompt JSON Format**
```json
{
  "prompt_id": "llm_01",
  "content_type": "main_article",
  "date": "2025-01-15",
  "prompt": "You are an AI journalist writing for 'The Artificially Intelligent Times'...",
  "model_configs": {
    "gpt-4": {
      "provider": "openai",
      "temperature": 0.7,
      "max_tokens": 1500,
      "top_p": 0.9,
      "presence_penalty": 0.1,
      "frequency_penalty": 0.1
    },
    "claude-3-sonnet": {
      "provider": "bedrock",
      "temperature": 0.7,
      "max_tokens": 1000,
      "top_p": 0.9
    }
  },
  "context": {
    "weather": "Sunny, 15°C in Pontesbury",
    "news_headlines": ["AI reaches new milestone", "Tech stocks surge"],
    "local_events": ["Shropshire tech meetup tonight"]
  },
  "generation_timestamp": "2025-01-15T10:30:00Z"
}
```

## 🔄 Execution Modes

### **Scheduled Execution** (Production)
Triggered daily by EventBridge Scheduler:
```json
{
  "START_DATE": "2025-01-15",
  "END_DATE": "2025-01-15"
}
```

### **Manual Execution** (Development)
```bash
# Generate prompts for specific date range
aws lambda invoke \
  --function-name craicgptie_prompt_generator \
  --payload '{
    "START_DATE": "2025-01-15",
    "END_DATE": "2025-01-20"
  }' \
  --cli-binary-format raw-in-base64-out \
  response.json

cat response.json | jq '.'
```

### **Local Testing**
```python
# Test locally
if __name__ == "__main__":
    test_event = {
        "START_DATE": "2025-01-15",
        "END_DATE": "2025-01-15"
    }
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))
```

## 📈 Performance & Optimization

### **Context Gathering Performance**
- **Weather API**: Cached for 1 hour to reduce API calls
- **News Scraping**: Parallel fetching with 5-second timeout
- **Content Caching**: Reuse context data across prompt types

### **Prompt Generation Metrics**
- **Processing Time**: ~30 seconds for 5-day range
- **Success Rate**: >99% prompt generation
- **Cache Hit Rate**: >80% for weather/news data
- **S3 Upload Speed**: ~2 seconds per prompt file

### **Cost Optimization**
- Minimal external API calls (weather only)
- Efficient S3 operations with batch uploads
- Smart caching to reduce redundant operations
- Optimized Lambda memory allocation

## 🔍 Monitoring & Debugging

### **CloudWatch Logs**
```bash
# Monitor prompt generation
aws logs tail /aws/lambda/craicgptie_prompt_generator --follow

# Check for specific errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie_prompt_generator \
  --filter-pattern 'ERROR' \
  --start-time $(date -v-1H +%s)000

# Monitor performance
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie_prompt_generator \
  --filter-pattern 'Processing time'
```

### **Success Metrics**
```bash
# Check prompt generation stats
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie_prompt_generator \
  --filter-pattern '"prompts_generated"'

# Verify S3 uploads
aws s3 ls s3://your-bucket/static_assets/content/prompts/2025/01/15/ --recursive
```

## 🐛 Troubleshooting

### **Common Issues**

**Missing Context Data**
- Check weather API key and endpoint
- Verify news source accessibility
- Review context gathering timeout settings

**S3 Upload Failures**
- Verify S3 bucket permissions
- Check bucket name in environment variables
- Validate S3 key naming format

**Provider Configuration Issues**
- Check secrets manager configuration
- Verify model ID formatting
- Review provider-specific parameters

**Performance Issues**
- Monitor Lambda memory usage
- Check external API response times
- Review parallel processing limits

### **Debug Commands**
```bash
# Test S3 connectivity
aws s3 cp test.txt s3://your-bucket/test.txt
aws s3 rm s3://your-bucket/test.txt

# Test secrets access
aws secretsmanager get-secret-value --secret-id craicgpt/openai-api-key

# Check function configuration
aws lambda get-function-configuration --function-name craicgptie_prompt_generator
```

## 🤝 Contributing

### **Adding New Prompt Types**
1. Define new prompt template in prompt generation logic
2. Add model-specific configurations
3. Update S3 storage structure
4. Add validation and testing

### **Provider Integration**
1. Add new provider enum and configuration
2. Implement provider-specific parameter mapping
3. Add secrets management support
4. Update documentation and examples

### **Prompt Engineering Improvements**
- Enhance context gathering sources
- Improve model-specific optimizations
- Add A/B testing capabilities
- Implement prompt effectiveness metrics

**Unified Prompt Engineering - Production Ready** 📝