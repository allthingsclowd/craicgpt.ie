<p align="center">
  <img src="frontend/static_assets/images/CraicGPT_240h.png" alt="CraicGPT Logo" width="350"/>
  <img src="frontend/static_assets/images/GeekwiththePeak.png" alt="Geek with the Peak Logo" width="150"/>
</p>

# CraicGPT.ie - AI-Powered Digital Newspaper

**Learn AI in Code: From Basic LLM Calls to Advanced AI Agents**

A comprehensive educational project demonstrating practical AI integration, from simple API calls to sophisticated agent workflows. CraicGPT.ie generates a daily AI-powered newspaper while teaching developers how to work with Large Language Models (LLMs), image generation, and AI agent architectures.

## 📚 Project Vision & Learning Path

This repository serves as a **hands-on learning journey** through the evolving landscape of AI development:

### **Phase 1: Foundation - Basic LLM Integration** (Current)
- Direct API calls to LLM and image generation services
- Traditional embedded AI workflows
- RESTful API integration patterns
- Basic prompt engineering and response handling

### **Phase 2: Evolution - AI Agents** (Planned)
- Implementation of ReAct (Reasoning + Acting) agent patterns
- Tool-using AI with function calling
- Multi-step reasoning and decision making
- Agent-based content generation workflows

### **Phase 3: Future - Model Context Protocol (MCP)** (Planned) 
- MCP client and server implementations
- Standardized tool interfaces for AI agents
- Advanced inter-agent communication
- Production-ready agent architectures

---

## 🏗️ Architecture Overview

CraicGPT.ie is built as **two distinct applications** with different deployment strategies:

### **Frontend Application** ✅ **Production Ready**
- **Technology**: Static HTML/CSS/JavaScript newspaper layout
- **Hosting**: AWS S3 + CloudFront CDN with custom domain
- **Deployment**: Fully automated via Terraform (`terraform/frontend/`)
- **Features**: 
  - Model selection (LLM and Image Generation)
  - Date picker for historical content
  - Responsive newspaper layout
  - Real-time content updates

### **Backend Content Pipeline** ⚠️ **Manual Deployment** 
- **Technology**: 4 AWS Lambda functions in Python
- **Current State**: Manual deployment (Terraform boilerplate exists but unvalidated)
- **Architecture**: Event-driven serverless pipeline

---

## 🔧 Backend Lambda Architecture

The content generation pipeline consists of four specialized Lambda functions:

### **1. Prompt Generator** (`lambda_code/PromptGenerator/`)
- **Purpose**: Daily prompt generation for all content types
- **Trigger**: AWS EventBridge Scheduler (daily)
- **Output**: 13 prompts stored in S3
  - 5 LLM prompts (`llm_01` - `llm_05`)
  - 8 Image prompts (`img_01` - `img_08`)

### **2. Orchestrator** (`lambda_code/orchestrator/`)
- **Purpose**: Workflow coordination and dependency management
- **Trigger**: AWS EventBridge Scheduler (daily, after prompt generation)
- **Function**: 
  - Reads date range from environment variables
  - Invokes LLM and Image handlers sequentially
  - Manages model-specific rate limiting
  - Handles failures and retries with exponential backoff
  - **Concurrency Control**: Real-time monitoring of account-wide Lambda executions
  - **Resource Management**: Smart backoff when approaching AWS platform limits

### **3. LLM Handler** (`lambda_code/llmHandler/`)
- **Purpose**: Text content generation using various LLM providers
- **Models Supported**:
  - Anthropic Claude (Sonnet, Haiku)
  - Amazon Titan Text
  - Support for Cohere, AI21 (extensible)
- **Content Types**: Main articles, comparisons, stories, jokes, author bios

### **4. Image Generation Handler** (`lambda_code/imageGenHandler/`)
- **Purpose**: Visual content generation
- **Models Supported**:
  - Amazon Titan Image Generator
  - Amazon Nova Canvas
