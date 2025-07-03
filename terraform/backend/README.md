# Backend Infrastructure - Development Configuration 🚧

**Lambda Functions, EventBridge, S3, and Secrets Management**

This directory contains Terraform configurations for deploying the CraicGPT.ie backend infrastructure. The configuration includes all Lambda functions, EventBridge schedulers, S3 storage, and Secrets Manager integration for the multi-provider AI newspaper generation system.

**⚠️ IMPORTANT**: This configuration is in development status and requires careful validation before production deployment.

## 🏗️ Architecture Overview

### **Backend Infrastructure Components** 🚧
```
Backend Development Infrastructure
├── Lambda Functions (4 functions)
│   ├── craicgptie_prompt_generator     # Prompt engineering
│   ├── craicgptie-orchestrator         # Workflow coordination  
│   ├── craicgptie_llm_runner          # Text generation
│   └── craicgptie_image_runner        # Image generation
├── EventBridge Schedulers
│   ├── Daily prompt generation trigger
│   ├── Orchestrated content generation
│   └── Automated workflow scheduling
├── S3 Bucket for Content Storage
│   ├── Prompts storage (/prompts/YYYY/MM/DD/)
│   ├── Generated content (/website/YYYY/MM/DD/)
│   └── Static assets and configurations
├── IAM Roles & Policies
│   ├── Lambda execution roles
│   ├── S3 access policies
│   ├── Secrets Manager permissions
│   └── EventBridge invocation rights
└── Secrets Manager Integration
    ├── OpenAI API keys
    ├── Anthropic API keys
    └── Google Gemini API keys
```

### **10 Lambda Concurrency Limit Compliance**
- **Critical Requirement**: Total Lambda concurrency ≤ 10
- **Architecture**: Orchestrator (1) + Workers (max 9) = 10 total
- **Enforcement**: Built-in concurrency monitoring and throttling
- **Validation**: Real-time CloudWatch metrics tracking

## 🚀 Deployment Setup

### **Prerequisites**
```bash
# Terraform installation
terraform version  # Should be >= 1.8.0

# AWS CLI configuration
aws configure
# Ensure account has appropriate Lambda and IAM permissions

# Validate AWS account limits
aws service-quotas get-service-quota \
  --service-code lambda \
  --quota-code L-B99A9384  # Concurrent executions quota
```

### **Configuration Requirements**
```bash
cd terraform/backend

# Copy example configuration
cp terraform.tfvars.example terraform.tfvars

# Edit with your specific settings
nano terraform.tfvars
```

### **Required Configuration Variables**
```hcl
# Environment Configuration
environment = "development"  # or "production"
project_name = "craicgpt"
aws_region = "eu-west-1"

# Lambda Configuration
lambda_memory_size = 1024
lambda_timeout = 300
lambda_image_memory_size = 2048
lambda_image_timeout = 900

# CRITICAL: 10 Lambda limit compliance
max_account_concurrent = 9  # Orchestrator + 9 workers = 10 total
concurrency_check_enabled = true

# S3 Configuration
content_bucket_name = "craicgpt-content-dev"
enable_s3_versioning = true

# Secrets Configuration
openai_secret_name = "craicgpt/openai-api-key"
anthropic_secret_name = "craicgpt/anthropic-api-key" 
google_secret_name = "craicgpt/google-api-key"

# EventBridge Configuration
enable_scheduled_triggers = true
daily_schedule_expression = "cron(0 6 * * ? *)"  # 6 AM UTC daily
```

### **Deployment Process** ⚠️
```bash
# Initialize Terraform
terraform init

# CRITICAL: Review planned changes carefully
terraform plan -out=backend.plan

# IMPORTANT: Validate Lambda concurrency limits
grep -r "concurrent" *.tf modules/*/

# Deploy with caution (development environment recommended)
terraform apply backend.plan

# Post-deployment validation
./scripts/validate-backend-deployment.sh
```

## 📁 Lambda Functions Configuration

### **Prompt Generator Function**
**Purpose**: Generate optimized prompts for all AI providers

