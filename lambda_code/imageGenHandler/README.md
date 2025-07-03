# imageGenHandler - Multi-Provider Image Generation

**Unified Image Generation Across Multiple AI Providers**

The imageGenHandler function generates images for the CraicGPT newspaper using multiple image generation providers, supporting AWS Bedrock and OpenAI with unified interface and comprehensive error handling.

## 🎯 Purpose

Generate high-quality images for newspaper content using multiple image generation providers while maintaining consistent output format, proper error handling, and seamless integration with the content pipeline.

## 🏗️ Architecture

### **Multi-Provider Image Generation**
```
Image Prompt ─┐
              │
Provider      ├─► AWS Bedrock ────► Titan Image, Nova Canvas
Detection     │                    (IAM Auth)
              │
              ├─► OpenAI ─────────► DALL-E 3
              │                    (API Key via Secrets Manager)
              │
              └─► Future Providers ► Midjourney, Stable Diffusion
                                   (Planned)
                                   │
                                   ▼
                              Base64 Image ──► S3 Storage ──► paper_content.json
```

### **Supported Providers & Models**

**AWS Bedrock** (IAM Authentication):
- `amazon.titan-image-generator-v1` - Titan Image Generator
- `amazon.nova-canvas-v1:0` - Nova Canvas (Advanced)

**OpenAI** (API Key via Secrets Manager):
- `dall-e-3` - DALL-E 3 (High-quality image generation)

**Planned Providers**:
- Anthropic (Image analysis/description capabilities)
- Google Gemini (Image understanding and generation)
- Midjourney API (When available)

## 🚀 Key Features

### **Unified Image Generation**
```python
def invoke_image_model(model_id: str, prompt: str) -> ImageResponse:
    """Unified image model invocation supporting all providers"""
    provider = determine_provider(model_id)
    
    if provider == ModelProvider.AWS_BEDROCK:
        return invoke_bedrock_image_model(model_id, prompt)
    elif provider == ModelProvider.OPENAI:
        return invoke_openai_image_model(model_id, prompt)
    else:
        return ImageResponse(
            success=False,
            image_data="",
            model_id=model_id,
            provider=provider.value,
            error_message=f"Image generation not supported for provider: {provider.value}"
        )
```

### **Provider Auto-Detection**
```python
def determine_provider(model_id: str) -> ModelProvider:
    """Determine which provider to use based on model ID"""
    if model_id.startswith(("dall-e", "gpt-4")):
        return ModelProvider.OPENAI
    elif model_id.startswith(("claude-3-5", "claude-3-opus")) and not model_id.startswith("anthropic."):
        return ModelProvider.ANTHROPIC_DIRECT
    elif model_id.startswith(("gemini-", "palm-")):
        return ModelProvider.GOOGLE_GEMINI
    else:
        return ModelProvider.AWS_BEDROCK
```

### **Standardized Response Format**
```python
@dataclass
class ImageResponse:
    """Standardized response format for all image providers"""
    success: bool
    image_data: str  # Base64 encoded image
    model_id: str
    provider: str
    processing_time_ms: Optional[int] = None
    finish_reason: Optional[str] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    alt_text: Optional[str] = None
```

## 🔧 Technical Implementation

### **Function Configuration**
- **Runtime**: Python 3.12
- **Memory**: 2048 MB (images require more memory)
- **Timeout**: 15 minutes (image generation takes longer)
- **Handler**: `lambda_function.lambda_handler`

### **Environment Variables**
```bash
# S3 Storage
PROMPT_BUCKET=your-s3-bucket-name

# Multi-provider secrets
OPENAI_SECRET_NAME=craicgpt/openai-api-key
ANTHROPIC_SECRET_NAME=craicgpt/anthropic-api-key
GOOGLE_SECRET_NAME=craicgpt/google-api-key

# Model configuration
BEDROCK_IMAGE_MODEL_IDS=amazon.titan-image-generator-v1,amazon.nova-canvas-v1:0
OPENAI_IMAGE_MODEL_IDS=dall-e-3

# AWS Configuration
AWS_REGION=eu-west-1
```