- **Content Types**: Article illustrations, advertisements, feature images

---

## ⚙️ Concurrency Management

The orchestrator includes sophisticated concurrency control to handle AWS Lambda platform limits and prevent throttling:

### **Configuration Options**

Set these environment variables on the orchestrator Lambda function:

```bash
# Account-wide concurrency limit (default: 9, max AWS allows: 1000)
MAX_ACCOUNT_CONCURRENT=9

# Enable/disable concurrency checking (default: true)
CONCURRENCY_CHECK_ENABLED=true

# Wait time when at concurrency limit (default: 30 seconds)
CONCURRENCY_BACKOFF_DELAY=30

# CloudWatch API region (default: eu-west-1)
CLOUDWATCH_REGION=eu-west-1
```

### **How It Works**

1. **Real-time Monitoring**: Uses CloudWatch metrics to check current Lambda executions across your entire AWS account
2. **Smart Throttling**: Waits when approaching the configured limit before invoking new workers
3. **Progressive Backoff**: Exponential delays between worker invocations (8+ seconds)
4. **Timeout Protection**: Maximum 3-minute wait per worker to prevent infinite loops
5. **Graceful Degradation**: Continues processing even if concurrency monitoring fails

### **Recommended Settings**

- **Development**: `MAX_ACCOUNT_CONCURRENT=5` (safe testing)
- **Production**: `MAX_ACCOUNT_CONCURRENT=9` (AWS free tier limit is 10)
- **Enterprise**: `MAX_ACCOUNT_CONCURRENT=50` (adjust based on account limits)

### **Monitoring Concurrency**

Check current Lambda executions across your account:

```bash
# View real-time concurrency metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name ConcurrentExecutions \
  --dimensions Name=FunctionName,Value=craicgptie-orchestrator \
  --start-time $(date -v-10M -u '+%Y-%m-%dT%H:%M:%S') \
  --end-time $(date -u '+%Y-%m-%dT%H:%M:%S') \
  --period 60 \
  --statistics Maximum

# Monitor account-wide concurrency
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name ConcurrentExecutions \
  --start-time $(date -v-10M -u '+%Y-%m-%dT%H:%M:%S') \
  --end-time $(date -u '+%Y-%m-%dT%H:%M:%S') \
  --period 60 \
  --statistics Maximum
```

---

## 🚀 Current Status & Next Steps

### **✅ What's Working**
- Frontend website with full Terraform automation
- All 4 Lambda functions operational with manual deployment
- Daily content generation pipeline
- Multi-model support (LLM and Image)
- Rate limiting and error handling
- Rich logging and monitoring
- **Account-wide concurrency control** with real-time AWS monitoring

### **🚧 Immediate Priorities**

1. **Backend Infrastructure Automation**
   - Validate and complete Terraform modules in `terraform/backend/`
   - IAM roles and policies for Lambda functions
   - EventBridge scheduler configuration
   - S3 bucket permissions and lifecycle policies

2. **CI/CD Pipeline Implementation**
   - GitHub Actions for security scanning
   - Automated testing and validation workflows
   - Multi-environment deployment (dev → prod)
   - Terraform best practices (remote state, locking)

3. **Production Hardening**
   - Comprehensive error handling and monitoring
   - Performance optimization and cost management
   - Security scanning and compliance
   - Documentation and runbooks

---

## 📁 Repository Structure

```
craicgpt.ie/
├── frontend/                    # Static website (Terraform ✅)
│   ├── index.html              # Main newspaper layout
│   ├── static_assets/          # CSS, JS, images
│   └── README.md               # Frontend documentation
├── lambda_code/                # Backend functions (Manual ⚠️)
│   ├── PromptGenerator/        # Daily prompt generation
│   ├── orchestrator/           # Workflow coordination
│   ├── llmHandler/             # LLM content generation  
│   └── imageGenHandler/        # Image generation
├── terraform/                  # Infrastructure as Code
│   ├── frontend/               # Website deployment (Working ✅)
│   └── backend/                # Lambda infrastructure (Boilerplate ⚠️)
├── prompts/                    # Base prompt templates
├── test_*.py                   # Test utilities and validation
└── README.md                   # This file
```