```hcl
resource "aws_lambda_function" "prompt_generator" {
  function_name = "craicgptie_prompt_generator"
  runtime      = "python3.12"
  handler      = "lambda_function.lambda_handler"
  memory_size  = 512
  timeout      = 300
  
  environment {
    variables = {
      PROMPT_BUCKET = var.content_bucket_name
      OPENAI_SECRET_NAME = var.openai_secret_name
      ANTHROPIC_SECRET_NAME = var.anthropic_secret_name
      GOOGLE_SECRET_NAME = var.google_secret_name
    }
  }
}
```

### **Orchestrator Function**
**Purpose**: Coordinate workflow with strict concurrency control

```hcl
resource "aws_lambda_function" "orchestrator" {
  function_name = "craicgptie-orchestrator"
  runtime      = "python3.12"
  handler      = "lambda_function.lambda_handler"
  memory_size  = 1024
  timeout      = 900  # 15 minutes
  
  # CRITICAL: Reserve concurrency to ensure orchestrator availability
  reserved_concurrent_executions = 1
  
  environment {
    variables = {
      MAX_ACCOUNT_CONCURRENT = var.max_account_concurrent
      CONCURRENCY_CHECK_ENABLED = var.concurrency_check_enabled
      LLM_WORKER_FUNCTION = aws_lambda_function.llm_runner.function_name
      IMAGE_WORKER_FUNCTION = aws_lambda_function.image_runner.function_name
      PROMPT_BUCKET = var.content_bucket_name
    }
  }
}
```

### **LLM Runner Function**
**Purpose**: Multi-provider text generation

```hcl
resource "aws_lambda_function" "llm_runner" {
  function_name = "craicgptie_llm_runner"
  runtime      = "python3.12"
  handler      = "lambda_function.lambda_handler"
  memory_size  = var.lambda_memory_size
  timeout      = var.lambda_timeout
  
  environment {
    variables = {
      PROMPT_BUCKET = var.content_bucket_name
      OPENAI_SECRET_NAME = var.openai_secret_name
      ANTHROPIC_SECRET_NAME = var.anthropic_secret_name
      GOOGLE_SECRET_NAME = var.google_secret_name
    }
  }
}
```

### **Image Runner Function**
**Purpose**: Multi-provider image generation

```hcl
resource "aws_lambda_function" "image_runner" {
  function_name = "craicgptie_image_runner"
  runtime      = "python3.12"
  handler      = "lambda_function.lambda_handler"
  memory_size  = var.lambda_image_memory_size
  timeout      = var.lambda_image_timeout
  
  environment {
    variables = {
      PROMPT_BUCKET = var.content_bucket_name
      OPENAI_SECRET_NAME = var.openai_secret_name
    }
  }
}
```

## 🔐 IAM Configuration

### **Lambda Execution Role**
```hcl
resource "aws_iam_role" "lambda_execution_role" {
  name = "${var.project_name}-lambda-execution-${var.environment}"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
  
  tags = {
    Environment = var.environment
    Project     = var.project_name
    Component   = "backend-infrastructure"
  }
}
```

### **Required IAM Policies**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::craicgpt-content-dev/*"
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
    },
    {
      "Effect": "Allow",
      "Action": [
        "lambda:InvokeFunction"
      ],
      "Resource": [
        "arn:aws:lambda:*:*:function:craicgptie_*",
        "arn:aws:lambda:*:*:function:craicgptie-*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "cloudwatch:GetMetricStatistics"
      ],
      "Resource": "*"
    }
  ]
}
```

## 📊 EventBridge Scheduling

### **Daily Prompt Generation**
```hcl
resource "aws_cloudwatch_event_rule" "daily_prompt_generation" {
  name                = "${var.project_name}-daily-prompts-${var.environment}"
  description         = "Trigger daily prompt generation"
  schedule_expression = var.daily_schedule_expression
  
  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_cloudwatch_event_target" "prompt_generator_target" {
  rule      = aws_cloudwatch_event_rule.daily_prompt_generation.name
  target_id = "PromptGeneratorTarget"
  arn       = aws_lambda_function.prompt_generator.arn
  
  input = jsonencode({
    START_DATE = "$${strftime('%Y-%m-%d', timestamp())}"
    END_DATE   = "$${strftime('%Y-%m-%d', timestamp())}"
  })
}
```

### **Orchestrated Content Generation**
```hcl
resource "aws_cloudwatch_event_rule" "content_orchestration" {
  name                = "${var.project_name}-orchestration-${var.environment}"
  description         = "Trigger content generation orchestration"
  schedule_expression = "cron(30 6 * * ? *)"  # 30 minutes after prompt generation
  
  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}
