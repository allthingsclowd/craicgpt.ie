<p align="center">
  <img src="docs/images/logo1.png" alt="CraicGPT Logo" width="150"/>
  <img src="docs/images/logo2.png" alt="AWS Logo" width="150"/>
</p>

# CraicGPT.ie Infrastructure

This repository contains the Terraform code to manage the infrastructure for the [craicgpt.ie](https://www.craicgpt.ie) website and its backend content generation services, all hosted on Amazon Web Services (AWS).

## Purpose and Goal

The primary goal of this infrastructure is to provide a scalable and cost-effective platform for:
1.  Hosting the static frontend website for CraicGPT.ie.
2.  Running scheduled backend services that leverage various Large Language Models (LLMs) and image generation models to create and update content for the website.

## Terraform Deployments

The infrastructure is divided into two main Terraform deployments, located in the `terraform/` directory:

### 1. Frontend Deployment (`terraform/frontend`)

*   **Responsibility:** Deploys the public-facing craicgpt.ie website and its core components.
*   **Key Aspects:**
    *   **Amazon S3:** For static website hosting.
    *   **Amazon CloudFront:** Acts as the Content Delivery Network (CDN) for global content distribution, caching, and SSL/TLS termination.
    *   **AWS Certificate Manager (ACM):** Manages the SSL/TLS certificates for the custom domain.
    *   **Amazon Route 53:** Used for DNS records that point the custom domain to the CloudFront distribution.
    *   **(Optional) AWS Lambda & EventBridge Scheduler:** Includes configurations for a Lambda function (e.g., for content orchestration from the frontend perspective) and a scheduler to trigger it.
*   **Status:** Fully functional.

### 2. Backend Deployment (`terraform/backend`)

*   **Responsibility:** Deploys AWS Lambda functions and associated resources for scheduled, automated content generation.
*   **Key Aspects:**
    *   **AWS Lambda:** Hosts various functions designed to interact with different LLMs (e.g., Bedrock Titan, Claude, OpenAI ChatGPT, Google Gemini) and image generation models (e.g., Bedrock Titan Image, Stability AI, DALL-E).
    *   **Amazon EventBridge Scheduler:** Manages cron-like schedules to trigger these Lambda functions periodically.
    *   **AWS IAM:** Defines specific roles and policies for Lambda functions, granting necessary permissions to access services like Bedrock, Secrets Manager (for API keys), and the frontend's S3 bucket for content output.
    *   **Content Output:** Lambda functions are designed to write their generated content (e.g., articles, images) to the S3 bucket managed by the frontend deployment.
*   **Status:** Work in progress. The Terraform code is structured with modules and has passed `terraform validate`. However, the Lambda function code itself and the end-to-end integration require further development, debugging, and thorough testing.

## Prerequisites

Before you can deploy this infrastructure, you need the following tools installed and configured:

*   **Terraform:** Version 1.8.0 or later is recommended.
*   **AWS CLI:** Configured with appropriate AWS credentials and a default region. Ensure the IAM user/role has sufficient permissions to create the resources defined in the Terraform code.

## Usage Instructions

Follow these general steps for both the frontend and backend deployments:

1.  **Navigate to the Deployment Directory:**
    *   For frontend: `cd terraform/frontend`
    *   For backend: `cd terraform/backend`

2.  **Prepare Terraform Variables:**
    *   Copy the example variables file: `cp terraform.tfvars.example terraform.tfvars`
    *   Edit `terraform.tfvars` and update the values to match your specific requirements (e.g., domain names, API key secret ARNs, S3 bucket names if overriding).

3.  **Initialize Terraform:**
    *   This command downloads necessary provider plugins and initializes modules.
    ```bash
    terraform init
    ```

4.  **Plan Changes:**
    *   This command shows you what changes Terraform will make to your infrastructure. Review this carefully.
    ```bash
    terraform plan
    ```

5.  **Apply Changes:**
    *   This command applies the planned changes to your AWS account. You will be prompted to confirm.
    ```bash
    terraform apply
    ```

## Variables

Each deployment (`terraform/frontend` and `terraform/backend`) has its own set of input variables defined in its respective `variables.tf` file, and that `terraform.tfvars.example` files provide guidance.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs, feature requests, or improvements.

## License

This project is licensed under the MIT License - see the `LICENSE` file for details (if one is added to the repository).
