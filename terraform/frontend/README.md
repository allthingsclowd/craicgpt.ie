# Frontend Infrastructure - Production Ready ✅

**Complete Frontend Deployment with S3, CloudFront, Route 53, and SSL**

This directory contains production-ready Terraform configurations for deploying the CraicGPT.ie frontend infrastructure. The configuration includes static website hosting, global CDN distribution, custom domain setup, and SSL certificate management.

## 🏗️ Architecture Overview

### **Infrastructure Components**
```
Frontend Production Infrastructure ✅
├── S3 Static Website Hosting
│   ├── Public read access for web content
│   ├── Static website configuration
│   └── CORS configuration for API calls
├── CloudFront CDN Distribution
│   ├── Global edge locations
│   ├── Custom domain with SSL/TLS
│   ├── Cache optimization for static assets
│   └── Security headers and policies
├── Route 53 DNS Configuration
│   ├── A record for apex domain
│   ├── AAAA record for IPv6 support
│   └── DNS validation for SSL certificate
├── ACM SSL Certificate
│   ├── Automatic DNS validation
│   ├── Wildcard certificate support
│   └── Auto-renewal capabilities
└── IAM Policies & Roles
    ├── S3 bucket policies
    ├── CloudFront origin access
    └── Minimal required permissions
```

### **Modular Architecture**
- **`modules/s3/`**: S3 bucket configuration for static hosting
- **`modules/cloudfront/`**: CloudFront distribution with custom domain
- **`modules/acm/`**: SSL certificate management and validation
- **`modules/frontend-upload/`**: Automated frontend deployment
- **`modules/lambda/`**: Supporting Lambda functions for automation
- **`modules/scheduler/`**: EventBridge schedulers for automated tasks

## 🚀 Quick Deployment

### **Prerequisites**
```bash
# Install Terraform (macOS)
brew install terraform

# Verify installation
terraform version  # Should be >= 1.8.0

# Configure AWS CLI
aws configure
# Set up credentials with appropriate permissions
```

### **Configuration Setup**
```bash
cd terraform/frontend

# Copy example configuration
cp terraform.tfvars.example terraform.tfvars

# Edit configuration with your domain details
nano terraform.tfvars
```

### **Required Configuration Variables**
```hcl
# Domain Configuration (REQUIRED)
domain_name = "craicgpt.ie"
route53_zone_id = "Z1234567890ABC"  # Your Route 53 Hosted Zone ID

# Environment Settings
environment = "production"
project_name = "craicgpt"

# AWS Configuration
aws_region = "eu-west-1"

# Optional: Custom S3 bucket names
s3_bucket_name = "craicgpt-frontend-prod"
s3_logs_bucket_name = "craicgpt-logs-prod"

# Optional: CloudFront configuration
cloudfront_price_class = "PriceClass_100"  # US, Canada, Europe
enable_ipv6 = true
```

### **Deployment Process**
```bash
# Initialize Terraform
terraform init

# Review planned changes
terraform plan

# Deploy infrastructure (production ready)
terraform apply

# Verify deployment
curl -I https://craicgpt.ie
# Should return 200 OK with proper headers
```

## 📁 Module Breakdown

### **S3 Static Website Module** (`modules/s3/`)
**Purpose**: Static website hosting with proper security configurations

**Key Features**:
- Public read access for web content
- Static website configuration with index.html
- CORS configuration for API requests
- Server-side encryption enabled
- Versioning for content management
- Lifecycle policies for cost optimization

**Outputs**:
- `bucket_name`: S3 bucket name for content uploads
- `bucket_domain_name`: S3 bucket domain for CloudFront origin
- `bucket_arn`: S3 bucket ARN for IAM policies

### **CloudFront CDN Module** (`modules/cloudfront/`)
**Purpose**: Global content delivery with custom domain and SSL

