Perfect, I’ll put together a high-level design (HLD) for CraicGPT.ie using AWS services to support daily comparisons of all major LLMs and image generators. This will include the website layout, AWS architecture, Terraform modular design, and key Lambda function roles. I’ll also include implementation prompt templates and generate a comic-style branding prompt in an Irish broadsheet style.

I’ll let you know when the HLD is ready for review.


# CraicGPT.ie High-Level Design

## Overview

CraicGPT.ie is envisioned as a daily **AI-generated comic newspaper** website that showcases outputs from multiple Large Language Models (LLMs) and image generators side-by-side. The site’s front-end is styled like a traditional Irish broadsheet comic page – complete with a branded banner, a mini bio of the creator, a date selector (defaulting to today), a main “article” with a headline and image, a humorous graph comparing LLMs, fake advertisement boxes, a “joke of the day” blurb, and an “LLM story of the day” section. Users can toggle between different LLM-generated texts and AI-generated images via two sets of radio buttons (one for LLM choice, one for image generator choice) to compare responses to the **same daily prompts**. All content updates daily in an automated fashion. The following sections describe the system architecture, components, and development approach for CraicGPT.ie.

## Architecture Diagram and Description

Below is a high-level architecture illustrating how daily content is generated and delivered to users. The solution uses a fully **serverless and event-driven** approach on AWS, combined with a static website for the front-end.

```
+--------------------+       +-----------------------+       +---------------------+
| EventBridge        | ----> |   Lambda Function     | ----> |  S3 Bucket          |
| (Scheduled Event)  |       |   (Content Generator) |       |  (Daily Content)    |
+--------------------+       +-----------------------+       +----------+----------+
                                                                         |
         Static Content Deployment (HTML/CSS/JS)                         | AI outputs (text, images)
+--------------------+                                        +----------v----------+
| S3 Bucket          | <-------------- CloudFront ------------+  (Content Storage)  |
| (Static Website)   |              (CDN + SSL)               +----------+----------+
+---------+----------+                                                  |
          |                                                Public/Authorized requests for 
          |                                                daily JSON & images (by date/LLM)
          |                                                            v
          |                                            +----------------------+
          |                                            |  User Browser        |
          | Initial page load (HTML, CSS, JS)          |  (craicgpt.ie)       |
          +------------------------------------------> | - selects date, LLM, |
                                                       |   image generator    |
                                                       +----------------------+
```

**Data Flow:** Every day at a preset time (e.g. midnight), an **Amazon EventBridge** scheduled rule triggers an **AWS Lambda** function responsible for content generation. This Lambda function calls out to various **LLM APIs** (for example, OpenAI GPT-4, etc.) and **image generation APIs** (e.g. DALL·E or Stable Diffusion) using predetermined prompts. The same set of prompts is fed to each target LLM and image generator to produce that day’s content. The Lambda then stores the generated outputs (texts, images, metadata) into **Amazon S3** storage, organized by date and model. According to AWS’s event-driven design, a scheduled EventBridge trigger can reliably invoke a Lambda on a daily schedule.

The website front-end is a **static site** (HTML/JS/CSS) hosted on **Amazon S3** and distributed via **Amazon CloudFront** for low-latency access and custom domain support. When a user visits craicGPT.ie, CloudFront serves the static page from S3. The page includes a date selector and radio buttons for models; by default it will load today’s date. Using client-side logic, the page then fetches that day’s content (e.g. a JSON file and images) from the S3 content storage (via CloudFront). If the user selects a different date or different LLM/image, the page dynamically loads the corresponding text or image from S3 and updates the displayed content without a full page reload. This architecture cleanly separates the **content generation pipeline** (back-end) from the **content presentation** (front-end static site).

## AWS Services Breakdown

### Amazon S3 – Static Site & Content Storage

**S3 for Static Website:** The website’s HTML, CSS, JavaScript, and other assets (e.g. logo images, style sheets) reside in an S3 bucket enabled for static website hosting (or at least configured as a CloudFront origin). S3 is a natural choice for hosting static content due to its simplicity and scalability. Since the front-end is static, it is recommended to store any rarely-changing site assets and pages in S3. This includes the newspaper-style layout HTML and any fixed images (like the banner graphic or creator’s bio photo). The S3 bucket for the site will be set to **read-only** for public access (or completely private with CloudFront Origin Access Control) to ensure the content is delivered only via CloudFront (preventing direct S3 URL access).

