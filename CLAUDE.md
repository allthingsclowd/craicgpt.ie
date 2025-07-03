# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

### Build and Package
```bash
# Build TypeScript
npm run build

# Package for deployment
npm run package
```

### Testing
Currently no test framework is configured. Tests are manual through Lambda invocations.

### Linting
No linting configuration found. Consider adding ESLint or similar.

## Architecture Overview

CraicGPT.ie is an AI-powered newspaper generation system with a serverless architecture designed for educational purposes:

**Frontend**: Static HTML/CSS/JS newspaper layout hosted on AWS S3 + CloudFront
**Backend**: 4 AWS Lambda functions orchestrating content generation

### Educational Phase 0 - Multi-Provider Support

The system now supports multiple AI model providers for learning different API patterns:

- **AWS Bedrock** (current): Claude, Titan Text/Image, Nova Canvas
- **OpenAI** (new): GPT-4, O3 Mini, DALL-E 3
- **Anthropic Direct** (new): Claude 3.5 Sonnet with vision
- **Google Gemini** (new): Gemini Pro, Gemini Pro Vision, Gemini Ultra

### Lambda Function Pipeline

1. **Educational Prompt Generator** (`lambda_code/PromptGenerator/lambda_function_v2.py`)
   - **NEW**: Clear educational structure with explicit prompt engineering parameters
   - **NEW**: Component-based prompt building showing influence relationships
   - **NEW**: Multi-provider model configurations
   - Generates 13 prompts daily (5 LLM + 8 image) with clear temperature, max_tokens, top_p settings
   - **Educational Features**: 
     - Explicit prompt engineering parameters (temperature: 0.2-0.9, max_tokens, top_p)
     - Component influence documentation (weather → mood, news → content hijacking)
     - Provider-specific authentication patterns

2. **Orchestrator** (`lambda_code/orchestrator/`)
   - Coordinates workflow and manages dependencies
   - Handles date ranges and model-specific rate limiting
   - Implements sophisticated concurrency control using CloudWatch metrics
   - LLM processing completes before image processing per date

3. **Educational Model Runner** (`lambda_code/shared/educational_runner.py`)
   - **NEW**: Unified interface for all model providers
   - **NEW**: Educational error handling and response standardization
   - **NEW**: Clear API pattern demonstrations for each provider
   - Supports AWS Bedrock, OpenAI, Anthropic Direct, Google Gemini
   - **Educational Features**: 
     - Standardized ModelResponse class across all providers
     - Provider-specific authentication examples
     - API pattern documentation in responses

4. **Model Configurations** (`lambda_code/shared/model_configurations.py`)
   - **NEW**: Centralized model configuration with educational annotations
   - **NEW**: Prompt engineering parameter explanations
   - **NEW**: Provider comparison and use case documentation
   - **Educational Features**: 
     - Parameter validation and educational notes
     - Use case recommendations per model
     - API endpoint and authentication documentation

### Key Dependencies

- **Phase Dependencies**: LLM processing must complete before image processing for each date
- **Concurrency Management**: Real-time Lambda concurrency monitoring via CloudWatch
- **Rate Limiting**: Model-specific throttling with exponential backoff
- **Storage**: S3 for prompt storage and content output

### Environment Variables (Orchestrator)

Critical configuration for concurrency control:
- `MAX_ACCOUNT_CONCURRENT`: Account-wide Lambda limit (default: 9)
- `CONCURRENCY_CHECK_ENABLED`: Enable real-time monitoring (default: true)
- `CONCURRENCY_BACKOFF_DELAY`: Wait time at limit (default: 30s)
- `CLOUDWATCH_REGION`: CloudWatch API region (default: eu-west-1)

## Deployment Status

**Frontend**: Fully automated via Terraform (`terraform/frontend/`)
**Backend**: Manual deployment required (Terraform boilerplate exists in `terraform/backend/`)

## Content Generation Process

1. **Prompt Generation**: Creates date-specific prompts with news context
2. **Orchestration**: Manages worker Lambda invocations with dependency awareness
3. **Content Generation**: Parallel LLM and image processing with rate limiting
4. **Output**: JSON files stored in S3, consumed by frontend

## Educational Prompt Engineering Patterns

### Explicit Parameter Configuration

Each prompt template now shows clear prompt engineering parameters:

```python
# Educational example from lambda_function_v2.py
main_article = PromptTemplate(
    temperature=0.9,        # High creativity for diary entries
    max_tokens=800,         # Long enough for full article
    top_p=0.95,            # High diversity for creative expression
    presence_penalty=0.1,   # Light penalty to avoid repetition
    frequency_penalty=0.1   # Light penalty for natural variation
)
```

### Component Influence Mapping

Clear documentation of how components influence outputs:

- **Weather Context** → Natural opening material and mood setting
- **News Headlines** → Material for "headline hijacking" to connect news to personal life  
- **Family Context** → Content for "family follies" section
- **Tech Trends** → Work-related anecdotes and technical context

### Provider-Specific Patterns

Educational examples for each provider:

- **AWS Bedrock**: IAM authentication, InvokeModel API, JSON request/response
- **OpenAI**: Bearer token auth, Chat Completions API, messages format
- **Anthropic**: x-api-key header, Messages API, direct feature access
- **Google Gemini**: API key parameter, GenerateContent API, parts array

## Common Patterns

- **Error Handling**: Exponential backoff for throttling, graceful degradation
- **Monitoring**: CloudWatch integration for real-time metrics
- **Configuration**: Environment variables for runtime behavior  
- **Idempotency**: Skip processing if output already exists
- **Resilience**: Comprehensive retry logic with timeout protection
- **Educational Logging**: Detailed logs showing parameter choices and component influences

## Development Notes

- All Lambda functions use Python 3.11+
- **NEW**: Multi-provider support (AWS Bedrock, OpenAI, Anthropic, Gemini)
- **NEW**: Educational structure with explicit parameter documentation
- **NEW**: Component-based prompt building for clear learning
- No testing framework - consider adding pytest
- Manual deployment process for backend infrastructure
- Frontend uses modern JavaScript with responsive CSS Grid layout

## Phase 1 Migration Path

The educational Phase 0 structure prepares for Phase 1 agentic migration:

- Current: Manual prompt templates with explicit parameters
- Phase 1: AI agents that reason about prompt construction
- Learning bridge: Understanding parameters → Teaching agents to use them
- Component system → Agent tool selection patterns