```

## 🔧 S3 Configuration

### **Content Bucket Setup**
```hcl
resource "aws_s3_bucket" "content_bucket" {
  bucket = var.content_bucket_name
  
  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "content-storage"
  }
}

resource "aws_s3_bucket_versioning" "content_bucket" {
  bucket = aws_s3_bucket.content_bucket.id
  versioning_configuration {
    status = var.enable_s3_versioning ? "Enabled" : "Disabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "content_bucket" {
  bucket = aws_s3_bucket.content_bucket.id
  
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
```

### **S3 Directory Structure**
```
s3://craicgpt-content-dev/
├── static_assets/
│   ├── content/
│   │   ├── prompts/YYYY/MM/DD/*.json     # Generated prompts
│   │   └── website/YYYY/MM/DD/           # Generated content
│   └── configurations/
│       └── model_configs.json
└── logs/
    ├── lambda_execution/
    └── error_reports/
```

## 🔒 Secrets Management

### **API Key Storage**
```hcl
resource "aws_secretsmanager_secret" "openai_api_key" {
  name = var.openai_secret_name
  description = "OpenAI API key for CraicGPT content generation"
  
  tags = {
    Environment = var.environment
    Project     = var.project_name
    Provider    = "openai"
  }
}

resource "aws_secretsmanager_secret" "anthropic_api_key" {
  name = var.anthropic_secret_name
  description = "Anthropic API key for CraicGPT content generation"
  
  tags = {
    Environment = var.environment
    Project     = var.project_name
    Provider    = "anthropic"
  }
}

resource "aws_secretsmanager_secret" "google_api_key" {
  name = var.google_secret_name
  description = "Google Gemini API key for CraicGPT content generation"
  
  tags = {
    Environment = var.environment
    Project     = var.project_name
    Provider    = "google"
  }
}
```

### **Secret Value Management**
```bash
# Set API keys securely (manual step after deployment)
aws secretsmanager put-secret-value \
  --secret-id craicgpt/openai-api-key \
  --secret-string "your-openai-api-key"

aws secretsmanager put-secret-value \
  --secret-id craicgpt/anthropic-api-key \
  --secret-string "your-anthropic-api-key"

aws secretsmanager put-secret-value \
  --secret-id craicgpt/google-api-key \
  --secret-string "your-google-api-key"
```

## 📈 Monitoring & Logging

### **CloudWatch Configuration**
```hcl
resource "aws_cloudwatch_log_group" "lambda_logs" {
  for_each = toset([
    "/aws/lambda/craicgptie_prompt_generator",
    "/aws/lambda/craicgptie-orchestrator", 
    "/aws/lambda/craicgptie_llm_runner",
    "/aws/lambda/craicgptie_image_runner"
  ])
  
  name              = each.value
  retention_in_days = var.log_retention_days
  
  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}
```

### **Custom Metrics**
```hcl
# Lambda concurrency monitoring
resource "aws_cloudwatch_metric_alarm" "lambda_concurrency" {
  alarm_name          = "${var.project_name}-lambda-concurrency-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "ConcurrentExecutions"
  namespace           = "AWS/Lambda"
  period              = "60"
  statistic           = "Maximum"
  threshold           = "8"  # Alert before hitting 10 limit
  alarm_description   = "Lambda concurrency approaching account limit"
  
  alarm_actions = [aws_sns_topic.alerts.arn]
}
```

## 🧪 Testing & Validation

### **Deployment Validation Scripts**
```bash
#!/bin/bash
# validate-backend-deployment.sh

echo "🔍 Validating backend infrastructure deployment..."

# Check Lambda functions
echo "Checking Lambda functions..."
aws lambda list-functions --query 'Functions[?starts_with(FunctionName, `craicgptie`)].FunctionName'

# Verify S3 bucket
echo "Verifying S3 bucket..."
aws s3 ls s3://craicgpt-content-dev/

# Test secrets access
echo "Testing secrets access..."
aws secretsmanager describe-secret --secret-id craicgpt/openai-api-key

# Check EventBridge rules
echo "Checking EventBridge rules..."
aws events list-rules --name-prefix craicgpt

# Validate IAM permissions
echo "Validating IAM roles..."
aws iam get-role --role-name craicgpt-lambda-execution-development

echo "✅ Backend infrastructure validation complete!"
```

### **Manual Testing**
```bash
# Test prompt generation
aws lambda invoke \
  --function-name craicgptie_prompt_generator \
  --payload '{"START_DATE":"2025-01-15","END_DATE":"2025-01-15"}' \
  --cli-binary-format raw-in-base64-out \
  test-prompts.json

# Test orchestration
aws lambda invoke \
  --function-name craicgptie-orchestrator \
  --payload '{"START_DATE":"2025-01-15","END_DATE":"2025-01-15"}' \
  --cli-binary-format raw-in-base64-out \
  test-orchestration.json

# Monitor execution
aws logs tail /aws/lambda/craicgptie-orchestrator --follow
```

## 🐛 Troubleshooting

### **Common Issues**

**Lambda Concurrency Limits**
```bash
# Check current concurrency usage
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name ConcurrentExecutions \
  --statistics Maximum \
  --start-time $(date -v-1H -u '+%Y-%m-%dT%H:%M:%S') \
  --end-time $(date -u '+%Y-%m-%dT%H:%M:%S') \
  --period 300

# Check account limits
aws service-quotas get-service-quota \
  --service-code lambda \
  --quota-code L-B99A9384
```

**IAM Permission Issues**
```bash
# Test Lambda execution role
aws sts assume-role \
  --role-arn arn:aws:iam::account:role/craicgpt-lambda-execution-development \
  --role-session-name test-session

# Check policy attachments
aws iam list-attached-role-policies \
  --role-name craicgpt-lambda-execution-development
```

**S3 Access Problems**
```bash
# Test bucket access
aws s3 ls s3://craicgpt-content-dev/
aws s3 cp test.txt s3://craicgpt-content-dev/test.txt
aws s3 rm s3://craicgpt-content-dev/test.txt
```

### **Monitoring Commands**
```bash
# Monitor all Lambda functions
for func in craicgptie_prompt_generator craicgptie-orchestrator craicgptie_llm_runner craicgptie_image_runner; do
  echo "=== $func ==="
  aws logs tail /aws/lambda/$func --since 1h
done

# Check EventBridge trigger history
aws logs filter-log-events \
  --log-group-name /aws/events/rule/craicgpt-daily-prompts-development

# Monitor S3 operations
aws s3api get-bucket-notification-configuration \
  --bucket craicgpt-content-dev
```

## ⚠️ Production Deployment Checklist

Before deploying to production:

### **Pre-Deployment Validation**
- [ ] Test all Lambda functions individually
- [ ] Verify 10 Lambda concurrency limit enforcement
- [ ] Validate IAM permissions (principle of least privilege)
- [ ] Test secrets management and API key access
- [ ] Verify S3 bucket configuration and access patterns
- [ ] Test EventBridge scheduling and triggers

### **Production Configuration**
- [ ] Set `environment = "production"`
- [ ] Use production S3 bucket names
- [ ] Configure production secrets
- [ ] Set appropriate log retention periods
- [ ] Enable production monitoring and alerting
- [ ] Configure backup and disaster recovery

### **Post-Deployment Validation**
- [ ] Run end-to-end content generation test
- [ ] Monitor CloudWatch metrics for first 24 hours
- [ ] Verify cost tracking and optimization
- [ ] Test failure scenarios and recovery
- [ ] Document operational procedures

## 🤝 Contributing

### **Infrastructure Improvements**
- Enhanced monitoring and alerting
- Multi-region deployment support
- Advanced cost optimization
- Improved security configurations

### **Lambda Optimizations**
- Performance tuning for each function
- Advanced retry and error handling
- Cost-effective memory and timeout settings
- Improved logging and debugging

### **Operational Enhancements**
- Automated deployment pipelines
- Infrastructure testing frameworks
- Performance benchmarking
- Disaster recovery procedures

**Backend Infrastructure - Development Status** 🚧