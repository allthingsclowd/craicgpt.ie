# acm.tf

# 1. Define a separate AWS Provider for us-east-1 (N. Virginia)
# This is crucial for CloudFront certificates
provider "aws" {
  alias  = "us_east_1_acm"
  region = "us-east-1"
}

# 2. Retrieve your Route 53 Hosted Zone (replace with your actual domain and zone ID)
# This assumes your DNS is managed by Route 53
data "aws_route53_zone" "primary" {
  name = "craicgpt.ie." # Don't forget the trailing dot!
}

# 3. Declare the ACM Certificate Resource
resource "aws_acm_certificate" "main_certificate" {
  provider          = aws.us_east_1_acm # Explicitly use the us-east-1 provider
  domain_name       = "craicgpt.ie"
  validation_method = "DNS"
  subject_alternative_names = [
    "www.craicgpt.ie"
  ]

  # Lifecycle rule to ensure a new certificate is created before the old one is destroyed
  # This prevents downtime during certificate renewal
  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name        = "craicgpt-cloudfront-certificate"
    Environment = "production"
  }
}

# 4. Create DNS Validation Records in Route 53
# This uses a for_each loop to create a CNAME record for each domain/SAN in the certificate
resource "aws_route53_record" "certificate_validation" {
  for_each = {
    for dvo in aws_acm_certificate.main_certificate.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      value  = dvo.resource_record_value
      zone_id = data.aws_route53_zone.primary.zone_id
    }
  }

  name    = each.value.name
  type    = each.value.type
  records = [each.value.value]
  ttl     = 60 # Time-to-live for the DNS record
  zone_id = each.value.zone_id
}

# 5. Validate the ACM Certificate
resource "aws_acm_certificate_validation" "main_certificate_validation" {
  provider                = aws.us_east_1_acm # Explicitly use the us-east-1 provider
  certificate_arn         = aws_acm_certificate.main_certificate.arn
  validation_record_fqdns = [for record in aws_route53_record.certificate_validation : record.fqdn]

  # Depend on the creation of the validation records to ensure they exist before validation
  depends_on = [aws_route53_record.certificate_validation]
}

# Output the ARN of the validated certificate for use in CloudFront distributions
output "acm_certificate_arn" {
  description = "The ARN of the validated ACM certificate in us-east-1."
  value       = aws_acm_certificate_validation.main_certificate_validation.certificate_arn
}