---

## 🛠️ Prerequisites & Setup

### **Required Tools**
- **Terraform** >= 1.8.0
- **AWS CLI** with configured credentials
- **Python** 3.11+ (for Lambda functions)
- **Node.js** (for frontend tooling, optional)

### **AWS Requirements**
- AWS account with appropriate IAM permissions
- Domain name registered (for custom domain)
- Route 53 hosted zone (for DNS management)

### **Quick Start - Frontend Deployment**

1. **Configure Variables**
   ```bash
   cd terraform/frontend
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with your domain and settings
   ```

2. **Deploy Infrastructure**
   ```bash
   terraform init
   terraform plan
   terraform apply
   ```

3. **Upload Frontend Assets**
   ```bash
   # Assets are automatically uploaded during Terraform deployment
   ```

### **Manual Backend Deployment**
Currently requires manual Lambda function deployment through AWS Console or CLI. See individual function READMEs for deployment instructions.

### **Manual Content Generation**

Content generation is a **two-step process**: first generate prompts, then generate content. Here's how to trigger one-off generation for specific date ranges using the AWS CLI:

#### **Complete Two-Step Process (Scheduled)**

```bash
# Set your date range
START_DATE="2025-01-01" 
END_DATE="2025-01-05"

# Step 1: Schedule prompt generation (5 minutes from now)
PROMPT_EXECUTION_TIME=$(date -u -d '+5 minutes' '+%Y-%m-%dT%H:%M:%S')

aws scheduler create-schedule \
  --name "craicgpt-prompts-$(date +%s)" \
  --schedule-expression "at(${PROMPT_EXECUTION_TIME})" \
  --target '{
    "Arn": "arn:aws:lambda:YOUR_REGION:YOUR_ACCOUNT:function:craicgptie_prompt_generator",
    "RoleArn": "arn:aws:iam::YOUR_ACCOUNT:role/EventBridgeSchedulerRole",
    "Input": "{\"START_DATE\":\"'${START_DATE}'\",\"END_DATE\":\"'${END_DATE}'\"}"
  }' \
  --flexible-time-window State=OFF \
  --description "Generate prompts for CraicGPT content ${START_DATE} to ${END_DATE}"

echo "✅ Scheduled prompt generation for ${PROMPT_EXECUTION_TIME} UTC"

# Step 2: Schedule orchestrator (10 minutes from now - allows time for prompts)
ORCHESTRATOR_EXECUTION_TIME=$(date -u -d '+10 minutes' '+%Y-%m-%dT%H:%M:%S')

aws scheduler create-schedule \
  --name "craicgpt-orchestrator-$(date +%s)" \
  --schedule-expression "at(${ORCHESTRATOR_EXECUTION_TIME})" \
  --target '{
    "Arn": "arn:aws:lambda:YOUR_REGION:YOUR_ACCOUNT:function:craicgptie-orchestrator",
    "RoleArn": "arn:aws:iam::YOUR_ACCOUNT:role/EventBridgeSchedulerRole",
    "Input": "{\"START_DATE\":\"'${START_DATE}'\",\"END_DATE\":\"'${END_DATE}'\"}"
  }' \
  --flexible-time-window State=OFF \
  --description "Orchestrate CraicGPT content generation for ${START_DATE} to ${END_DATE}"

echo "✅ Scheduled orchestrator execution for ${ORCHESTRATOR_EXECUTION_TIME} UTC"
echo "📅 Date range: ${START_DATE} to ${END_DATE}"
echo "⏱️  Monitor progress in CloudWatch logs:"
echo "   📝 Prompt generation: craicgptie_prompt_generator"
echo "   🎭 Content orchestration: craicgptie-orchestrator"
```

#### **Alternative: Direct Invocation (Immediate)**