**Key Features**:
- Custom domain with SSL certificate
- Global edge location distribution
- Cache optimization for different content types
- Security headers (HSTS, Content Security Policy)
- Origin access identity for S3 security
- Custom error pages (404, 403)

**Cache Configuration**:
```hcl
# Static assets (long cache)
cache_behavior_static = {
  path_pattern = "/static/*"
  ttl_default = 86400    # 24 hours
  ttl_max = 31536000     # 1 year
}

# HTML content (short cache)
cache_behavior_html = {
  path_pattern = "*.html"
  ttl_default = 300      # 5 minutes
  ttl_max = 3600         # 1 hour
}
```

### **ACM SSL Certificate Module** (`modules/acm/`)
**Purpose**: Automated SSL certificate management

**Key Features**:
- Automatic DNS validation
- Wildcard certificate support (`*.craicgpt.ie`)
- Auto-renewal capabilities
- CloudFront compatibility (us-east-1 region)

**Validation Process**:
```hcl
# Certificate validation via DNS
resource "aws_acm_certificate_validation" "cert" {
  certificate_arn         = aws_acm_certificate.cert.arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation : record.fqdn]
  
  timeouts {
    create = "5m"
  }
}
```

### **Frontend Upload Module** (`modules/frontend-upload/`)
**Purpose**: Automated frontend content deployment

**Key Features**:
- Automated upload of static website files
- Content type detection and proper headers
- Cache invalidation for CloudFront
- Build optimization and minification

## 🔧 Configuration Management

### **Environment Variables**
Create `terraform.tfvars` with your specific configuration:

```hcl
# Core Configuration
domain_name = "craicgpt.ie"
route53_zone_id = "Z1234567890ABC"
environment = "production"
project_name = "craicgpt"
aws_region = "eu-west-1"

# S3 Configuration
s3_bucket_name = "craicgpt-frontend-prod"
s3_logs_bucket_name = "craicgpt-logs-prod"
enable_s3_versioning = true

# CloudFront Configuration
cloudfront_price_class = "PriceClass_100"
enable_ipv6 = true
enable_compression = true

# SSL Configuration
enable_ssl = true
ssl_minimum_protocol_version = "TLSv1.2_2021"

# Monitoring
enable_cloudwatch_logs = true
log_retention_days = 30
```

### **State Management**
The configuration supports remote state for production safety:

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

## 📊 Outputs & Integration

### **Important Outputs**
```hcl
# CloudFront Distribution
output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID for cache invalidation"
  value       = module.cloudfront.distribution_id
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name"
  value       = module.cloudfront.domain_name
}

# S3 Bucket Information
output "s3_bucket_name" {
  description = "S3 bucket name for content uploads"
  value       = module.s3.bucket_name
}

# SSL Certificate
output "ssl_certificate_arn" {
  description = "ACM certificate ARN"
  value       = module.acm.certificate_arn
}

# Custom Domain
output "website_url" {
  description = "Website URL with custom domain"
  value       = "https://${var.domain_name}"
}
```

### **Integration with Backend**
The frontend infrastructure integrates with backend services:

```bash
# Frontend calls backend APIs
API_ENDPOINT="https://api.craicgpt.ie"
CORS_ORIGIN="https://craicgpt.ie"
```

## 🔐 Security Configuration

### **S3 Bucket Security**
```hcl
# Bucket policy for CloudFront access only
data "aws_iam_policy_document" "s3_policy" {
  statement {
    sid    = "AllowCloudFrontAccess"
    effect = "Allow"
    
    principals {
      type        = "AWS"
      identifiers = [aws_cloudfront_origin_access_identity.oai.iam_arn]
    }
    
    actions = [
      "s3:GetObject"
    ]
    
    resources = [
      "${aws_s3_bucket.frontend.arn}/*"
    ]
  }
}
```

