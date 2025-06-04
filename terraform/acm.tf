# Author: Graham Land
# Date: 2025-06-04
# Filename and Path: terraform/acm.tf
# Description: Manages SSL/TLS certificate via AWS Certificate Manager for the domain,
#              including DNS validation using the us-east-1 provider alias.
#              Prerequisites: Route 53 hosted zone for the domain; providers configured in providers.tf.
#              Validation: Check if the ACM certificate status is 'Issued' in the AWS console (us-east-1 region).
#                          Verify DNS records for validation are created in the Route 53 hosted zone.

# terraform/acm.tf

# Defines common values for ACM certificate management.
locals {
  domain_name = "craicgpt.ie"
  # Common tags for resources in this file, promoting consistency.
  common_tags = {
    Environment = "production"
    Project     = "CraicGPT.ie"
    ManagedBy   = "Terraform"
  }
  # Specific tags for the ACM certificate.
  certificate_tags = merge(local.common_tags, {
    Name = "${local.domain_name}-cloudfront-certificate"
  })
}

# Retrieves information about the Route 53 hosted zone for the site's domain.
# This data source is used to get the zone ID, which is necessary for creating DNS validation records for ACM.
data "aws_route53_zone" "site_domain" {
  name = "${local.domain_name}." # The domain name of the hosted zone. Note the trailing dot.
}

# Provisions an ACM (AWS Certificate Manager) certificate for the specified domain.
# This certificate will be validated using DNS records created in the Route 53 hosted zone.
resource "aws_acm_certificate" "site_certificate" {
  provider          = aws.us_east_1_acm   # Explicitly uses the us-east-1 AWS provider.
  domain_name       = local.domain_name   # The primary domain name for the certificate.
  validation_method = "DNS"               # Specifies DNS as the validation method.
  subject_alternative_names = [
    "www.${local.domain_name}"            # Subject Alternative Names (SANs) for the certificate.
  ]

  # Lifecycle rule to ensure a new certificate is created before the old one is destroyed.
  # This helps prevent downtime during certificate renewal by managing the replacement process.
  lifecycle {
    create_before_destroy = true
  }

  tags = local.certificate_tags # Applies the defined tags to the certificate resource.
}

# Creates DNS validation records in AWS Route 53.
# These records are required by ACM to validate domain ownership for the certificate.
# A separate DNS record is created for each domain name (primary and SANs) specified in the certificate.
resource "aws_route53_record" "certificate_validation" {
  # Iterates over the domain validation options provided by the ACM certificate resource.
  # Each option corresponds to a domain that needs validation.
  for_each = {
    for dvo in aws_acm_certificate.site_certificate.domain_validation_options : dvo.domain_name => {
      name    = dvo.resource_record_name # The name of the record ACM expects.
      type    = dvo.resource_record_type # The type of record (e.g., CNAME).
      value   = dvo.resource_record_value # The value of the record.
      zone_id = data.aws_route53_zone.site_domain.zone_id # Associates record with the correct hosted zone.
    }
  }

  name    = each.value.name   # The name of the DNS record.
  type    = each.value.type   # The type of the DNS record.
  records = [each.value.value] # The value(s) for the DNS record.
  ttl     = 60                # Time-to-live for the DNS record in seconds.
  zone_id = each.value.zone_id # The ID of the hosted zone where the record will be created.
}

# Validates the ACM certificate using the DNS records created above.
# This resource effectively 'waits' for AWS to confirm that the DNS validation records
# are correctly in place and match the details of the certificate.
resource "aws_acm_certificate_validation" "site_certificate_validation" {
  provider                = aws.us_east_1_acm # Explicitly uses the us-east-1 AWS provider.
  certificate_arn         = aws_acm_certificate.site_certificate.arn # ARN of the certificate to validate.
  # A list of Fully Qualified Domain Names (FQDNs) of the DNS records used for validation.
  validation_record_fqdns = [for record in aws_route53_record.certificate_validation : record.fqdn]

  # Ensures that the DNS validation records are created before attempting certificate validation.
  # This explicit dependency is crucial for the correct order of operations.
  depends_on = [aws_route53_record.certificate_validation]
}