For immediate execution, run both steps sequentially:

```bash
# Step 1: Generate prompts first
echo "🚀 Step 1: Generating prompts..."
aws lambda invoke \
  --function-name craicgptie_prompt_generator \
  --payload '{
    "START_DATE": "2025-01-01",
    "END_DATE": "2025-01-05"
  }' \
  --cli-binary-format raw-in-base64-out \
  prompt_response.json

echo "✅ Prompt generation completed. Response:"
cat prompt_response.json | jq '.'

# Wait a moment for S3 consistency
echo "⏳ Waiting 30 seconds for S3 consistency..."
sleep 30

# Step 2: Run orchestrator
echo "🚀 Step 2: Running orchestrator..."
aws lambda invoke \
  --function-name craicgptie-orchestrator \
  --payload '{
    "START_DATE": "2025-01-01",
    "END_DATE": "2025-01-05"
  }' \
  --cli-binary-format raw-in-base64-out \
  orchestrator_response.json

echo "✅ Orchestration completed. Response:"
cat orchestrator_response.json | jq '.'
```

#### **Prerequisites for Manual Execution**
- **Lambda functions deployed**: `craicgptie_prompt_generator`, `craicgptie-orchestrator`, `craicgptie_llm_runner`, `craicgptie_image_runner`
- **EventBridge Scheduler execution role** with Lambda invoke permissions  
- **AWS CLI configured** with appropriate permissions
- **S3 bucket** accessible for prompt and content storage

#### **Understanding the Process**
1. **Prompt Generator** creates 13 prompts per date (5 LLM + 8 Image) and stores them in S3
2. **Orchestrator** reads those prompts and coordinates LLM/Image worker invocations  
3. **Workers** generate content and store results back to S3 as JSON files
4. **Frontend** fetches the JSON files to display the generated newspaper

### **🎯 Ready-to-Use Commands (Copy & Paste)**

These examples use your specific Lambda function ARNs and are ready to copy-paste:

#### **Option A: Scheduled Execution (Recommended)**

Generate content for the next 5 days starting tomorrow:

```bash
# Set date range (modify as needed)
START_DATE=$(date -v+1d '+%Y-%m-%d')
END_DATE=$(date -v+5d '+%Y-%m-%d')

# Configure concurrency control (adjust based on your AWS account limits)
CONCURRENCY_LIMIT=9  # Safe for AWS free tier (limit of 10)

# Step 1: Update orchestrator environment variables for concurrency control
echo "⚙️ Configuring orchestrator concurrency settings..."
aws lambda update-function-configuration \
  --function-name arn:aws:lambda:eu-west-1:217369101910:function:craicgptie-orchestrator \
  --environment Variables="{
    \"MAX_ACCOUNT_CONCURRENT\":\"${CONCURRENCY_LIMIT}\",
    \"CONCURRENCY_CHECK_ENABLED\":\"true\",
    \"CONCURRENCY_BACKOFF_DELAY\":\"30\",
    \"CLOUDWATCH_REGION\":\"eu-west-1\"
  }" \
  --output table

echo "✅ Concurrency control configured (limit: ${CONCURRENCY_LIMIT})"

# Step 2: Schedule prompt generation (5 minutes from now)
PROMPT_EXECUTION_TIME=$(date -u -v+5M '+%Y-%m-%dT%H:%M:%S')

aws scheduler create-schedule \
  --name "craicgpt-prompts-$(date +%s)" \
  --schedule-expression "at(${PROMPT_EXECUTION_TIME})" \
  --target '{
    "Arn": "arn:aws:lambda:eu-west-1:217369101910:function:craicgptie_prompt_generator",
    "RoleArn": "arn:aws:iam::217369101910:role/EventBridgeSchedulerRole",
    "Input": "{\"START_DATE\":\"'${START_DATE}'\",\"END_DATE\":\"'${END_DATE}'\"}"
  }' \
  --flexible-time-window State=OFF \
  --description "Generate prompts for CraicGPT content ${START_DATE} to ${END_DATE}"

echo "✅ Scheduled prompt generation for ${PROMPT_EXECUTION_TIME} UTC"

# Step 3: Schedule orchestrator (10 minutes from now)
ORCHESTRATOR_EXECUTION_TIME=$(date -u -v+10M '+%Y-%m-%dT%H:%M:%S')

aws scheduler create-schedule \
  --name "craicgpt-orchestrator-$(date +%s)" \
  --schedule-expression "at(${ORCHESTRATOR_EXECUTION_TIME})" \
  --target '{
    "Arn": "arn:aws:lambda:eu-west-1:217369101910:function:craicgptie-orchestrator", 
    "RoleArn": "arn:aws:iam::217369101910:role/EventBridgeSchedulerRole",
    "Input": "{\"START_DATE\":\"'${START_DATE}'\",\"END_DATE\":\"'${END_DATE}'\"}"
  }' \
  --flexible-time-window State=OFF \
  --description "Orchestrate CraicGPT content generation for ${START_DATE} to ${END_DATE}"

echo "✅ Scheduled orchestrator execution for ${ORCHESTRATOR_EXECUTION_TIME} UTC"
echo "📅 Date range: ${START_DATE} to ${END_DATE}"
echo "🔧 Concurrency limit: ${CONCURRENCY_LIMIT} simultaneous Lambda executions"
echo ""
echo "🔍 Monitor progress in CloudWatch logs:"
echo "   📝 Prompt generation: /aws/lambda/craicgptie_prompt_generator"
echo "   🎭 Content orchestration: /aws/lambda/craicgptie-orchestrator"
echo "   💬 LLM processing: /aws/lambda/craicgptie_llm_runner"
echo "   🖼️  Image generation: /aws/lambda/craicgptie_image_runner"
```

