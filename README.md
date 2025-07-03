<p align="center">
  <img src="frontend/static_assets/images/CraicGPT_240h.png" alt="CraicGPT Logo" width="350"/>
  <img src="frontend/static_assets/images/GeekwiththePeak.png" alt="Geek with the Peak Logo" width="150"/>
</p>

# CraicGPT.ie - Multi-Provider AI Newspaper Generator

**Production-Ready Multi-Provider AI Content Generation Platform**

CraicGPT.ie is a sophisticated serverless application that generates daily AI-powered newspapers using multiple model providers. The system demonstrates advanced prompt engineering, multi-provider AI integration, and production-grade infrastructure automation.

## 🏗️ System Architecture

### **Multi-Provider AI Support**
- **AWS Bedrock**: Claude, Titan Text, Titan Image, Nova Canvas (IAM authentication)
- **OpenAI**: GPT-4, O3 Mini, DALL-E 3 (API keys via AWS Secrets Manager)
- **Anthropic Direct**: Claude 3.5 Sonnet, Claude 3 Opus (API keys via AWS Secrets Manager)
- **Google Gemini**: Gemini Pro, Gemini Ultra (API keys via AWS Secrets Manager)

### **Serverless Pipeline Architecture**
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│                 │    │                 │    │                 │    │                 │
│ Prompt          │───▶│ Orchestrator    │───▶│ Content         │───▶│ Static Website  │
│ Generator       │    │                 │    │ Generators      │    │ (S3 + CloudFront)│
│                 │    │                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
       │                       │                       │
       │                       │                       ├─ LLM Handler (Multi-Provider)
       │                       │                       └─ Image Handler (Multi-Provider)
       │                       │
       │                       └─ 10 Lambda Concurrency Limit Enforcement
       │
       └─ Unified Multi-Provider Prompt Engineering
```

### **Core Components**
1. **Unified Prompt Generator**: Creates prompts optimized for all supported providers
2. **Orchestrator**: Manages workflow execution with strict 10 Lambda concurrency limits
3. **Multi-Provider Handlers**: Support text and image generation across all providers
4. **Frontend**: Static newspaper layout with provider selection interface
5. **Infrastructure**: Fully automated Terraform deployment

## 🚀 Key Features

### **Production-Grade Multi-Provider Support**
- ✅ **Single Unified System**: One codebase supporting all major AI providers
- ✅ **Secrets Management**: Secure API key storage via AWS Secrets Manager
- ✅ **Provider Auto-Detection**: Automatic routing based on model IDs
- ✅ **Comprehensive Error Handling**: Retry logic and fallback mechanisms
- ✅ **Backward Compatibility**: Existing integrations continue working

### **Advanced Orchestration**
- ✅ **10 Lambda Limit Compliance**: Hard limit enforcement (orchestrator + 9 workers)
- ✅ **CloudWatch Monitoring**: Real-time concurrency tracking
- ✅ **Idempotent Workflows**: Safe to rerun on failures
- ✅ **Dependency Management**: LLM generation before image generation
- ✅ **Rate Limiting**: Model-specific throttling controls

### **Comprehensive Prompt Engineering**
- ✅ **Explicit Parameters**: Visible temperature, max_tokens, top_p settings
- ✅ **Provider Optimization**: Model-specific prompt formatting
- ✅ **Component Influence Mapping**: Clear relationships between context and content
- ✅ **Educational Documentation**: Learn prompt engineering best practices

## 📁 Repository Documentation Tree

### **Core Documentation**
- [`README.md`](README.md) - This file (main overview)
- [`CLAUDE.md`](CLAUDE.md) - Claude Code assistant documentation
- [`docs/secrets-manager-setup.md`](docs/secrets-manager-setup.md) - AWS Secrets Manager configuration

### **Component Documentation**
- [`frontend/README.md`](frontend/README.md) - Static website and user interface
- [`lambda_code/README.md`](lambda_code/README.md) - Serverless backend functions
- [`lambda_code/PromptGenerator/README.md`](lambda_code/PromptGenerator/README.md) - Multi-provider prompt generation
- [`lambda_code/orchestrator/README.md`](lambda_code/orchestrator/README.md) - Workflow orchestration and concurrency control
- [`lambda_code/llmHandler/README.md`](lambda_code/llmHandler/README.md) - Multi-provider text generation
- [`lambda_code/imageGenHandler/README.md`](lambda_code/imageGenHandler/README.md) - Multi-provider image generation
- [`terraform/README.md`](terraform/README.md) - Infrastructure as Code
- [`terraform/frontend/README.md`](terraform/frontend/README.md) - Frontend infrastructure deployment
- [`terraform/backend/README.md`](terraform/backend/README.md) - Backend infrastructure deployment
- [`prompts/README.md`](prompts/README.md) - Base prompt templates and examples
- [`docs/README.md`](docs/README.md) - Additional documentation and guides

## 🛠️ Quick Start

### **Prerequisites**
- AWS CLI configured with appropriate permissions
- Terraform >= 1.8.0
- Python 3.12+ (for Lambda functions)
- API keys for external providers (OpenAI, Anthropic, Google)

### **1. Deploy Frontend (Fully Automated)**
```bash
cd terraform/frontend
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your domain settings
terraform init
terraform plan
terraform apply
```

### **2. Configure Secrets (Required for Multi-Provider)**
```bash
# Create API key secrets
aws secretsmanager create-secret \
    --name "craicgpt/openai-api-key" \
    --secret-string '{"api_key":"sk-your-openai-key-here"}'

