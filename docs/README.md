# Documentation - Additional Guides and Resources

**Comprehensive Documentation for CraicGPT.ie Multi-Provider AI System**

This directory contains additional documentation, setup guides, troubleshooting resources, and best practices for the CraicGPT.ie multi-provider AI newspaper generation system.

## 📁 Documentation Contents

### **Setup and Configuration Guides**
- **`secrets-manager-setup.md`**: Complete guide for configuring AWS Secrets Manager with multi-provider API keys

### **Planned Documentation** (To be added)
- **`deployment-guide.md`**: Step-by-step deployment instructions
- **`troubleshooting.md`**: Common issues and solutions
- **`api-provider-setup.md`**: Individual provider account setup
- **`cost-optimization.md`**: Managing costs across multiple providers
- **`monitoring-guide.md`**: CloudWatch and observability setup

## 🎯 Purpose

Provide comprehensive documentation to support:
- **System Administration**: Setup, configuration, and maintenance
- **Development**: Contributing to the codebase and adding features
- **Operations**: Monitoring, troubleshooting, and optimization
- **Education**: Understanding multi-provider AI integration

## 🏗️ Documentation Architecture

### **Multi-Provider Integration**
Documentation covers all supported providers:
- **AWS Bedrock**: IAM-based authentication, native integration
- **OpenAI**: API key management, GPT and DALL-E integration
- **Anthropic Direct**: Direct API access, Claude model optimization
- **Google Gemini**: API key setup, multimodal capabilities

### **Infrastructure Components**
- **Frontend**: S3 static hosting, CloudFront CDN, Route 53 DNS
- **Backend**: Lambda functions, EventBridge scheduling, S3 storage
- **Security**: Secrets Manager, IAM policies, encryption
- **Monitoring**: CloudWatch logs, metrics, alerting

## 🚀 Quick Reference

### **Essential Setup Commands**
```bash
# Deploy frontend infrastructure
cd terraform/frontend && terraform apply

# Deploy backend infrastructure (development)
cd terraform/backend && terraform apply

# Configure API secrets
aws secretsmanager put-secret-value \
  --secret-id craicgpt/openai-api-key \
  --secret-string "your-api-key"

# Test system end-to-end
aws lambda invoke \
  --function-name craicgptie-orchestrator \
  --payload '{"START_DATE":"2025-01-15","END_DATE":"2025-01-15"}' \
  --cli-binary-format raw-in-base64-out \
  test.json
```

### **Common Monitoring Commands**
```bash
# Monitor Lambda execution
aws logs tail /aws/lambda/craicgptie-orchestrator --follow

# Check S3 content generation
aws s3 ls s3://your-bucket/static_assets/content/website/2025/01/15/

# Verify secrets access
aws secretsmanager get-secret-value --secret-id craicgpt/openai-api-key
```

## 📊 System Overview

### **Content Generation Pipeline**
```
1. PromptGenerator → 2. Orchestrator → 3. LLM/Image Workers → 4. S3 Storage → 5. Frontend Display
     │                      │                    │                   │               │
     ├─ Context Gathering   ├─ Concurrency       ├─ Multi-Provider   ├─ JSON/Binary  ├─ Model Selection
     ├─ Prompt Engineering  ├─ Dependency Mgmt   ├─ Error Handling   ├─ Caching      ├─ Comparison View
     └─ S3 Storage         └─ Progress Tracking └─ Standardized      └─ Versioning   └─ Educational UI
                                                    Response Format
```

### **Architectural Principles**
- **Multi-Provider Support**: Unified interface across all AI providers
- **10 Lambda Limit Compliance**: Strict concurrency control and monitoring
- **Educational Transparency**: Visible prompt engineering and parameters
- **Production Ready**: Robust error handling and monitoring
- **Cost Optimization**: Efficient resource usage and provider selection

## 🔧 Configuration Management

### **Environment Variables**
All components use consistent environment variable patterns:

```bash
# S3 Storage
PROMPT_BUCKET=your-s3-bucket-name

# Multi-provider secrets
OPENAI_SECRET_NAME=craicgpt/openai-api-key
ANTHROPIC_SECRET_NAME=craicgpt/anthropic-api-key
GOOGLE_SECRET_NAME=craicgpt/google-api-key

# Concurrency control
MAX_ACCOUNT_CONCURRENT=9
CONCURRENCY_CHECK_ENABLED=true

# Model configuration
BEDROCK_MODEL_IDS=anthropic.claude-3-sonnet-20240229-v1:0,amazon.titan-text-express-v1
OPENAI_MODEL_IDS=gpt-4,o3-mini
```

### **Terraform Variables**
Centralized configuration through terraform.tfvars:

```hcl
# Core settings
domain_name = "craicgpt.ie"
environment = "production"
project_name = "craicgpt"

# Provider configuration
enable_openai = true
enable_anthropic = true
enable_google = true

# Resource sizing
lambda_memory_size = 1024
lambda_timeout = 300
```

## 🔐 Security Best Practices

### **API Key Management**
- Store all external API keys in AWS Secrets Manager
- Use IAM policies for least-privilege access
- Rotate keys regularly and monitor usage
- Never commit keys to source control

