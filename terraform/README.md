# Terraform - Infrastructure as Code

**Complete Infrastructure Automation for CraicGPT.ie**

This directory contains Terraform configurations for deploying all CraicGPT.ie infrastructure components. The infrastructure is split into frontend (production-ready) and backend (lambda functions) deployments.

## 🏗️ Architecture Overview

### **Infrastructure Components**
```
Frontend Infrastructure (Production ✅)
├── S3 Static Website Hosting
├── CloudFront CDN Distribution  
├── Route 53 DNS Configuration
├── ACM SSL Certificate
└── IAM Policies & Roles

Backend Infrastructure (Development 🚧)
├── Lambda Functions (4 functions)
├── EventBridge Schedulers
├── S3 Bucket for Content Storage
├── IAM Roles & Policies
└── Secrets Manager Integration
```

### **Deployment Strategy**
- **Frontend**: Fully automated Terraform deployment
- **Backend**: Terraform configuration available, manual validation required
- **Environments**: Development and Production configurations
- **State Management**: Remote state with S3 backend and DynamoDB locking

## 📁 Directory Structure

```
terraform/
├── frontend/                 # Frontend infrastructure (Production Ready ✅)
│   ├── main.tf              # Main configuration
│   ├── variables.tf         # Input variables
│   ├── outputs.tf           # Output values
│   ├── terraform.tfvars.example  # Example configuration
│   └── README.md            # Frontend-specific documentation
├── backend/                  # Backend infrastructure (Development 🚧)
│   ├── main.tf              # Lambda and supporting services
│   ├── variables.tf         # Input variables
│   ├── outputs.tf           # Output values
│   ├── terraform.tfvars.example  # Example configuration
│   └── README.md            # Backend-specific documentation
└── README.md                # This file
```

## 🚀 Quick Start

### **Prerequisites**
```bash
# Install Terraform
brew install terraform  # macOS
# or download from https://terraform.io/downloads

# Verify installation
terraform version  # Should be >= 1.8.0

# Configure AWS CLI
aws configure
```

### **Frontend Deployment** (Production Ready)
```bash
cd terraform/frontend

# Copy and configure variables
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your domain and settings

# Initialize Terraform
terraform init

# Review planned changes
terraform plan

# Deploy infrastructure
terraform apply
```

### **Backend Deployment** (Requires Validation)
```bash
cd terraform/backend

# Copy and configure variables
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your settings

# Initialize Terraform
terraform init

# Review planned changes (VALIDATE CAREFULLY)
terraform plan

# Deploy infrastructure (PROCEED WITH CAUTION)
terraform apply
```

## 🔧 Configuration Management

### **Environment Variables**
Create `terraform.tfvars` in each directory:

**Frontend Configuration:**
```hcl
# Domain Configuration
domain_name = "craicgpt.ie"
route53_zone_id = "Z1234567890ABC"

# Environment
environment = "production"
project_name = "craicgpt"

# AWS Configuration
aws_region = "eu-west-1"
```

**Backend Configuration:**
```hcl
# Environment
environment = "production"
project_name = "craicgpt"

# Lambda Configuration
lambda_memory_size = 1024
lambda_timeout = 300

# S3 Configuration
content_bucket_name = "craicgpt-content-prod"

# Secrets Configuration
openai_secret_name = "craicgpt/openai-api-key"
anthropic_secret_name = "craicgpt/anthropic-api-key"
google_secret_name = "craicgpt/google-api-key"
```

### **State Management**
Both configurations support remote state:

```hcl
terraform {
  backend "s3" {
    bucket         = "your-terraform-state-bucket"
    key            = "craicgpt/frontend/terraform.tfstate"
    region         = "eu-west-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}
```

## 📊 Infrastructure Components

### **Frontend Infrastructure** ✅
- **S3 Bucket**: Static website hosting with public read access
- **CloudFront Distribution**: Global CDN with custom domain
- **Route 53 Records**: DNS configuration for custom domain
- **ACM Certificate**: SSL/TLS certificate for HTTPS
- **IAM Policies**: Minimal required permissions

### **Backend Infrastructure** 🚧
- **Lambda Functions**: 4 functions with proper IAM roles
- **EventBridge Rules**: Scheduled triggers for automation
- **S3 Bucket**: Content storage with proper CORS configuration
- **Secrets Manager**: Secure API key storage
- **CloudWatch**: Logging and monitoring configuration