**S3 for Generated Content:** The daily AI-generated outputs (text and images) are also stored in S3, either in the same bucket under a designated `content/` path or in a separate bucket. Using S3 to store this dynamic-but-static content is straightforward and cost-effective for a static site. Each day’s content can be saved as a collection of objects (files) organized by date. For example, we might have a directory structure like:

* `content/2025-06-03/main_GPT4.txt` (main article text from GPT-4)
* `content/2025-06-03/main_Anthropic.txt` (main article text from another LLM)
* `content/2025-06-03/image_DALLE.png` (main image from DALL·E)
* `content/2025-06-03/image_StableDiffusion.png` (main image from Stable Diffusion)
* `content/2025-06-03/joke.txt` (joke of the day text)
* `content/2025-06-03/story.txt` (LLM story of the day text)
* `content/2025-06-03/llm_comparison.png` (image of the comparison graph for LLMs)

Alternatively, an approach is to generate a single **JSON file** per date that contains all textual content and references to image file URLs, to simplify client retrieval (one request for all content). In either case, S3’s key-value storage and ability to serve JSON or images makes it ideal. By using date-based keys or folders, the site can easily retrieve content by date (the selected date becomes part of the path or key). The S3 storage model should be chosen for simplicity unless queryable dynamic access is needed (in which case a database could be considered, though likely not necessary here). Given that our front-end is static and fetches content by known keys, **S3 is recommended over DynamoDB** – DynamoDB would only be necessary if complex queries or ultra-low latency lookups were needed, which is not the case for this use (S3 plus CloudFront can handle static content very efficiently). In short, *“if your frontend is hosted on S3, it's simplest to store your content on S3 as well”*.

### Amazon CloudFront – CDN and Domain

CloudFront sits in front of both the static site bucket and the content bucket (if separate) to distribute content globally with caching. It will be configured with the custom domain `craicGPT.ie` (and an SSL certificate via AWS Certificate Manager for HTTPS). All user requests go through CloudFront: the initial page load (HTML/CSS/JS) comes from the static site origin, and subsequent XHR requests (for JSON data or images when switching dates/LLMs) can be routed to the content origin. CloudFront can be set up with **multiple origins** and path-based routing (for example, requests to `/<static files>` go to the site bucket, and `/_content/*` or a specific path go to the content bucket). This ensures a single domain for the client. The S3 buckets can use Origin Access Identity/Control so that content is not publicly accessible except through CloudFront. CloudFront will cache the content (HTML pages, JSON, images) at edge locations, which is beneficial because although new content is added daily, each day’s content can be considered static once generated. We might set relatively long TTLs for past dates (since they won’t change) and a shorter TTL for “today’s” content if we expect to update or regenerate it on the fly (though in our case, content is generated once per day and not modified afterward). Using CloudFront also improves security (hiding S3 direct URLs) and performance for our static site.

### AWS Lambda – Content Generation Functions

At the heart of the back-end are the AWS Lambda functions that handle **AI content generation**. These will be written in TypeScript (running on Node.js runtime in Lambda). We will likely implement multiple Lambda functions or a single Lambda with multiple steps, depending on the design preference:

* **Main Content Generator Lambda:** This function is triggered daily by EventBridge. It orchestrates the process of generating all necessary content for the day. The Lambda will use API calls to external AI services (e.g., OpenAI, etc.) for: 1) generating the main article text from each LLM, 2) generating the main image from each image generator given the same prompt, and 3) generating any additional pieces (e.g., “joke of the day”, “interesting LLM story of the day”, and possibly the data for the comparison graph or a caption). The logic can be structured to iterate through a list of LLMs and image APIs configured (e.g., an array of LLM endpoints to hit with the prompt) and similarly for images. Each result is collected and then stored to S3. For storing, the Lambda will use the AWS SDK to `PutObject` the results into the content S3 bucket (or prefix). For example, after getting a response from GPT-4, it will save the text to `content/{date}/main_GPT4.txt`. It will also save the image bytes from an image API response to an S3 key like `content/{date}/image_DALLE.png`. The Lambda needs appropriate IAM permissions to write to the S3 bucket (an IAM policy allowing `s3:PutObject` on the designated bucket/path).