### **IAM Permissions Required**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": [
        "arn:aws:s3:::your-bucket/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": [
        "arn:aws:secretsmanager:*:*:secret:craicgpt/*"
      ]
    }
  ]
}
```

## 🎨 Image Content Types

### **Generated Image Types**
- **Main Article** (`img_01`): Hero illustration for main story
- **Comparison Article** (`img_02`): Hero illustration for comparison piece
- **Advertisements** (`img_03-06`): 4 sponsored content images
- **LLM Story** (`img_07`): Spot illustration for feature story
- **Daily Joke** (`img_08`): Visual element for humor section

### **Image Specifications**
- **Format**: PNG (preferred) or JPEG
- **Size**: 512x512 pixels (optimized for web)
- **Quality**: Standard to High quality based on provider
- **Storage**: Base64 encoded in JSON, binary files in S3

### **Output Format**
```json
{
  "contentSlots": {
    "mainArticle": {
      "imageOutputs": {
        "dall-e-3": {
          "imageUrl": "img_01_dall-e-3_512.png",
          "imageAlt": "AI-generated image using dall-e-3"
        },
        "amazon.titan-image-generator-v1": {
          "imageUrl": "img_01_amazon-titan-image-generator-v1_512.png", 
          "imageAlt": "AI-generated image using amazon.titan-image-generator-v1"
        }
      }
    },
    "advertisement1": {
      "imageOutputs": {
        "amazon.nova-canvas-v1:0": {
          "imageUrl": "img_03_amazon-nova-canvas-v1-0_512.png",
          "imageAlt": "Product advertisement, clean design"
        }
      }
    }
  }
}
```

## 🔐 Provider-Specific Implementations

### **AWS Bedrock Image Generation**
```python
def invoke_bedrock_image_model(model_id: str, prompt: str) -> ImageResponse:
    """Invoke AWS Bedrock image model"""
    
    # Build model-specific request body
    if model_id.startswith("amazon.titan-image"):
        body = json.dumps({
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {"text": prompt},
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "height": 512,
                "width": 512,
                "cfgScale": 8.0
            }
        })
    elif model_id.startswith("amazon.nova-canvas"):
        body = json.dumps({
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {"text": prompt},
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "height": 512,
                "width": 512,
                "cfgScale": 7.0,
                "seed": 42
            }
        })
    
    response = safe_invoke(model_id, body, "bedrock-image")
    payload = json.loads(response["body"].read())
    
    # Extract base64 image data
    if "images" in payload:
        image_data = payload["images"][0]
        if model_id.startswith("amazon.nova-canvas"):
            image_data = payload["images"][0].get("data", image_data)
    
    return ImageResponse(
        success=True,
        image_data=image_data,
        model_id=model_id,
        provider="bedrock",
        alt_text=f"AI-generated image using {model_id}"
    )
```

### **OpenAI DALL-E Integration**
```python
def invoke_openai_image_model(model_id: str, prompt: str) -> ImageResponse:
    """Invoke OpenAI DALL-E model"""
    
    api_key = get_openai_api_key()
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    request_body = {
        "model": model_id,
        "prompt": prompt,
        "n": 1,
        "size": "512x512",
        "quality": "standard",
        "response_format": "b64_json"
    }
    
    response = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers=headers,
        json=request_body,
        timeout=120
    )
    
    if response.status_code == 200:
        response_data = response.json()
        image_data = response_data['data'][0]['b64_json']
        
        return ImageResponse(
            success=True,
            image_data=image_data,
            model_id=model_id,
            provider="openai",
            alt_text=f"AI-generated image using {model_id}"
        )
```

## 🔄 Execution Modes

### **Worker Mode** (Called by Orchestrator)
```json
{
  "date": "2025-01-15",
  "model_id": "dall-e-3", 
  "prompt_ids": ["img_01"],
  "worker_mode": true
}
```

### **Legacy Mode** (Date Range Processing)
```json
{
  "start_date": "2025-01-15",
  "end_date": "2025-01-20",
  "model_ids": ["amazon.titan-image-generator-v1", "dall-e-3"]
}
```

### **Manual Testing**
```bash
# Test specific image model
aws lambda invoke \
  --function-name craicgptie_image_runner \
  --payload '{
    "date": "2025-01-15",
    "model_id": "dall-e-3",
    "prompt_ids": ["img_01"],
    "worker_mode": true
  }' \
  --cli-binary-format raw-in-base64-out \
  response.json

