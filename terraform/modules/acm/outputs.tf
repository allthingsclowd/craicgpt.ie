# Author: Graham Land & AI
# Date: YYYY-MM-DD
# Filename and Path: terraform/modules/acm/outputs.tf
# Description: Defines outputs for the ACM submodule.

output "certificate_arn" {
  description = "The ARN of the ACM certificate."
  value       = aws_acm_certificate.site_certificate.arn
}

output "certificate_validation_arn" {
  description = "The ARN of the validated ACM certificate (this is typically what CloudFront needs)."
  value       = aws_acm_certificate_validation.site_certificate_validation.certificate_arn
}

output "route53_validation_records_fqdns" {
  description = "The FQDNs of the DNS records used for validation."
  value       = [for record in aws_route53_record.certificate_validation : record.fqdn]
}