* **Modular Lambdas (alternative):** In a more modular approach, we could use **multiple Lambda functions** for different tasks. For example, one Lambda could handle *text generation* (calling all LLMs), another Lambda could handle *image generation* (calling all image APIs), and perhaps separate ones for generating the joke and story. These could be orchestrated via an AWS Step Functions workflow or triggered in sequence using EventBridge events. However, given the scope (a handful of API calls), a single Lambda that sequentially calls all required APIs (or even does some in parallel using `Promise.all` in Node.js) is simpler for an MVP. As the application grows, one could refactor to multiple functions (for example, if using different API keys or if one type of generation significantly slows down the others, separating might help scale them independently).

Each Lambda invocation is **triggered once daily** by the scheduler, and it will produce that day’s content. The content is then immediately available in S3 for the front-end to use. Using EventBridge Scheduler to invoke a Lambda on a schedule is a reliable method for daily jobs, and it eliminates the need for any server or cron management.

**Graph Generation:** The site includes an “article” with a graph comparing top LLMs of the day. This could be handled in a few ways. One approach is to generate an **image** of a graph as part of the Lambda’s work – for example, using a library (or an API like QuickChart) to create a chart (perhaps comparing some metrics of the LLM outputs like length, sentiment, or a fun rating) and saving that graph image to S3. Another creative approach is to prompt an image generator to *“draw a comic-style chart comparing X and Y”* and use that result. For MVP, a simple bar chart of LLM names could even be hard-coded or based on a trivial metric (like token count) just to fulfill the comic comparison concept. The Lambda could also store some numeric data in a JSON for the front-end to render a chart via JavaScript (using Chart.js or similar) rather than an image. The simplest path is likely generating a static chart image or static HTML snippet for the graph article and storing it. This ensures the front-end remains static.

**Joke and Story Generation:** The Lambda will use additional prompts for the daily joke and the interesting LLM-related story. For example, the prompt template for the joke might be *“Tell a short funny joke of the day about \[some topic]”* and for the story *“Give a short newsy story or anecdote about AI or LLMs for today”*. These outputs (text, possibly with a title or author line) are saved to S3 (e.g., as `joke.txt`, `story.txt`). We might designate one primary LLM (say GPT-4 or whichever is deemed best at humor) to generate these sections, rather than generating them from every LLM. The reason is that these sections are presented as single articles, not toggleable by model. However, one could also generate them with multiple LLMs and pick the best, or even show comparisons (“Here’s how GPT-4’s joke vs another model’s joke”). For now, we assume one final version of each is stored for display.

### Amazon EventBridge – Scheduler

EventBridge (Scheduler) is configured to fire an event every day at a specific time (e.g., 00:01 Irish time, or whatever time fits the “daily edition”). This event triggers the content generation Lambda(s). EventBridge’s scheduling service is highly scalable and can reliably handle daily (or even more frequent) scheduled tasks without dedicated servers. We will create an EventBridge Rule of type Schedule (cron expression or rate 1 day) with the Lambda function as the target. The Lambda’s IAM role must allow EventBridge to invoke it, and when we define the EventBridge rule we specify the Lambda ARN as the target (AWS will handle granting invoke permissions automatically or we attach a policy). In case multiple Lambdas are used (for separate text/image generation), we could either have multiple scheduled rules (each calling a different Lambda) or one rule invoking a main Lambda that then internally invokes others or spawns parallel processes. For simplicity, one rule -> one Lambda is the initial design.

It’s worth noting that this architecture is **event-driven**; no servers run continuously. The Lambda only runs when triggered daily, and the front-end is static. This is cost-efficient and scalable, as AWS will only charge for the brief Lambda execution time and S3/CloudFront usage.

### AWS IAM – Roles and Permissions

Several IAM roles/policies are needed for security and proper access control:

* **Lambda Execution Role:** The Lambda(s) will run with an IAM role that grants permission to the necessary resources. At minimum, it needs permission to write to the content S3 bucket (`s3:PutObject`, and possibly `s3:GetObject` if the Lambda should read existing files). If the Lambda calls external APIs (OpenAI, etc.), it will need internet access – which means it either should be in a public subnet or use AWS NAT Gateway; however, since this is a simple setup, we can run the Lambda in no VPC (default), giving it internet by default. No special IAM permissions are needed for calling external web APIs. If secrets (API keys) are stored in AWS Secrets Manager or SSM Parameter Store, the Lambda role would also need permission to read those.