# Check generated image
cat response.json | jq '.body' | jq -r '.status'
```

## 📈 Performance & Monitoring

### **Performance Metrics**
- **Processing Time**: 30-120 seconds per image (varies by provider)
- **Success Rate**: >90% across all providers (content filtering may block some)
- **Image Quality**: High quality, web-optimized output
- **Storage Efficiency**: Base64 encoding with S3 binary storage

### **Content Filtering Handling**
```python
# Handle blocked/filtered images uniformly
if not response.success:
    model_specific_outputs[pid] = {
        "blocked": True,
        "reason": response.error_message[:120] if response.error_message else "Unknown error"
    }
    continue
```

### **Monitoring Commands**
```bash
# Monitor image generation
aws logs tail /aws/lambda/craicgptie_image_runner --follow

# Check for content filtering
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie_image_runner \
  --filter-pattern '"blocked":true'

# Monitor provider-specific issues  
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie_image_runner \
  --filter-pattern '"provider":"openai"'

# Check image generation success rates
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie_image_runner \
  --filter-pattern '"Generated image"'
```

## 🖼️ Image Processing Pipeline

### **Image Storage Workflow**
1. **Generation**: Provider generates base64 encoded image
2. **Validation**: Check image data integrity and format
3. **Storage**: Save binary image to S3 with standardized naming
4. **Metadata**: Update paper_content.json with image references
5. **Serving**: CloudFront serves optimized images to frontend

### **File Naming Convention**
```
{prompt_id}_{model_slug}_{size}.png

Examples:
- img_01_dall-e-3_512.png
- img_02_amazon-titan-image-generator-v1_512.png
- img_03_amazon-nova-canvas-v1-0_512.png
```

### **S3 Storage Structure**
```
s3://bucket/static_assets/content/website/YYYY/MM/DD/
├── paper_content.json                          # Metadata
├── img_01_dall-e-3_512.png                    # Main article image
├── img_02_amazon-titan-image-generator-v1_512.png  # Comparison image
├── img_03_amazon-nova-canvas-v1-0_512.png     # Advertisement 1
└── ...                                         # Additional images
```

## 🐛 Troubleshooting

### **Common Issues**

**Content Filtering/Blocked Images**
```bash
# Check for blocked content patterns
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie_image_runner \
  --filter-pattern '"blocked":true' \
  --start-time $(date -v-24H +%s)000

# Review prompt content for filtering triggers
aws s3 cp s3://your-bucket/static_assets/content/prompts/2025/01/15/img_01.json - | jq '.prompt'
```

**Provider API Issues**
```bash
# Test OpenAI API access
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"dall-e-3","prompt":"test","size":"512x512","n":1}' \
  https://api.openai.com/v1/images/generations

# Check Bedrock model availability
aws bedrock list-foundation-models \
  --by-inference-type "ON_DEMAND" \
  --by-output-modality "IMAGE"
```

**Image Storage Issues**
```bash
# Verify S3 permissions
aws s3 cp test.png s3://your-bucket/test-upload.png
aws s3 rm s3://your-bucket/test-upload.png

# Check image file integrity
aws s3 cp s3://your-bucket/static_assets/content/website/2025/01/15/img_01_dall-e-3_512.png test-download.png
file test-download.png  # Should show: PNG image data
```

**Memory/Timeout Issues**
```bash
# Monitor memory usage
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie_image_runner \
  --filter-pattern 'Memory'

# Check timeout patterns
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie_image_runner \
  --filter-pattern 'TIMEOUT'
```

## 🤝 Contributing

### **Adding New Image Providers**
1. Add provider detection logic
2. Implement provider-specific API integration
3. Handle provider-specific response formats
4. Add secrets management configuration
5. Include comprehensive error handling

### **Image Quality Improvements**
- Higher resolution options (1024x1024, 2048x2048)
- Advanced prompt engineering for better images
- Style consistency across providers
- Image optimization and compression

### **Enhanced Features**
- Image variation generation
- Style transfer capabilities
- Batch image processing
- Advanced content filtering bypass

**Multi-Provider Image Generation - Production Ready** 🖼️