#### **Option B: Immediate Execution (Quick Test)**

Generate content for today only:

```bash
# Generate content for today
TODAY=$(date '+%Y-%m-%d')

echo "🚀 Generating CraicGPT content for ${TODAY}..."

# Configure concurrency control for testing
echo "⚙️ Configuring orchestrator for immediate execution..."
aws lambda update-function-configuration \
  --function-name arn:aws:lambda:eu-west-1:217369101910:function:craicgptie-orchestrator \
  --environment Variables="{
    \"MAX_ACCOUNT_CONCURRENT\":\"5\",
    \"CONCURRENCY_CHECK_ENABLED\":\"true\",
    \"CONCURRENCY_BACKOFF_DELAY\":\"20\",
    \"CLOUDWATCH_REGION\":\"eu-west-1\"
  }" \
  --output table

echo "✅ Concurrency control configured (testing mode: limit 5)"

# Step 1: Generate prompts
echo "📝 Step 1: Generating prompts..."
aws lambda invoke \
  --function-name arn:aws:lambda:eu-west-1:217369101910:function:craicgptie_prompt_generator \
  --payload '{
    "START_DATE": "'${TODAY}'",
    "END_DATE": "'${TODAY}'"
  }' \
  --cli-binary-format raw-in-base64-out \
  prompt_response.json

echo "✅ Prompt generation completed"

# Wait for S3 consistency
echo "⏳ Waiting 30 seconds for S3 consistency..."
sleep 30

# Step 2: Run orchestrator
echo "🎭 Step 2: Running orchestrator..."
aws lambda invoke \
  --function-name arn:aws:lambda:eu-west-1:217369101910:function:craicgptie-orchestrator \
  --payload '{
    "START_DATE": "'${TODAY}'",
    "END_DATE": "'${TODAY}'"
  }' \
  --cli-binary-format raw-in-base64-out \
  orchestrator_response.json

echo "✅ Content generation completed for ${TODAY}"
echo ""
echo "📁 Generated files:"
echo "   📝 prompt_response.json"
echo "   📄 orchestrator_response.json"
echo ""
echo "🌐 Check your website: https://craicgpt.ie/?date=${TODAY}"
echo "🔧 Used concurrency limit: 5 (testing mode)"

# Cleanup response files
rm -f prompt_response.json orchestrator_response.json
```