* **EventBridge Invoke Permissions:** When an EventBridge rule targets a Lambda, AWS typically handles the invocation permission (adding a resource-based policy on the Lambda that allows the EventBridge service to invoke it). In Terraform, one might need to explicitly allow the rule to invoke the Lambda. This is a standard setup.

* **CloudFront Access to S3:** If using an Origin Access Identity or Origin Access Control for CloudFront to fetch S3 content, then the S3 bucket policy must trust the CloudFront OAI/OAC. This means an IAM-like policy on the bucket allowing `s3:GetObject` for the CloudFront principal. This is configured when setting up CloudFront. It ensures that S3 objects can’t be fetched by arbitrary users, only by CloudFront on behalf of end-users.

* **Least Privilege:** All IAM policies should follow least privilege. For example, the Lambda’s S3 write permission can be restricted to only the specific bucket (and even specific prefix if desired). If DynamoDB or other services were used, those would be similarly locked down. Terraform will manage these roles and policies as code.

### (Optional) Amazon API Gateway

In this design, **API Gateway is not strictly required** because the static site can fetch content directly from S3/CloudFront. The browser can request a JSON file or image from a CloudFront URL, and that content comes straight from S3. This is a perfectly valid approach for static sites, and avoids the complexity of setting up an API layer. However, if we wanted to introduce an API (for example, to combine data or perform on-the-fly processing), we could add Amazon API Gateway + Lambda as a read-API. For instance, an API Gateway endpoint like `/getContent?date=2025-06-03` could trigger a Lambda that fetches the various S3 objects for that date and returns a consolidated JSON. This might simplify client logic (only one fetch to an endpoint). The trade-off is higher complexity and cost (API Gateway and an extra Lambda invocation on each page load). For an MVP that emphasizes simplicity, it’s recommended to stick with direct S3 content serving. Should the project evolve (e.g., requiring user-specific content or non-public data), an API Gateway could be added then.

## Content Storage Model Considerations

As mentioned, storing daily generated content in S3 is the simplest model. Within S3, **organization by date** is key. Each day’s edition can live in its own folder or have the date as a filename prefix. This makes it easy to list available dates and to retrieve a specific day’s files. For example, on the front-end the date selector could correspond to a path like `/content/2025-06-03/`.

We have a few options in how to structure the actual content files:

* **Discrete files per content piece:** Store each logical piece in a separate file (as illustrated earlier: separate files for each LLM’s main article, separate image files, etc.). This is straightforward and mirrors how a traditional newspaper might have separate assets. The front-end will just issue multiple requests (which is fine especially if they’re small and cached).

* **Bundle by type:** Alternatively, store one JSON for all LLM texts of the main article, one JSON for all other text pieces, etc. For example `main_articles_2025-06-03.json` could contain `{ "GPT4": "text...", "ModelB": "text..." }`. And maybe a `misc_articles_2025-06-03.json` containing the joke and story. This reduces the number of requests but requires more parsing.

* **Single JSON bundle:** As noted, we could store everything in one JSON file per day. This JSON might look like:

  ```json
  {
    "date": "2025-06-03",
    "headline": "Funny Headline of the Day",
    "mainArticle": {
      "GPT-4": "<p>Article text from GPT-4...</p>",
      "ModelB": "<p>Article text from Model B...</p>",
      "...": "... other models ..."
    },
    "joke": {
      "title": "Joke of the Day",
      "text": "LLM-generated joke text..."
    },
    "story": {
      "title": "AI News of the Day",
      "text": "LLM-generated short story..."
    },
    "graphData": {
      "imageUrl": "content/2025-06-03/llm_comparison.png",
      "caption": "Which LLM was the wittiest?"
    },
    "ads": [
      { "imageUrl": "content/common/fake_ad1.png", "alt": "Ad 1", "link": "#" },
      ... (4 more ads)
    ]
  }
  ```

  And image files (like the main image from each generator, the graph, and any ad images) would be stored separately as PNG/JPEG files. The JSON approach is nice for atomic retrieval. Since this is a static site, we might lean on simpler approaches to avoid needing to generate a combined JSON on the fly. But our Lambda can certainly compose and upload such a JSON after gathering all pieces, which the front-end could fetch in one go.