aws secretsmanager create-secret \
    --name "craicgpt/anthropic-api-key" \
    --secret-string '{"api_key":"sk-ant-your-anthropic-key-here"}'

aws secretsmanager create-secret \
    --name "craicgpt/google-api-key" \
    --secret-string '{"api_key":"your-google-api-key-here"}'
```

### **3. Deploy Backend Functions**

#### **Option A: Terraform Deployment (Recommended)**
```bash
cd terraform/backend
# Configure your settings
terraform init
terraform plan
terraform apply
```

#### **Option B: Manual Lambda Deployment**
Each Lambda function requires specific files and dependencies:

```bash
# Deploy LLM Handler (with multi-provider support)
cd lambda_code/llmHandler
cp ../shared/educational_runner.py .
cp ../shared/model_configurations.py .
pip install requests -t .
zip -r llm_handler_complete.zip .
aws lambda update-function-code --function-name craicgptie_llm_runner --zip-file fileb://llm_handler_complete.zip

# Deploy Image Handler (with multi-provider support)
cd ../imageGenHandler
cp ../shared/educational_runner.py .
cp ../shared/model_configurations.py .
pip install requests -t .
zip -r image_handler_complete.zip .
aws lambda update-function-code --function-name craicgptie_image_runner --zip-file fileb://image_handler_complete.zip

# Deploy Prompt Generator (with multi-provider support)
cd ../PromptGenerator
cp ../shared/educational_runner.py .
cp ../shared/model_configurations.py .
pip install requests -t .
zip -r prompt_generator_complete.zip .
aws lambda update-function-code --function-name craicgptie_prompt_generator --zip-file fileb://prompt_generator_complete.zip

# Deploy Orchestrator (coordination only, no external APIs)
cd ../orchestrator
zip -r orchestrator.zip lambda_function.py
aws lambda update-function-code --function-name craicgptie-orchestrator --zip-file fileb://orchestrator.zip
```

#### **Lambda Function Composition**
Each Lambda function contains the following files:

**LLM Handler** (`craicgptie_llm_runner`):
- `lambda_function.py` - Main handler for text generation
- `educational_runner.py` - Multi-provider API calls
- `model_configurations.py` - Model endpoint definitions  
- `requests/` - HTTP library for external APIs
- Dependencies: `urllib3`, `certifi`, `charset_normalizer`, `idna`

**Image Handler** (`craicgptie_image_runner`):
- `lambda_function.py` - Main handler for image generation
- `educational_runner.py` - Multi-provider API calls  
- `model_configurations.py` - Model endpoint definitions
- `requests/` - HTTP library for external APIs
- Dependencies: `urllib3`, `certifi`, `charset_normalizer`, `idna`

**Prompt Generator** (`craicgptie_prompt_generator`):
- `lambda_function_v2.py` - Educational prompt generation with explicit parameters
- `educational_runner.py` - Multi-provider API calls
- `model_configurations.py` - Model endpoint definitions
- `requests/` - HTTP library for external APIs
- Dependencies: `urllib3`, `certifi`, `charset_normalizer`, `idna`

**Orchestrator** (`craicgptie-orchestrator`):
- `lambda_function.py` - Workflow coordination and concurrency control
- No external dependencies (uses only AWS SDK)

### **4. Generate Content**
```bash
# Generate content for today using all providers
TODAY=$(date '+%Y-%m-%d')