### **Infrastructure Security**
- Enable encryption at rest for all S3 buckets
- Use HTTPS only for all communications
- Implement proper CORS policies
- Regular security audits and updates

### **Lambda Security**
- Minimal IAM permissions for each function
- VPC configuration when required
- Environment variable encryption
- Regular security patching

## 📈 Performance and Cost Optimization

### **Lambda Optimization**
- Right-sized memory allocation based on function requirements
- Optimal timeout settings to prevent unnecessary costs
- Efficient error handling to reduce retry overhead
- Connection pooling for external API calls

### **Multi-Provider Cost Management**
- Track usage and costs per provider
- Implement intelligent provider selection
- Monitor token usage and optimize prompt efficiency
- Use reserved capacity where beneficial

### **S3 and CloudFront Optimization**
- Lifecycle policies for old content archival
- Optimal caching strategies for different content types
- Compression and optimization for static assets
- Regional optimization for primary audience

## 🔍 Monitoring and Observability

### **CloudWatch Integration**
- Comprehensive logging for all Lambda functions
- Custom metrics for business KPIs
- Alerting for failures and performance issues
- Cost tracking and budget alerts

### **Application Monitoring**
- End-to-end content generation tracking
- Provider-specific performance metrics
- User interaction analytics
- Error rate and success rate monitoring

### **Operational Dashboards**
- Real-time system health overview
- Content generation pipeline status
- Cost breakdown by provider and component
- Performance trends and optimization opportunities

## 🧪 Testing and Validation

### **Infrastructure Testing**
```bash
# Terraform validation
terraform validate
terraform plan -detailed-exitcode

# Security scanning
checkov -f main.tf

# Deployment validation
./scripts/validate-deployment.sh
```

### **Application Testing**
```bash
# Unit tests for Lambda functions
pytest tests/

# Integration testing
./scripts/integration-test.sh

# End-to-end validation
./scripts/e2e-test.sh
```

### **Performance Testing**
```bash
# Load testing
./scripts/load-test.sh

# Stress testing for concurrency limits
./scripts/stress-test.sh

# Cost analysis
./scripts/cost-analysis.sh
```

## 🐛 Troubleshooting

### **Common Issues and Solutions**

#### **Lambda Concurrency Exceeded**
- **Symptom**: TooManyRequestsException errors
- **Solution**: Check CloudWatch metrics, adjust MAX_ACCOUNT_CONCURRENT
- **Prevention**: Monitor concurrency usage proactively

#### **API Key Authentication Failures**
- **Symptom**: 401/403 errors from external providers
- **Solution**: Verify secrets in Secrets Manager, check IAM permissions
- **Prevention**: Regular key rotation and monitoring

#### **Content Generation Failures**
- **Symptom**: Empty or error responses from providers
- **Solution**: Check prompts, validate model availability, review logs
- **Prevention**: Comprehensive error handling and retry logic

### **Debugging Tools and Commands**
```bash
# Lambda function logs
aws logs tail /aws/lambda/function-name --follow

# Secrets Manager access test
aws secretsmanager get-secret-value --secret-id secret-name

# S3 content verification
aws s3 ls s3://bucket-name/path/ --recursive

# CloudWatch metrics
aws cloudwatch get-metric-statistics --namespace AWS/Lambda --metric-name Duration
```

## 🤝 Contributing

### **Documentation Guidelines**
- Use clear, concise language with practical examples
- Include code snippets and command-line examples
- Maintain consistency in formatting and structure
- Update documentation with any system changes

### **Adding New Documentation**
1. Identify documentation gaps or new requirements
2. Create structured documentation following existing patterns
3. Include practical examples and testing procedures
4. Review for accuracy and completeness
5. Update main README.md with new documentation links

### **Documentation Maintenance**
- Regular reviews to ensure accuracy with current system
- Update examples and commands as system evolves
- Incorporate feedback from users and operators
- Maintain version control for documentation changes

## 🔗 Related Resources

### **Internal Documentation**
- [Main README](../README.md): Complete system overview and documentation tree
- [Frontend Documentation](../frontend/README.md): Static website and UI components
- [Backend Documentation](../lambda_code/README.md): Serverless pipeline overview
- [Infrastructure Documentation](../terraform/README.md): Complete infrastructure automation

### **External Resources**
- [AWS Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [AWS Secrets Manager User Guide](https://docs.aws.amazon.com/secretsmanager/latest/userguide/)
- [Terraform AWS Provider Documentation](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [OpenAI API Documentation](https://platform.openai.com/docs)
- [Anthropic API Documentation](https://docs.anthropic.com/)
- [Google AI API Documentation](https://ai.google.dev/)

### **Provider-Specific Documentation**
- **AWS Bedrock**: Native integration with IAM authentication
- **OpenAI**: GPT-4, O3 Mini for text; DALL-E 3 for images
- **Anthropic**: Claude 3.5 Sonnet, Claude 3 Opus direct API access
- **Google Gemini**: Gemini Pro, Gemini Ultra with multimodal capabilities

**Comprehensive Documentation - Educational and Production Ready** 📚