In summary, **the recommended model is to use Amazon S3 as an object store for all daily content**, with a clear naming convention for keys. This keeps things simple and leverages S3’s strengths for static hosting. DynamoDB or other databases are not necessary unless we plan to add more dynamic queries or metadata search (for example, “find me all days where Model X was funniest” – out of scope for now). If needed, one could later add a DynamoDB table indexing some stats or allowing content search, but MVP does not demand it.

## Infrastructure as Code (Terraform)

All the infrastructure and deployment configurations will be managed via **Terraform** (using HCL). The project repository (GitHub: `github.com/allthingsclowd/craicgpt.ie`) will contain the Terraform code alongside any application code (like Lambda source, website code). Using Terraform ensures the AWS resources can be easily created, updated, and version-controlled. We will adhere to modular best practices in Terraform to keep the configuration clean and reusable. Specifically, we will create **Terraform modules** to encapsulate different components of the architecture, and then a root module to wire them together. This modular approach is recommended for clarity and reuse.

A possible Terraform project structure could be:

```
/terraform
   ├─ main.tf            # root module calling submodules for the whole infrastructure
   ├─ variables.tf       # any global variables for root (like domain name, etc.)
   ├─ outputs.tf         # outputs from root module (like CloudFront URL)
   └─ modules/
         ├─ static_site/
         │    ├─ main.tf        # S3 bucket, CloudFront distribution, DNS, ACM
         │    ├─ variables.tf   # inputs like bucket name, domain, cert ARN, etc.
         │    └─ outputs.tf     # outputs like bucket ARN, CloudFront domain
         ├─ content_pipeline/
         │    ├─ main.tf        # Lambda function(s), EventBridge rule, IAM roles
         │    ├─ variables.tf   # inputs like bucket name for content, schedule cron, etc.
         │    └─ outputs.tf     # outputs like Lambda ARNs
         └─ network/ (optional if needed, e.g., VPC for Lambda – likely not needed)
```

In this setup, the **static\_site module** would handle creating the S3 bucket for the website, configuring it (possibly as a website endpoint if not using OAC, though with CloudFront we’ll use the REST endpoint with OAC), creating the CloudFront distribution (with an OAC/OAI and bucket policy attachment), and possibly setting up Route53 DNS records for the `craicgpt.ie` domain and requesting an ACM certificate for TLS. This keeps all front-end related infra together.

The **content\_pipeline module** would create the content S3 bucket (if separate) and the Lambdas, their IAM roles, and the EventBridge scheduler rule. For the Lambdas, Terraform can bundle the TypeScript code. We may structure the Lambda code in a subdirectory and use Terraform’s `aws_lambda_function` resource with either inline code (for very small funcs) or, more practically, pointing to a ZIP file (which could be created by a build script or CI pipeline). The module would also include any needed IAM policies (for S3 write, etc.) and the EventBridge Rule + Target linking to the Lambda (with a `schedule_expression` like `cron(0 0 * * ? *)` for every midnight UTC, for example). If multiple Lambda functions are used (e.g., `textGenerator` and `imageGenerator`), each can be a separate resource with its own schedule or invoked by the main one. This module keeps the back-end logic isolated from the front-end infra.

Terraform best practices such as using **remote state** (to persist state securely), pinning provider and module versions, and organizing config by environment may also be applied. For instance, if we plan to have dev/staging environments, we could use Terraform workspaces or separate state files. Tagging resources appropriately (Project: CraicGPT.ie, Environment: prod, etc.) is also a good practice. The code repository can include a CI/CD pipeline (GitHub Actions or similar) to automatically apply Terraform changes on push, but initially manual `terraform apply` might suffice.

By modularizing, each piece (static site, content generation, etc.) can be developed and tested somewhat independently and even open-sourced if useful. As noted in community best practices: *“Use simple wrapper root modules and lots of submodules. Don't nest too deeply, though – typically 3 levels is plenty.”* This structure aligns with that advice by having a thin root that calls two second-level modules, each of which groups related resources.