#### **Option C: Specific Date Range**

Generate content for a custom date range:

```bash
# ⚠️  MODIFY THESE DATES BEFORE RUNNING
START_DATE="2025-01-15"
END_DATE="2025-01-20"

# Calculate number of days to optimize concurrency
DAYS_COUNT=$(( ( $(date -j -f "%Y-%m-%d" "${END_DATE}" "+%s") - $(date -j -f "%Y-%m-%d" "${START_DATE}" "+%s") ) / 86400 + 1 ))
CONCURRENCY_LIMIT=$(( DAYS_COUNT > 5 ? 9 : 7 ))  # Higher limit for longer date ranges

echo "🚀 Generating CraicGPT content from ${START_DATE} to ${END_DATE} (${DAYS_COUNT} days)..."

# Configure concurrency control based on workload
echo "⚙️ Configuring orchestrator for ${DAYS_COUNT}-day generation..."
aws lambda update-function-configuration \
  --function-name arn:aws:lambda:eu-west-1:217369101910:function:craicgptie-orchestrator \
  --environment Variables="{
    \"MAX_ACCOUNT_CONCURRENT\":\"${CONCURRENCY_LIMIT}\",
    \"CONCURRENCY_CHECK_ENABLED\":\"true\",
    \"CONCURRENCY_BACKOFF_DELAY\":\"30\",
    \"CLOUDWATCH_REGION\":\"eu-west-1\"
  }" \
  --output table

echo "✅ Concurrency control configured (limit: ${CONCURRENCY_LIMIT} for ${DAYS_COUNT} days)"

# Step 1: Generate prompts
aws lambda invoke \
  --function-name arn:aws:lambda:eu-west-1:217369101910:function:craicgptie_prompt_generator \
  --payload '{
    "START_DATE": "'${START_DATE}'",
    "END_DATE": "'${END_DATE}'"
  }' \
  --cli-binary-format raw-in-base64-out \
  /dev/null

echo "✅ Prompts generated for ${START_DATE} to ${END_DATE}"

# Wait for S3 consistency
echo "⏳ Waiting 30 seconds for S3 consistency..."
sleep 30

# Step 2: Run orchestrator
aws lambda invoke \
  --function-name arn:aws:lambda:eu-west-1:217369101910:function:craicgptie-orchestrator \
  --payload '{
    "START_DATE": "'${START_DATE}'",
    "END_DATE": "'${END_DATE}'"
  }' \
  --cli-binary-format raw-in-base64-out \
  /dev/null

echo "✅ Content generation completed!"
echo "🔧 Used concurrency limit: ${CONCURRENCY_LIMIT} for ${DAYS_COUNT} days"
echo ""
echo "🌐 View generated content:"
CURRENT_DATE="${START_DATE}"
while [[ "${CURRENT_DATE}" <= "${END_DATE}" ]]; do
    echo "   📅 ${CURRENT_DATE}: https://craicgpt.ie/?date=${CURRENT_DATE}"
    CURRENT_DATE=$(date -j -v+1d -f '%Y-%m-%d' "${CURRENT_DATE}" '+%Y-%m-%d')
done
```

#### **📊 Monitoring & Troubleshooting**

After running any of the above commands, monitor progress with:

```bash
# Real-time log monitoring
aws logs tail /aws/lambda/craicgptie_prompt_generator --follow
aws logs tail /aws/lambda/craicgptie-orchestrator --follow

# Check recent executions
aws logs describe-log-streams \
  --log-group-name /aws/lambda/craicgptie-orchestrator \
  --order-by LastEventTime \
  --descending \
  --max-items 5

# Check for errors in the last hour
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie-orchestrator \
  --start-time $(date -v-1H +%s)000 \
  --filter-pattern 'ERROR'

# Monitor concurrency and throttling
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie-orchestrator \
  --start-time $(date -v-30M +%s)000 \
  --filter-pattern '"🔧 Account concurrency" OR "🚦 Waiting for concurrency" OR "⚠️ High concurrency"'

# Check current account-wide Lambda concurrency
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name ConcurrentExecutions \
  --start-time $(date -v-5M -u '+%Y-%m-%dT%H:%M:%S') \
  --end-time $(date -u '+%Y-%m-%dT%H:%M:%S') \
  --period 60 \
  --statistics Maximum

# View orchestrator environment variables (verify concurrency config)
aws lambda get-function-configuration \
  --function-name arn:aws:lambda:eu-west-1:217369101910:function:craicgptie-orchestrator \
  --query 'Environment.Variables' \
  --output table
```

**Common Issues & Solutions:**

- **🚦 "Waiting for concurrency to drop"**: Normal - orchestrator is managing AWS limits
- **⚠️ "High concurrency detected"**: Reduce `MAX_ACCOUNT_CONCURRENT` if you have other Lambda functions running
- **❌ "TooManyRequestsException"**: AWS throttling - increase `CONCURRENCY_BACKOFF_DELAY` or reduce concurrent limit
- **🔄 "Retrying worker invocation"**: Normal retry behavior - check worker logs for specific errors

---

## 🎯 Learning Objectives

### **Phase 1: LLM Integration Fundamentals**
- **API Integration**: REST calls to various LLM providers
- **Prompt Engineering**: Crafting effective prompts for different content types
- **Response Handling**: Parsing and processing LLM outputs
- **Error Resilience**: Timeout handling, retries, and fallbacks
- **Rate Limiting**: Managing API quotas and costs
- **Multi-Model Support**: Abstracting provider differences

### **Phase 2: AI Agent Development** (Coming Soon)
- **ReAct Pattern**: Reasoning and Acting in iterative loops
- **Tool Integration**: Function calling and external API usage
- **Decision Making**: Multi-step reasoning and planning
- **Memory Management**: Maintaining context across interactions
- **Agent Orchestration**: Coordinating multiple specialized agents

### **Phase 3: MCP Implementation** (Future)
- **Protocol Implementation**: MCP client and server development
- **Tool Standardization**: Universal tool interfaces
- **Agent Communication**: Inter-agent messaging and coordination
- **Production Deployment**: Scalable agent architectures

---

## 🤝 Contributing

We welcome contributions at all levels! Whether you're learning AI development or an experienced practitioner, there are opportunities to help:

### **Beginner-Friendly**
- Documentation improvements
- Frontend enhancements
- Test case development
- Bug reports and feature requests

### **Intermediate**
- Backend Terraform completion
- CI/CD pipeline implementation
- Performance optimizations
- Additional LLM provider integrations

### **Advanced**
- Agent architecture design (Phase 2)
- MCP implementation (Phase 3)
- Advanced monitoring and observability
- Security and compliance enhancements

---

## 📖 Educational Resources

### **Key Concepts Demonstrated**
- **Serverless Architecture**: AWS Lambda event-driven design
- **Infrastructure as Code**: Terraform best practices
- **API Design**: RESTful patterns and error handling
- **Content Generation**: Practical LLM and image model usage
- **Workflow Orchestration**: Dependency management and scheduling

### **Technologies Showcased**
- **AWS Services**: Lambda, S3, CloudFront, EventBridge, IAM
- **AI/ML Services**: Amazon Bedrock, Anthropic Claude, Titan models
- **Infrastructure**: Terraform, GitHub Actions (planned)
- **Frontend**: Modern JavaScript, CSS Grid, responsive design

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙋‍♂️ Support & Community

- **Issues**: Report bugs and request features via GitHub Issues
- **Discussions**: Join conversations about AI development patterns
- **Documentation**: Comprehensive guides for each phase of development

**Learn AI in Code - Start Your Journey Today!** 🚀
