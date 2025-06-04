# craicgpt.ie
AI designed &amp; built AI agentic website 

This all starts with Gemini & ChatGPT 'Research' following a basic prompt, response outputs can be seen in the respective folders [ChatGPT](chatgpt-4.5Research) & [Gemini](gemini2.5Pro)

I started with what I though would be the fun and 'easy' part to generate the branding image trying the same two AI engines. It took 3 hours of back and forth where I eventually gave up and settled on this image for the website banner - AI is great when given a blank canvas and a description, it has no issues with copyright either as it's very clear what it's influences were for cartoon style, I mentioned Viz and Beano ;) However, when trying to tweak and tune the provided images it was painful to the point where I was considering using paint or preview to make what I considered trivial changes. Learnings here are general LLMs are not good for image modification - I will explore image generation AI tooling at another time. We are focused on ideation, creation and coding at present!

![CraicGPT.ie](images/WebsiteBrandingChatGPT.png)

## Terraform Infrastructure

This directory (`terraform/`) contains the Terraform configuration for provisioning and managing the AWS infrastructure that powers the CraicGPT.ie application.

### Purpose

The Terraform code automates the setup of all necessary cloud resources, ensuring a consistent, repeatable, and version-controlled infrastructure. This setup is designed to host a serverless web application with scheduled content updates.

### Services Provisioned

The configuration provisions the following key AWS services:

*   **AWS S3 (Simple Storage Service):** Used to store static website assets (HTML, CSS, JavaScript, images) and generated content.
*   **AWS CloudFront:** Acts as the Content Delivery Network (CDN) to distribute the website globally, providing low-latency access and HTTPS termination. It uses Origin Access Control (OAC) to securely serve content from the S3 bucket.
*   **AWS Lambda:** Hosts the `ContentOrchestratorLambda` function, responsible for backend logic, such as orchestrating daily content generation.
*   **AWS ACM (Certificate Manager):** Manages the SSL/TLS certificate required for HTTPS on the custom domain (`craicgpt.ie`). Certificates are provisioned in `us-east-1` as required by CloudFront.
*   **AWS EventBridge Scheduler:** Triggers the `ContentOrchestratorLambda` function on a daily schedule (currently set to 01:00 UTC) to perform automated tasks.
*   **AWS IAM (Identity and Access Management):** Defines necessary roles and policies for services to interact securely (e.g., Lambda permissions to access S3 and Secrets Manager, Scheduler permissions to invoke Lambda).
*   **AWS Route 53 (Implied):** While not directly managed for record creation in these primary files (except for ACM validation records), it's assumed that the DNS hosted zone for `craicgpt.ie` exists in Route 53 for the ACM certificate validation and CloudFront alias records to function.

### Architecture Overview

1.  **Static Content Hosting:** The S3 bucket (`craicgpt-website-assets`) stores all website files.
2.  **Content Delivery:** CloudFront serves these files from S3. It's configured with custom cache policies for different content types (static assets vs. daily generated content) and uses an ACM certificate for HTTPS.
3.  **Dynamic Content Orchestration:** The `ContentOrchestratorLambda` (Node.js 18.x runtime) is triggered daily by an EventBridge Scheduler rule. This Lambda is expected to generate or update content and place it into the `/content/` path in the S3 bucket. It has permissions to write to S3 and read API keys from AWS Secrets Manager (for LLM and Image Generation services).
4.  **Security:**
    *   CloudFront uses OAC to ensure the S3 bucket is not publicly accessible.
    *   Lambda execution roles are scoped with least-privilege permissions.
    *   Secrets for external APIs are stored in AWS Secrets Manager and accessed by the Lambda function.
5.  **DNS & SSL:** ACM provides the SSL certificate, validated using DNS records in Route 53. CloudFront uses this certificate.

### Usage

To deploy or update the infrastructure:

1.  **Prerequisites:**
    *   Install Terraform (see [Terraform official website](https://www.terraform.io/downloads.html)).
    *   Configure AWS credentials locally (e.g., via AWS CLI, environment variables, or IAM instance profiles). Ensure these credentials have sufficient permissions to create the resources defined.
    *   Ensure the domain `craicgpt.ie` has a hosted zone in AWS Route 53 in the same AWS account.
    *   Populate the necessary variables. You can create a `terraform.tfvars` file in the `terraform/` directory or provide variables via command-line flags. Key variables to set include:
        *   `aws_region`: The primary AWS region for deployment (e.g., "eu-west-1").
        *   `cloudfront_aliases`: List of domain names for CloudFront (e.g., `["craicgpt.ie", "www.craicgpt.ie"]`).
        *   `llm_api_key_secret_arn`: ARN of the Secrets Manager secret for the LLM API key.
        *   `image_gen_api_key_secret_arn`: ARN of the Secrets Manager secret for the ImageGen API key.

2.  **Navigate to the Terraform directory:**
    ```bash
    cd terraform
    ```

3.  **Initialize Terraform:**
    This downloads the necessary provider plugins.
    ```bash
    terraform init
    ```

4.  **Plan the changes:**
    This shows you what Terraform will create, modify, or destroy.
    ```bash
    terraform plan
    ```
    If using a `.tfvars` file, it will be picked up automatically. Otherwise, you can specify variables:
    ```bash
    terraform plan -var="aws_region=eu-west-1" -var='cloudfront_aliases=["craicgpt.ie","www.craicgpt.ie"]' ...
    ```

5.  **Apply the changes:**
    This provisions the resources in AWS.
    ```bash
    terraform apply
    ```
    Confirm by typing `yes` when prompted.
    To auto-approve (use with caution):
    ```bash
    terraform apply -auto-approve
    ```

6.  **Inspect Outputs:**
    After a successful apply, you can view defined outputs:
    ```bash
    terraform output
    ```

7.  **Destroy Infrastructure (if needed):**
    To remove all resources managed by this Terraform configuration:
    ```bash
    terraform destroy
    ```
    Confirm by typing `yes` when prompted.