Finally, Terraform will also manage any configuration that ties pieces together, such as passing the content bucket name to the Lambda (so the Lambda knows where to save files, likely via an environment variable set in Terraform). The Lambda’s code (TypeScript) will be deployed either by Terraform (zipping and uploading) or by a CI pipeline. Since the question specifically mentions Terraform deployment, we might use the Terraform AWS provider to upload the Lambda package to S3 and deploy, or use the Terraform **archive\_file** utility to zip code from a local directory. We will ensure the Terraform code is organized and documented, possibly providing a `README.md` in the repo to guide how to use the modules.

## Front-End Framework for MVP

For the initial implementation (MVP), a **lightweight static site framework** or simple HTML/JS approach is recommended. Two options stand out:

* **Astro**: Astro is a modern static site builder that emphasizes content-focused sites with great performance. It uses the concept of **Islands Architecture** where most of the page is pre-rendered static HTML, and only small interactive components hydrate on the client. This is ideal for CraicGPT.ie because the bulk of the page (articles, text, images) can be delivered as static content, and only the interactive controls (date picker and radio buttons) need a bit of client-side scripting. Astro would allow us to build the newspaper-style layout using components (which could make it easier to manage the repeated structure of article boxes, ads, etc.), and we can integrate vanilla JS or lightweight framework components for the interactive parts. Astro also makes it easy to integrate with an eventual Angular component if needed, but since Angular is heavier, we likely treat the MVP as a throwaway or prototype and later rewrite in Angular if desired.

* **Vanilla JS / HTML + CSS**: Given the requirements, one could even build this page with plain HTML and CSS (possibly using a CSS framework for grid or newspaper column layout) and a sprinkle of JavaScript for the dynamic content swapping. The radio button groups can have an `onchange` event that triggers a fetch to S3 for the selected content file and then updates the DOM. A date picker (could be an `<input type="date">` or a dropdown of available dates) can similarly trigger content loading. This approach has zero build tooling and can be done quickly. The downside is maintainability if the layout grows complex – but since it’s mostly a static layout, that might be fine.

For style, we’ll create custom CSS to mimic a **newspaper comic aesthetic** – likely using a serif font for headlines, maybe slightly yellowed background or printed-paper look, and including comic-style imagery. We can incorporate some fun elements like drop caps in the main article, or stylized borders around ads. Astro would let us use any CSS or even CSS-in-JS if desired; with plain HTML we’d just include a stylesheet.

A potential approach is to start with a simple static HTML+CSS prototype (to nail the design and layout), then migrate that into Astro components for better structure. Astro also allows easily pulling in JSON content at build time or runtime. However, since our content is dynamic per day and we don't want to rebuild the site daily (we prefer the site to fetch fresh content at runtime), we will treat the content as external data. In Astro, we could use client-side scripts or Astro’s partial hydration to fetch the data on the client side after the page loads. This is similar to what we’d do in plain JS anyway.

In summary, **for MVP speed and simplicity, a static site with minimal JS is best**. Astro is a good candidate because it produces very optimized static output and would allow an easier transition to a more interactive framework later. The choice might also depend on the developer’s familiarity – if the team knows Angular well, they might be tempted to use it from the start, but it’s arguably overkill for this read-only comparison site and would increase time to market. Starting lightweight will let us iterate on the design and content quickly.

## Example Prompts for AI Generation and Code (Follow-up)

To illustrate and assist with subsequent development steps, here are some example **prompts** (for image generation and for code generation via AI) that align with this project:

### Prompt for CraicGPT.ie Branding Banner Image

*(This prompt can be used with an image generator like DALL·E or Stable Diffusion to create a logo/banner in an Irish comic newspaper style.)*

**Prompt:** *“Design a **newspaper banner** for **CraicGPT.ie** in a quirky Irish comic style. The banner should look like the title of an Irish broadsheet newspaper but with a fun twist: include Irish-themed comic elements (like a little leprechaun or shamrock character) and bold, old-style newspaper fonts. It should feel vintage yet humorous. The text ‘CraicGPT.ie’ must be prominent, styled like a newspaper masthead, with perhaps a subtitle in smaller text ‘AI Daily Craic’. Use a color palette and illustration style reminiscent of classic Irish newspaper comics.”*

This prompt aims to yield a wide image suitable for the top-left corner banner that captures the Irish humor and comic aesthetic. The result might be an illustrated title with perhaps hand-drawn lettering and a mascot, fitting the tone of the site.