# Step 1: Generate prompts
aws lambda invoke \
  --function-name craicgptie_prompt_generator \
  --payload '{"START_DATE":"'${TODAY}'","END_DATE":"'${TODAY}'"}' \
  --cli-binary-format raw-in-base64-out \
  /dev/null

# Step 2: Generate content (respects 10 Lambda limit)
aws lambda invoke \
  --function-name craicgptie-orchestrator \
  --payload '{"START_DATE":"'${TODAY}'","END_DATE":"'${TODAY}'"}' \
  --cli-binary-format raw-in-base64-out \
  /dev/null
```

## 🔧 Configuration

### **Environment Variables**
Configure these on the orchestrator Lambda function:

```bash
# Critical: 10 Lambda limit compliance
MAX_ACCOUNT_CONCURRENT=9  # Orchestrator (1) + Workers (9) = 10 total
CONCURRENCY_CHECK_ENABLED=true
CONCURRENCY_BACKOFF_DELAY=5.0

# Multi-provider secrets
OPENAI_SECRET_NAME=craicgpt/openai-api-key
ANTHROPIC_SECRET_NAME=craicgpt/anthropic-api-key
GOOGLE_SECRET_NAME=craicgpt/google-api-key

# Model configuration
BEDROCK_MODEL_IDS=anthropic.claude-3-sonnet-20240229-v1:0,amazon.titan-text-express-v1
OPENAI_MODEL_IDS=gpt-4,o3-mini
ANTHROPIC_MODEL_IDS=claude-3-5-sonnet-20241022,claude-3-opus-20240229
GEMINI_MODEL_IDS=gemini-pro,gemini-ultra
```

### **Frontend Model Selection**
The frontend now includes radio buttons for all supported providers:

**LLM Models:**
- AWS Bedrock: Claude Sonnet, Titan Express, Claude Haiku
- OpenAI: GPT-4, O3 Mini
- Anthropic Direct: Claude 3.5 Sonnet, Claude 3 Opus
- Google: Gemini Pro, Gemini Ultra

**Image Models:**
- AWS Bedrock: Titan Image, Nova Canvas
- OpenAI: DALL-E 3

## 📊 Monitoring & Operations

### **CloudWatch Monitoring**
```bash
# Monitor orchestrator logs
aws logs tail /aws/lambda/craicgptie-orchestrator --follow

# Check concurrency compliance
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie-orchestrator \
  --filter-pattern '"CRITICAL: 10 Lambda limit"'

# Monitor multi-provider usage
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie_llm_runner \
  --filter-pattern '"provider"'
```

### **Performance Metrics**
- **Concurrency Limit**: Hard-coded 10 Lambda maximum (orchestrator + 9 workers)
- **Success Rate**: Target >95% content generation success
- **Processing Time**: ~45 seconds per model/date combination
- **Cost Optimization**: Multi-provider cost comparison and selection

## 🔐 Security Features

### **API Key Management**
- ✅ **AWS Secrets Manager**: Secure storage for all external provider API keys
- ✅ **IAM Policies**: Least privilege access to secrets and AWS services
- ✅ **Key Rotation**: Automated rotation support for supported providers
- ✅ **Audit Trail**: CloudTrail logging of all secret access

### **Network Security**
- ✅ **HTTPS Only**: All external API calls use encrypted connections
- ✅ **Lambda Security**: Functions run in isolated execution environments
- ✅ **S3 Encryption**: Content stored with server-side encryption
- ✅ **CloudFront Security**: Headers and CORS configuration

## 🎯 Production Readiness

### **✅ Completed Features**
- Multi-provider AI integration (AWS Bedrock, OpenAI, Anthropic, Google)
- Unified prompt generation with explicit parameters
- 10 Lambda concurrency limit enforcement
- AWS Secrets Manager integration
- Comprehensive error handling and retry logic
- Frontend model selection interface
- Idempotent workflow execution
- Real-time monitoring and alerting

### **🚧 Future Enhancements**
- CI/CD pipeline with automated testing
- Advanced cost optimization algorithms
- Multi-region deployment support
- Performance analytics dashboard
- A/B testing for prompt variations

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

We welcome contributions! See individual component README files for specific development guidelines and contribution opportunities.

**Built for Production - Ready for Scale** 🚀