### **Security Configuration**
- **IAM Principle of Least Privilege**: Minimal required permissions
- **Encryption**: All data encrypted at rest and in transit
- **HTTPS Only**: All traffic over encrypted connections
- **Resource Tagging**: Comprehensive tagging for cost tracking

## 🔐 Security Best Practices

### **IAM Configuration**
```hcl
# Example IAM policy for Lambda execution
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "lambda_execution_role" {
  name               = "${var.project_name}-lambda-execution"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  
  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}
```

### **S3 Security**
```hcl
# S3 bucket with proper security settings
resource "aws_s3_bucket" "content_bucket" {
  bucket = var.content_bucket_name
  
  tags = {
    Environment = var.environment
    Project     = var.project_name
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

## 📈 Cost Optimization

### **Resource Sizing**
- **Lambda Functions**: Optimized memory allocation based on function needs
- **S3 Storage**: Lifecycle policies for cost-effective storage
- **CloudFront**: Appropriate price class for global distribution
- **Route 53**: Minimal required DNS queries

### **Cost Monitoring**
```hcl
# Resource tagging for cost tracking
locals {
  common_tags = {
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
    Component   = "infrastructure"
  }
}
```

### **Estimated Costs** (Monthly)
- **Frontend Infrastructure**: $5-15/month (depending on traffic)
- **Backend Infrastructure**: $10-50/month (depending on usage)
- **Total Estimated**: $15-65/month for complete system

## 🔄 Deployment Workflows

### **Development Workflow**
```bash
# 1. Make infrastructure changes
git checkout -b feature/infrastructure-update

# 2. Test changes
terraform plan

# 3. Apply to development environment
terraform apply -var-file="dev.tfvars"

# 4. Validate deployment
./scripts/validate-deployment.sh

# 5. Create pull request
git add . && git commit -m "Update infrastructure"
git push origin feature/infrastructure-update
```

### **Production Deployment**
```bash
# 1. Review all changes carefully
terraform plan -var-file="prod.tfvars" -out=prod.plan

# 2. Apply changes
terraform apply prod.plan

# 3. Validate production deployment
./scripts/production-health-check.sh
```

## 🧪 Testing & Validation

### **Infrastructure Testing**
```bash
# Validate Terraform configuration
terraform validate

# Check formatting
terraform fmt -check

# Security scanning (if Checkov is installed)
checkov -f main.tf

# Plan without applying
terraform plan -detailed-exitcode
```

### **Deployment Validation**
```bash
# Test frontend deployment
curl -I https://craicgpt.ie
# Should return 200 OK with proper headers

# Test backend functions (after deployment)
aws lambda list-functions --query 'Functions[?starts_with(FunctionName, `craicgptie`)].FunctionName'

# Test S3 bucket access
aws s3 ls s3://your-content-bucket-name/
```

## 🐛 Troubleshooting

### **Common Issues**

**State Lock Issues**
```bash
# Force unlock if needed (use with caution)
terraform force-unlock LOCK_ID

# Check DynamoDB for lock entries
aws dynamodb scan --table-name terraform-locks
```

**Provider Issues**
```bash
# Re-initialize if providers change
terraform init -upgrade

# Clear provider cache
rm -rf .terraform/
terraform init
```

**Permission Issues**
```bash
# Verify AWS credentials
aws sts get-caller-identity

# Check IAM permissions
aws iam get-user
aws iam list-attached-user-policies --user-name YOUR_USERNAME
```

### **Debugging Tools**
```bash
# Enable detailed logging
export TF_LOG=DEBUG
terraform plan

# Validate AWS resources
aws cloudformation describe-stacks
aws lambda list-functions
aws s3 ls
```

## 🤝 Contributing

### **Infrastructure Changes**
1. Create feature branch for infrastructure updates
2. Test changes in development environment first
3. Document all changes and their impact
4. Get review for production deployments
5. Follow rollback procedures if issues occur

### **Best Practices**
- Always run `terraform plan` before `apply`
- Use descriptive resource names and tags
- Document any manual configuration steps
- Keep state files secure and backed up
- Regular infrastructure audits and updates

### **Adding New Resources**
1. Define resources in appropriate module
2. Add necessary variables and outputs
3. Update documentation
4. Test in development environment
5. Create migration plan for production

**Infrastructure as Code - Production Ready** 🏗️