### Prompt Template: Terraform Module Scaffolding

*(Use this prompt with an AI code assistant to generate an initial Terraform module structure.)*

**Prompt:** *“You are a DevOps engineer. Generate a **Terraform module scaffolding** for an AWS infrastructure to host a static website with daily content generation. The module should include: an **S3 bucket** for static site hosting, an **Amazon CloudFront distribution** (with an OAI or OAC) to serve the site on a custom domain with HTTPS, and outputs for the CloudFront domain. Use Terraform best practices (variables.tf for inputs like bucket name and domain, outputs.tf for outputs, etc.). Provide the contents of `main.tf`, `variables.tf`, and `outputs.tf` with placeholders or example values, well-commented.”*

This prompt will help create a baseline for the static site Terraform module. We would adapt it by adding modules or resources for Lambda and EventBridge in a separate module similarly.

### Prompt Template: Website HTML Structure (Newspaper Layout)

*(Use this prompt to get a starter HTML/CSS or Astro component layout.)*

**Prompt:** *“Create a basic **HTML structure** (with some CSS) for a webpage that looks like a single page of a broadsheet newspaper comic. Include: a top banner section for the title logo, a top-right sidebar for an author bio with a small image, a date selector input, and radio buttons to switch between AI models and image generators. Below, layout a main article section with a headline and an image, a sub-article with a graph (you can use a placeholder image for the graph), a section for a ‘Joke of the Day’, and another for an ‘LLM Story of the Day’. Also include five small boxes that could contain fake ads (they can be placeholders for now). Use appropriate semantic HTML (e.g., <header>, <aside>, <section>, etc.) and minimal CSS to achieve a newspaper column look (maybe two-column layout for some sections, etc.). Make sure the layout is responsive enough for web. Provide the HTML and CSS inline (you can use simple <style> for CSS).”*

This prompt will yield an initial front-end layout that we can then refine. If using Astro, we could adjust the prompt to: “Provide an Astro component or page with ...” The key is it helps scaffold the structure.

### Prompt Template: AWS Lambda (TypeScript) for LLM API Call

*(Use this prompt to get a sample Lambda function code for text generation.)*

**Prompt:** *“Write a **TypeScript AWS Lambda function** that calls an external AI API (e.g., OpenAI ChatGPT) to generate text and saves the result to an S3 bucket. The Lambda will be triggered by an event containing a `prompt`. It should read an environment variable for the target S3 bucket name and an API key for OpenAI. Use the OpenAI Node.js library or an HTTP fetch to call the ChatGPT API with the given prompt. Then, take the response text and upload it to S3 as an object (key can be `output.txt`). Include proper error handling and logging. Provide the TypeScript code for the lambda handler.”*

This prompt should produce an example Lambda handler code. We expect the code to show using `openai` package or `axios/fetch` to call the API, then `S3Client` (from AWS SDK v3) to put an object. We’ll adapt it to our specific prompts and keys, but it serves as a template.

### Prompt Template: AWS Lambda (TypeScript) for Image Generation API

*(Use this prompt for a lambda that generates an image and stores it.)*

**Prompt:** *“Write a **TypeScript AWS Lambda function** that generates an image using an AI image API and stores it in S3. The function should be triggered with an event containing an `imagePrompt`. It should call an image generation API (for example, DALL·E or Stable Diffusion via a REST API) using an API key (from env variable). Once it gets the image (for instance, as a binary or base64), it should save the image file to an S3 bucket (bucket name from env var, key can be `output.png`). Show how to convert a base64 response to binary for S3 upload if needed. Include error handling and use the AWS SDK to put the object. Provide the code for the handler function in TypeScript.”*

This will yield a code example demonstrating image API call and S3 upload. We’d adjust the specifics (URL, request format) to whichever service we use (for example, OpenAI’s image API or others).

---

By following the above design and utilizing these prompt templates, CraicGPT.ie can be implemented in a structured, maintainable way. The result will be a unique and entertaining site that automatically publishes an “AI newspaper” every day, showcasing the differences and capabilities of various AI models in a fun, Irish-themed comic format. With the high-level architecture in place, the next steps are to implement the Terraform modules, Lambda functions, and front-end layout, using the prompts and guidelines to accelerate development. Good luck, and have fun – or as one might say in Ireland, **“great craic”** is ahead!