### **CloudFront Security Headers**
```hcl
# Security headers configuration
response_headers_policy = {
  strict_transport_security = {
    access_control_max_age_sec = 31536000
    include_subdomains         = true
    preload                   = true
  }
  
  content_security_policy = {
    content_security_policy = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';"
    override                = false
  }
}
```

## 📈 Performance Optimization

### **Caching Strategy**
- **Static Assets**: 1 year cache (CSS, JS, images)
- **HTML Files**: 5 minute cache for dynamic updates
- **API Responses**: No cache to ensure fresh data

### **CloudFront Optimization**
```hcl
# Compression for text-based content
compress = true

# HTTP/2 support
http_version = "http2"

# Optimal price class for target audience
price_class = "PriceClass_100"  # US, Canada, Europe

# IPv6 support for modern clients
is_ipv6_enabled = true
```

### **Cost Optimization**
- **S3 Lifecycle Policies**: Archive old content to cheaper storage classes
- **CloudFront Price Class**: Optimized for primary geographic regions
- **Resource Tagging**: Comprehensive cost tracking and allocation

## 🧪 Testing & Validation

### **Deployment Validation**
```bash
# Test website accessibility
curl -I https://craicgpt.ie
# Expected: 200 OK with proper headers

# Verify SSL certificate
curl -vI https://craicgpt.ie 2>&1 | grep -i "SSL certificate verify ok"

# Check CloudFront headers
curl -H "Accept-Encoding: gzip" -I https://craicgpt.ie
# Should include CloudFront headers and compression

# Test DNS resolution
nslookup craicgpt.ie
dig craicgpt.ie
```

### **Performance Testing**
```bash
# Website speed test
curl -o /dev/null -s -w "Time: %{time_total}s\nSize: %{size_download} bytes\n" https://craicgpt.ie

# CloudFront cache validation
curl -I https://craicgpt.ie/static/style.css
# Look for X-Cache: Hit from cloudfront
```

## 🐛 Troubleshooting

### **Common Issues**

**SSL Certificate Validation Failing**
```bash
# Check Route 53 DNS records
aws route53 list-resource-record-sets --hosted-zone-id Z1234567890ABC

# Verify certificate status
aws acm describe-certificate --certificate-arn arn:aws:acm:us-east-1:account:certificate/certificate-id
```

**CloudFront Distribution Issues**
```bash
# Check distribution status
aws cloudfront get-distribution --id E1234567890ABC

# Test origin connectivity
aws s3 ls s3://craicgpt-frontend-prod --recursive

# Create cache invalidation
aws cloudfront create-invalidation --distribution-id E1234567890ABC --paths "/*"
```

**S3 Access Issues**
```bash
# Test bucket policy
aws s3 cp test.html s3://craicgpt-frontend-prod/test.html --acl public-read

# Check bucket CORS configuration
aws s3api get-bucket-cors --bucket craicgpt-frontend-prod
```

### **Monitoring Commands**
```bash
# Check CloudWatch metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/CloudFront \
  --metric-name Requests \
  --dimensions Name=DistributionId,Value=E1234567890ABC \
  --statistics Sum \
  --start-time $(date -v-1H -u '+%Y-%m-%dT%H:%M:%S') \
  --end-time $(date -u '+%Y-%m-%dT%H:%M:%S') \
  --period 3600

# Monitor S3 access logs
aws s3 ls s3://craicgpt-logs-prod/cloudfront-logs/ --recursive
```

## 🤝 Contributing

### **Frontend Updates**
1. Update static files in `/frontend` directory
2. Run `terraform apply` to deploy changes
3. CloudFront cache invalidation is automatic
4. Monitor performance and accessibility

### **Infrastructure Improvements**
- Enhanced security headers and policies
- Advanced caching strategies
- Multi-region deployment capabilities
- Progressive web app (PWA) support

### **Monitoring Enhancements**
- Custom CloudWatch dashboards
- Real-time performance metrics
- Cost tracking and optimization alerts
- User experience monitoring

**Frontend Infrastructure - Production Ready** 🌐