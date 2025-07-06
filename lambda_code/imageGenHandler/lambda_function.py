#!/usr/bin/env python3
"""
CraicGPT Multi-Provider Image Generation Handler
===============================================

PURPOSE:
Generate images for CraicGPT newspaper using multiple model providers
(AWS Bedrock, OpenAI DALL-E, Anthropic, Google Gemini) with secrets management.

ARCHITECTURE:
- Single handler supporting all image generation providers
- AWS Secrets Manager for secure API key retrieval
- Backward compatible with existing paper_content.json format
- Atomic saves to prevent concurrent modification issues
- Comprehensive error handling and retry logic

SUPPORTED PROVIDERS:
- AWS Bedrock: Titan Image, Nova Canvas (IAM authentication)
- OpenAI: DALL-E 3 (API key via Secrets Manager)
- Anthropic: Claude 3.5 Sonnet with vision capabilities (API key via Secrets Manager)
- Google Gemini: Gemini Pro Vision (API key via Secrets Manager)

USAGE:
    Single date: {"date": "2025-01-15"}
    Date range:  {"start_date": "2025-01-10", "end_date": "2025-01-15"}
    Worker mode: {"date": "2025-01-15", "model_id": "dall-e-3", "worker_mode": true}

IMAGE-PROMPT → NEWSPAPER SLOT MAP:
    img_01 → mainArticle        (hero)
    img_02 → comparisonArticle  (hero)
    img_03 → advertisements     (ad-block 1)
    img_04 → advertisements     (ad-block 2)
    img_05 → advertisements     (ad-block 3)
    img_06 → advertisements     (ad-block 4)
    img_07 → llmStory           (spot)
    img_08 → joke               (spot)

ENVIRONMENT VARIABLES:
- PROMPT_BUCKET: S3 bucket for prompt and content storage
- OPENAI_SECRET_NAME: AWS Secrets Manager secret name for OpenAI API key
- ANTHROPIC_SECRET_NAME: AWS Secrets Manager secret name for Anthropic API key
- GOOGLE_SECRET_NAME: AWS Secrets Manager secret name for Google API key
- AWS_REGION: AWS region for services (default: eu-west-1)

PERMISSIONS REQUIRED:
- s3:GetObject, s3:PutObject on PROMPT_BUCKET
- bedrock:InvokeModel for Bedrock models
- secretsmanager:GetSecretValue for API key secrets

RUNTIME: Python 3.12
"""
import os
import json
import re
import time
import random
import logging
import base64
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional
from dataclasses import dataclass
from enum import Enum

# Multi-provider support imports
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    logging.warning("requests not available - External API providers disabled")

import boto3
import botocore.exceptions
from botocore.config import Config

# =================================
# CONFIGURATION AND CONSTANTS
# =================================

# S3 and AWS configuration
PROMPT_BUCKET = os.environ["PROMPT_BUCKET"].strip()
PROMPT_ROOT = "static_assets/content/prompts"
PAPER_CONTENT_DIR = "static_assets/content/website"
AWS_REGION = os.getenv("AWS_REGION", "eu-west-1")

# Secrets Manager configuration for secure API key retrieval
OPENAI_SECRET_NAME = os.getenv("OPENAI_SECRET_NAME", "craicgpt/openai-api-key")
ANTHROPIC_SECRET_NAME = os.getenv("ANTHROPIC_SECRET_NAME", "craicgpt/anthropic-api-key")
GOOGLE_SECRET_NAME = os.getenv("GOOGLE_SECRET_NAME", "craicgpt/google-api-key")

# Model configuration - includes all providers
DEFAULT_MODELS = [
    "amazon.titan-image-generator-v1",  # Bedrock
    "amazon.nova-canvas-v1:0",  # Bedrock
    "dall-e-3",  # OpenAI
    "claude-3-5-sonnet-20241022",  # Anthropic (for image analysis/description)
    "gemini-pro-vision"  # Google
]

# ─── Alt-text helpers ───────────────────────────────────────────────
ALT_SLOT_TEXT = {
    "mainArticle":        "Main article illustration",
    "comparisonArticle":  "Comparison article illustration"
}

def ad_alt(idx: int) -> str:          # 0-based → "Ad 1…4"
    return f"Ad {idx + 1}"

# AWS clients with proper configuration
bedrock_cfg = Config(
    read_timeout=90,  # Longer timeout for image generation
    region_name=AWS_REGION,
    retries={'max_attempts': 3, 'mode': 'adaptive'},
    max_pool_connections=50
)

s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime", config=bedrock_cfg)
secrets = boto3.client("secretsmanager", region_name=AWS_REGION)

# API key cache for performance
_api_key_cache = {}

# =================================
# MULTI-PROVIDER SUPPORT CLASSES
# =================================

class ModelProvider(Enum):
    """Supported image generation providers"""
    AWS_BEDROCK = "bedrock"
    OPENAI = "openai"
    ANTHROPIC_DIRECT = "anthropic"
    GOOGLE_GEMINI = "gemini"

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

# =================================
# SECRETS MANAGEMENT
# =================================

def get_api_key(secret_name: str, cache_key: str) -> str:
    """Get API key from AWS Secrets Manager with caching"""
    global _api_key_cache
    
    if cache_key in _api_key_cache:
        return _api_key_cache[cache_key]
    
    try:
        response = secrets.get_secret_value(SecretId=secret_name)
        secret_data = json.loads(response['SecretString'])
        
        # Try multiple possible key names
        api_key = (secret_data.get('api_key') or 
                  secret_data.get('API_KEY') or 
                  secret_data.get('key') or 
                  secret_data.get(cache_key.upper() + '_API_KEY'))
        
        if not api_key:
            raise ValueError(f"API key not found in secret {secret_name}")
        
        _api_key_cache[cache_key] = api_key
        return api_key
        
    except Exception as e:
        log.error(f"Failed to retrieve API key from {secret_name}: {e}")
        raise

def get_openai_api_key() -> str:
    """Get OpenAI API key from AWS Secrets Manager"""
    return get_api_key(OPENAI_SECRET_NAME, "openai")

# =================================
# MULTI-PROVIDER IMAGE GENERATION
# =================================

def determine_provider(model_id: str) -> ModelProvider:
    """Determine which provider to use based on model ID"""
    if model_id.startswith(("dall-e", "gpt-4")):
        return ModelProvider.OPENAI
    elif model_id.startswith(("claude-3-5", "claude-3-opus")) and not model_id.startswith("anthropic."):
        return ModelProvider.ANTHROPIC_DIRECT
    elif model_id.startswith(("gemini-", "palm-", "imagen-")):
        return ModelProvider.GOOGLE_GEMINI
    else:
        return ModelProvider.AWS_BEDROCK

def invoke_bedrock_image_model(model_id: str, prompt: str) -> ImageResponse:
    """Invoke AWS Bedrock image model"""
    start_time = time.time()
    
    try:
        # Build request body based on model type
        if model_id.startswith("amazon.titan-image"):
            body = json.dumps({
                "taskType": "TEXT_IMAGE",
                "textToImageParams": {
                    "text": prompt
                },
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
                "textToImageParams": {
                    "text": prompt
                },
                "imageGenerationConfig": {
                    "numberOfImages": 1,
                    "height": 512,
                    "width": 512,
                    "cfgScale": 7.0,
                    "seed": 42
                }
            })
        else:
            raise ValueError(f"Unsupported Bedrock image model: {model_id}")
        
        # Invoke with retry logic
        resp, blocked, reason = safe_invoke(model_id, body, "bedrock-image")
        if blocked:
            raise Exception(f"Request blocked: {reason}")
        if resp is None:
            raise Exception(f"Model invocation failed after retries")
        payload = json.loads(resp["body"].read())
        
        # Extract image data based on model type
        if "images" in payload:
            if model_id.startswith("amazon.titan-image"):
                image_data = payload["images"][0]
            elif model_id.startswith("amazon.nova-canvas"):
                # Handle both dict and string formats for Nova Canvas
                image_item = payload["images"][0]
                if isinstance(image_item, dict):
                    image_data = image_item.get("data", image_item.get("image", image_item))
                else:
                    image_data = image_item  # Already a string
            else:
                image_data = payload["images"][0]
        else:
            raise ValueError(f"No image data in Bedrock response: {payload}")
        
        return ImageResponse(
            success=True,
            image_data=image_data,
            model_id=model_id,
            provider="bedrock",
            processing_time_ms=int((time.time() - start_time) * 1000),
            finish_reason="completed",
            alt_text=f"AI-generated image using {model_id}"
        )
        
    except Exception as e:
        log.error(f"Bedrock image model {model_id} error: {e}")
        return ImageResponse(
            success=False,
            image_data="",
            model_id=model_id,
            provider="bedrock",
            error_message=str(e),
            error_code="BEDROCK_IMAGE_ERROR"
        )

def invoke_openai_image_model(model_id: str, prompt: str) -> ImageResponse:
    """Invoke OpenAI DALL-E model"""
    if not HAS_REQUESTS:
        return ImageResponse(
            success=False,
            image_data="",
            model_id=model_id,
            provider="openai",
            error_message="requests library not available",
            error_code="MISSING_DEPENDENCY"
        )
    
    start_time = time.time()
    
    try:
        api_key = get_openai_api_key()
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # OpenAI model-specific parameters
        openai_size_overrides = {
            # DALL·E 3 only supports 1024-based sizes
            "dall-e-3": "1024x1024"
        }

        # Pick override if present, otherwise default to 512×512
        req_size = next(
            (sz for m, sz in openai_size_overrides.items() if model_id.startswith(m)),
            "512x512"
        )

        request_body = {
            "model": model_id,
            "prompt": prompt,
            "n": 1,
            "size": req_size,
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
                processing_time_ms=int((time.time() - start_time) * 1000),
                finish_reason="completed",
                alt_text=f"AI-generated image using {model_id}"
            )
        else:
            error_data = response.json() if response.content else {}
            error_msg = error_data.get('error', {}).get('message', f"HTTP {response.status_code}")
            
            return ImageResponse(
                success=False,
                image_data="",
                model_id=model_id,
                provider="openai",
                error_message=error_msg,
                error_code=f"OPENAI_HTTP_{response.status_code}"
            )
            
    except Exception as e:
        log.error(f"OpenAI image model {model_id} error: {e}")
        return ImageResponse(
            success=False,
            image_data="",
            model_id=model_id,
            provider="openai",
            error_message=str(e),
            error_code="OPENAI_IMAGE_ERROR"
        )

def invoke_google_image_model(model_id: str, prompt: str) -> ImageResponse:
    """Invoke Google Imagen model"""
    start_time = time.time()
    
    try:
        # Use educational_runner for Google models if available
        try:
            from educational_runner import EducationalModelRunner
            
            runner = EducationalModelRunner()
            response = runner.invoke_model(model_id, prompt)
            
            if response.success and response.content:
                # Google Imagen returns base64 encoded image
                return ImageResponse(
                    success=True,
                    image_data=response.content,
                    model_id=model_id,
                    provider="google",
                    processing_time_ms=response.processing_time_ms or int((time.time() - start_time) * 1000),
                    finish_reason=response.finish_reason or "completed",
                    alt_text=f"AI-generated image using {model_id}"
                )
            else:
                return ImageResponse(
                    success=False,
                    image_data="",
                    model_id=model_id,
                    provider="google",
                    error_message=response.error_message or "Google image generation failed",
                    error_code=response.error_code or "GOOGLE_IMAGE_ERROR"
                )
        except ImportError:
            return ImageResponse(
                success=False,
                image_data="",
                model_id=model_id,
                provider="google",
                error_message="Google image generation not properly configured - educational_runner unavailable",
                error_code="MISSING_DEPENDENCY"
            )
        except Exception as e:
            return ImageResponse(
                success=False,
                image_data="",
                model_id=model_id,
                provider="google",
                error_message=f"Google image generation error: {str(e)}",
                error_code="GOOGLE_RUNNER_ERROR"
            )
    except Exception as e:
        log.error(f"Google image model {model_id} error: {e}")
        return ImageResponse(
            success=False,
            image_data="",
            model_id=model_id,
            provider="google",
            error_message=str(e),
            error_code="GOOGLE_ERROR"
        )

def invoke_image_model(model_id: str, prompt: str) -> ImageResponse:
    """Unified image model invocation supporting all providers"""
    provider = determine_provider(model_id)
    
    if provider == ModelProvider.AWS_BEDROCK:
        return invoke_bedrock_image_model(model_id, prompt)
    elif provider == ModelProvider.OPENAI:
        return invoke_openai_image_model(model_id, prompt)
    elif provider == ModelProvider.GOOGLE_GEMINI:
        return invoke_google_image_model(model_id, prompt)
    else:
        return ImageResponse(
            success=False,
            image_data="",
            model_id=model_id,
            provider=provider.value,
            error_message=f"Image generation not supported for provider: {provider.value}",
            error_code="UNSUPPORTED_PROVIDER"
        )

slug = lambda m: re.sub(r'[:.\/]', '_', m)        # safe filename helper

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("image_runner")

# ─── Small helpers (dates, S3 I/O) ──────────────────────────────────────
today_iso = lambda: datetime.now(ZoneInfo("Europe/London")).date().isoformat()

def s3_read(key: str) -> str:
    """Read a string from S3"""
    resp = s3.get_object(Bucket=PROMPT_BUCKET, Key=key)
    return resp["Body"].read().decode("utf-8")

def load_prompt_json(prompt_id: str, date: str) -> dict:
    """Load prompt JSON from S3"""
    year, month, day = date.split("-")
    key = f"{PROMPT_ROOT}/{year}/{month}/{day}/{prompt_id}.json"
    data = json.loads(s3_read(key))
    return data

def get_prompt_for_model(prompt_data: dict, model_id: str) -> str:
    """Get the appropriate prompt for a specific model, handling Titan's character limit"""
    original_prompt = prompt_data.get("prompt", "")
    
    # Use Titan-optimized prompt if available and model is Titan
    if model_id.startswith("amazon.titan-image") and "titan_prompt" in prompt_data:
        titan_prompt = prompt_data["titan_prompt"]
        log.info(f"Using Titan-optimized prompt ({len(titan_prompt)} chars) instead of original ({len(original_prompt)} chars)")
        return titan_prompt
    
    return original_prompt

def s3_put(key: str, data: bytes, ct="image/png"):
    s3.put_object(Bucket=PROMPT_BUCKET, Key=key, Body=data, ContentType=ct)

def s3_exists(key: str) -> bool:
    """Check if an S3 object exists"""
    try:
        s3.head_object(Bucket=PROMPT_BUCKET, Key=key)
        return True
    except s3.exceptions.NoSuchKey:
        return False
    except Exception as e:
        log.warning(f"Error checking S3 existence for {key}: {e}")
        return False

# ─── Newspaper JSON skeleton & helpers ──────────────────────────────────
def load_paper_json(y, m, d):
    key = f"{PAPER_CONTENT_DIR}/{y}/{m}/{d}/paper_content.json"
    try:
        existing_paper = json.loads(s3_read(key))
        log.info(f"📄 Found existing paper_content.json for {y}-{m}-{d}")
        return key, existing_paper, True  # True = file existed
    except s3.exceptions.NoSuchKey:
        log.info(f"📄 Creating complete paper_content.json structure for {y}-{m}-{d}")
        # Create complete structure compatible with LLM handler (CRITICAL: must include llmOutputs)
        paper = {
            "publicationDate": f"{y}-{m}-{d}",
            "metadata": { "bannerTitle": "The Artificially Intelligent Times",
                          "defaultLLM": "anthropic.claude-3-sonnet-20240229-v1:0",
                          "defaultImageGen": "amazon.titan-image-generator-v1" },
            "contentSlots": {
                "mainArticle":       { "llmOutputs": {}, "imageOutputs": {} },
                "authorBio":         { "llmOutputs": {}, "imageOutputs": {} },
                "comparisonArticle": { "llmOutputs": {}, "imageOutputs": {} },
                "llmStory":          { "llmOutputs": {}, "imageOutputs": {} },
                "joke":              { "llmOutputs": {}, "imageOutputs": {} },
                "advertisement1":    { "imageOutputs": {} },
                "advertisement2":    { "imageOutputs": {} },
                "advertisement3":    { "imageOutputs": {} },
                "advertisement4":    { "imageOutputs": {} }
            }
        }
        return key, paper, False  # False = file was created new

def save_paper_json(key, obj):
    s3_put(key, json.dumps(obj, indent=2).encode(), "application/json")

def save_paper_json_atomic(key, paper_to_save, worker_model_id, max_retries=3):
    """
    Atomic save with race condition protection.
    Reloads the file before saving to merge changes from other workers.
    """
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                log.info(f"🔄 Retry {attempt}/{max_retries} for atomic save of {key} (worker: {worker_model_id})")
                time.sleep(0.5 * attempt)  # Brief backoff
            
            # Reload the current file to get any changes from other workers
            try:
                current_content = s3_read(key)
                current_paper = json.loads(current_content)
                log.info(f"🔄 Atomic save: Loaded current version of {key} for merge (worker: {worker_model_id})")
            except Exception as e:
                # File might not exist or be corrupted, use our version
                log.info(f"📝 Atomic save: Using our version of {key} (no current file found) (worker: {worker_model_id})")
                current_paper = paper_to_save
            
            # Merge our imageOutputs into the current file
            # Only update the sections that our worker model processed
            for slot_name, slot_data in paper_to_save["contentSlots"].items():
                if "imageOutputs" in slot_data:
                    # Ensure the slot exists in current paper
                    if slot_name not in current_paper["contentSlots"]:
                        current_paper["contentSlots"][slot_name] = {"llmOutputs": {}, "imageOutputs": {}}
                    
                    # Ensure imageOutputs exists in current paper slot
                    if "imageOutputs" not in current_paper["contentSlots"][slot_name]:
                        current_paper["contentSlots"][slot_name]["imageOutputs"] = {}
                    
                    # Only merge our worker's model data, preserve others
                    for model_id, model_outputs in slot_data["imageOutputs"].items():
                        if model_id == worker_model_id:
                            current_paper["contentSlots"][slot_name]["imageOutputs"][model_id] = model_outputs
                            log.info(f"🔄 Merged {model_id} imageOutputs for slot {slot_name}")
            
            # Save the merged version
            save_paper_json(key, current_paper)
            log.info(f"✅ Atomic save completed for {key} (worker: {worker_model_id})")
            return
            
        except Exception as e:
            log.warning(f"⚠️  Atomic save attempt {attempt + 1} failed for {key} (worker: {worker_model_id}): {e}")
            if attempt == max_retries - 1:
                log.error(f"❌ Atomic save failed after {max_retries} attempts, falling back to direct save")
                save_paper_json(key, paper_to_save)

# ─── Prompt → slot mapping ──────────────────────────────────────────────
PROMPT_TO_SLOT = {
    "img_01": "mainArticle",
    "img_02": "comparisonArticle",
    "img_03": "advertisement1",  # Changed from "advertisements" to individual slots
    "img_04": "advertisement2",
    "img_05": "advertisement3", 
    "img_06": "advertisement4",
    "img_07": "llmStory",
    "img_08": "joke"
}
ALT_SLOT_TEXT.update({ # Add alt text for new slots
    "llmStory": "LLM story illustration",
    "joke": "Joke illustration",
    "advertisement1": "Advertisement 1",
    "advertisement2": "Advertisement 2", 
    "advertisement3": "Advertisement 3",
    "advertisement4": "Advertisement 4"
})

# ─── Titan-specific prompt simplification ──────────────────────────────────
def simplify_prompt_for_titan(original_prompt: str, slot: str) -> str:
    """
    Create a simplified version of the prompt optimized for Titan Image Generator.
    Titan works better with shorter, more focused prompts.
    """
    
    # Base simplified prompts for each content type
    titan_base_prompts = {
        "mainArticle": "Family scene with father and children, cozy home setting",  # Restored original
        "comparisonArticle": "Simple data chart, clean infographic style", 
        "llmStory": "Cozy indoor scene, single person",
        "joke": "Simple cartoon style, editorial illustration",
        "advertisement1": "Product advertisement, clean design",
        "advertisement2": "Product advertisement, clean design", 
        "advertisement3": "Product advertisement, clean design",
        "advertisement4": "Product advertisement, clean design"
    }
    
    # Get the base prompt for this slot
    base = titan_base_prompts.get(slot, "Simple illustration")
    
    # Extract key elements from original prompt that Titan handles well
    simple_elements = []
    
    # Look for style keywords that Titan understands
    style_keywords = {
        "comic": "comic style",
        "cartoon": "cartoon style", 
        "realistic": "realistic style",
        "illustration": "illustration",
        "infographic": "infographic",
        "chart": "chart",
        "billboard": "advertisement",
        "poster": "poster"
    }
    
    for keyword, simple_style in style_keywords.items():
        if keyword in original_prompt.lower():
            simple_elements.append(simple_style)
            break  # Only take first match
    
    # Look for simple lighting/mood
    if "bright" in original_prompt.lower() or "sun" in original_prompt.lower():
        simple_elements.append("bright lighting")
    elif "cozy" in original_prompt.lower() or "warm" in original_prompt.lower():
        simple_elements.append("warm lighting")
    
    # Combine base with simple elements
    if simple_elements:
        return f"{base}, {', '.join(simple_elements[:2])}"  # Max 2 additional elements
    else:
        return base

def safe_invoke_with_fallback(model_id: str, original_prompt: str, slot: str, size: int, tag: str, 
                             max_retries: int = 6, base_delay: float = 0.25):
    """
    Enhanced safe_invoke that tries simplified prompts for Titan when original fails.
    """
    
    # First, try with original prompt using existing safe_invoke
    body = build_body(model_id, original_prompt, size=size)
    
    # Debug logging for Titan
    if model_id.startswith("amazon.titan-image"):
        log.info(f"🔍 TITAN DEBUG - Original prompt: {original_prompt}")
        log.info(f"🔍 TITAN DEBUG - Request body: {body}")
    
    resp, blocked, reason = safe_invoke(model_id, body, tag, max_retries, base_delay)
    
    # If successful, return as-is
    if resp is not None:
        return resp, blocked, reason, False  # False = didn't use fallback
    
    # For Titan models, try simplified prompt for both failures and content blocks
    if model_id.startswith("amazon.titan-image"):
        if blocked:
            log.info(f"🔄 Titan blocked by content filter, trying simplified version for {tag}")
        else:
            log.info(f"🔄 Titan failed with error, trying simplified version for {tag}")
        
        simplified_prompt = simplify_prompt_for_titan(original_prompt, slot)
        log.info(f"   Original: {original_prompt[:100]}...")
        log.info(f"   Simplified: {simplified_prompt}")
        
        # Try with simplified prompt
        simple_body = build_body(model_id, simplified_prompt, size=size)
        log.info(f"🔍 TITAN DEBUG - Simplified request body: {simple_body}")
        
        resp, blocked, reason = safe_invoke(model_id, simple_body, f"{tag}-simplified", max_retries//2, base_delay)
        
        if resp is not None:
            log.info(f"✅ Titan succeeded with simplified prompt for {tag}")
            return resp, blocked, reason, True  # True = used fallback
        else:
            log.warning(f"❌ Titan failed even with simplified prompt for {tag}: {reason}")
            return resp, blocked, reason, False
    
    # For non-Titan models or if original succeeded, return original result
    return resp, blocked, reason, False

# ─── REQUEST BODY builder (Titan & Nova share schema) ───────────────────
def build_body(model_id: str, prompt: str, *, size: int) -> str:
    """
    Return a JSON string for GA Bedrock image models.
    """
    # Enhanced negative prompts for better quality
    enhanced_negative = "low quality, blurry, ugly, distorted, watermark, text overlay, deformed"
    
    # Titan-specific optimizations
    if model_id.startswith("amazon.titan-image"):
        # Correct Titan request format to avoid false positives
        return json.dumps({
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {
                "text": prompt
            },
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "height": size,
                "width": size
            }
        })
    else:
        # Nova and other models can handle more complex configs
        return json.dumps({
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {
                 "text": prompt,
                 "negativeText": enhanced_negative
            },
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "quality": "premium",  # Nova can handle premium quality
                "width": size,
                "height": size,
                "cfgScale": 8.0
            }
        })

# ─── Bedrock invoke with exponential back-off ───────────────────────────
def safe_invoke(model_id: str, body_json: str, tag: str,
                max_retries: int = 6, base_delay: float = 0.25):
    """
    Invoke the Bedrock model with retries.

    Returns
    -------
    (resp, blocked, reason)
      resp    : botocore response object | None
      blocked : bool  – True if ValidationException (content filter)
      reason  : str | None  – server message from ValidationException
    """
    blocked_msg = None
    for attempt in range(max_retries):
        try:
            resp = bedrock.invoke_model(
                modelId=model_id,
                body=body_json,
                contentType="application/json",
                accept="application/json"
            )
            return resp, False, None
        except botocore.exceptions.ClientError as err:
            code = err.response["Error"]["Code"]
            if code == "ThrottlingException":
                wait = min(base_delay * (2 ** attempt), 8) + random.random() * 0.1
                log.warning("⏳  %s throttled (%s attempt %d) – %.2fs",
                            model_id, tag, attempt + 1, wait)
                time.sleep(wait)
                continue
            if code == "ValidationException":
                blocked_msg = err.response["Error"].get("Message", "?")
                log.warning("⚠️  %s ValidationException – %s → %s",
                            model_id, tag, blocked_msg)
                return None, True, blocked_msg
            raise
    log.error("🚫  %s throttled >%d× – skipped", model_id, max_retries)
    return None, False, None

# ─── Helper: extract base-64 PNG from Bedrock payload ───────────────────
def extract_base64(payload, model_id):
    """
    Robust extraction of base64 PNG from payload.
    Handles dict, list, or string payloads from Bedrock.
    """
    # Enhanced debugging for Nova Canvas
    if "nova" in model_id.lower():
        log.info(f"🔍 NOVA DEBUG - Payload type: {type(payload)}")
        if isinstance(payload, dict):
            log.info(f"🔍 NOVA DEBUG - Payload keys: {list(payload.keys())}")
            log.info(f"🔍 NOVA DEBUG - Full payload: {payload}")
        else:
            log.info(f"🔍 NOVA DEBUG - Payload content: {payload}")
    
    if isinstance(payload, str):
        log.info(f"✅ {model_id} - Found base64 as direct string")
        return payload

    if isinstance(payload, list):
        # Handles direct list-of-strings response
        result = payload[0] if payload else None
        if result:
            log.info(f"✅ {model_id} - Found base64 in list[0]")
        return result

    if isinstance(payload, dict):
        # Handle known dict structures from Bedrock
        if "base64" in payload:
            log.info(f"✅ {model_id} - Found base64 in payload['base64']")
            return payload["base64"]
        
        for key in ["images", "artifacts"]:
            if key in payload and isinstance(payload[key], list):
                for item in payload[key]:
                    if isinstance(item, dict) and "base64" in item:
                        log.info(f"✅ {model_id} - Found base64 in payload['{key}'][item]['base64']")
                        return item["base64"]
                    elif isinstance(item, str):
                        log.info(f"✅ {model_id} - Found base64 string in payload['{key}'][item]")
                        return item
        
        # Nova Canvas specific check - it might use a different structure
        if "nova" in model_id.lower():
            # Check for any key that contains image data
            for key, value in payload.items():
                if isinstance(value, str) and len(value) > 1000:  # Likely base64 image
                    log.info(f"✅ NOVA - Found potential base64 in payload['{key}'] (length: {len(value)})")
                    return value
                elif isinstance(value, dict) and "data" in value:
                    log.info(f"✅ NOVA - Found base64 in payload['{key}']['data']")
                    return value["data"]
        
        # Special case: directly a list under an unknown key
        for key, value in payload.items():
            if isinstance(value, list) and value:
                if isinstance(value[0], str):
                    log.info(f"✅ {model_id} - Found base64 string in payload['{key}'][0]")
                    return value[0]

    # If nothing matches, return None explicitly
    log.warning(f"⚠️ FAILED TO EXTRACT for {model_id}")
    log.warning(f"   Payload type: {type(payload)}")
    if isinstance(payload, dict):
        log.warning(f"   Payload keys: {list(payload.keys())}")
        log.warning(f"   Payload sample: {str(payload)[:500]}...")
    return None


# ═══════════════════════════════════════════════════════════════════════════
# DATE RANGE UTILITY
# ═══════════════════════════════════════════════════════════════════════════

def generate_date_range(start_date: str, end_date: str) -> list[str]:
    """Generate list of dates between start and end (inclusive)"""
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()
    
    dates = []
    current = start
    while current <= end:
        dates.append(current.isoformat())
        current += timedelta(days=1)
    
    return dates

# ─── Lambda entry-point ─────────────────────────────────────────────────
def lambda_handler(event, _ctx):
    """
    Enhanced worker handler - processes single model/date combinations
    
    Worker Mode (NEW - called by orchestrator):
    {"date": "2025-01-15", "model": "amazon.titan-image-generator-v1", "worker_mode": true}
    
    Legacy Mode (fallback for backwards compatibility):
    Single date: {"date": "2025-01-15"}
    Date range:  {"start_date": "2025-01-10", "end_date": "2025-01-15"}
    Environment variables: START_DATE, END_DATE
    """
    
    try:
        # Check for special debugging mode
        if event.get("debug"):
            import logging
            logging.getLogger().setLevel(logging.DEBUG)
            log.setLevel(logging.DEBUG)
            
        # Check for force regeneration mode
        force_regenerate = event.get("force_regenerate", False)
        
        # Environment variable fallback for dates (for production scheduling)
        if event.get("worker_mode"):
            # Worker mode - process single model/date combination for ALL image prompts
            dates = [event.get("date", today_iso())]
            model_ids = [event.get("model_id", DEFAULT_MODELS[0])]
            prompt_ids = [f"img_{i:02}" for i in range(1, 9)]  # Process ALL image prompts
            
            log.info("Worker mode: Processing ALL image prompts with %s for %s", 
                     model_ids[0], dates[0])
        else:
            # Legacy mode - handle multiple dates/models/prompts
            # Get date range from event payload first, fallback to environment variables, then default
            event_start = event.get("START_DATE")
            event_end = event.get("END_DATE")
            env_start = os.getenv("START_DATE")
            env_end = os.getenv("END_DATE")
            
            # Priority: event payload -> environment -> event legacy fields -> default
            if event_start and event_end:
                dates = generate_date_range(event_start, event_end)
                log.info("Using event payload dates: %s to %s (%d dates)", 
                         event_start, event_end, len(dates))
            elif event_start:
                dates = [event_start]
                log.info("Using event payload single date: %s", event_start)
            elif env_start and env_end:
                dates = generate_date_range(env_start, env_end)
                log.info("Using environment variable dates: %s to %s (%d dates)", 
                         env_start, env_end, len(dates))
            elif env_start:
                dates = [env_start]
                log.info("Using environment variable single date: %s", env_start)
            elif "start_date" in event and "end_date" in event:
                dates = generate_date_range(event["start_date"], event["end_date"])
                log.info("Processing event legacy date range: %s to %s (%d dates)", 
                         event["start_date"], event["end_date"], len(dates))
            elif "dates" in event:
                dates = event["dates"]
                log.info("Processing custom event date list: %d dates", len(dates))
            elif "date" in event:
                dates = [event["date"]]
                log.info("Processing single event legacy date: %s", event["date"])
            else:
                dates = [today_iso()]
                log.info("Processing default date (today): %s", dates[0])
            
            model_ids = event.get("model_ids") or DEFAULT_MODELS
            
        # Updated to include img_07 and img_08 for llmStory and joke images
        prompt_ids = event.get("prompt_ids") or [f"img_{i:02}" for i in range(1, 9)]

        start_time = time.time()
        # Track successes, failures and skips for worker-mode health reporting
        results_summary = {
            "successful_dates": 0,
            "failed_dates": 0,
            "total_images": 0,   # newly generated images
            "skipped_images": 0  # images that already existed and were therefore skipped
        }

        for day in dates:
            log.info("Processing date: %s (force_regenerate=%s)", day, force_regenerate)
            y, m, d = day.split("-")
            
            try:
                paper_key, paper, file_existed = load_paper_json(y, m, d)
                
                if file_existed:
                    log.info(f"🔍 Checking existing images for incremental processing on {day}")
                else:
                    log.info(f"🆕 Full image generation required for {day}")

                for pid in prompt_ids:
                    slot = PROMPT_TO_SLOT.get(pid)
                    if not slot:
                        log.warning("Unknown img_id %s – skipped", pid)
                        continue

                    try:
                        s3_key_for_prompt = f"{PROMPT_ROOT}/{y}/{m}/{d}/{pid}.json"
                        log.debug(f"Reading prompt from S3: {s3_key_for_prompt}")

                        prompt_json = s3_read(s3_key_for_prompt)
                        prompt_data = json.loads(prompt_json)
                        # Note: prompt_txt will be determined per model inside the model loop
                    except Exception as e:
                        log.error(f"Failed to load prompt {pid} for {day}: {e}")
                        continue

                    for model_id in model_ids:
                        # Get the appropriate prompt for this specific model
                        prompt_txt = get_prompt_for_model(prompt_data, model_id)
                        
                        # Use the full model ID as the key (same as LLM handler)
                        mdl_key = model_id
                        # Create a safe filename version of the model ID
                        mdl_slug = slug(model_id)  # Use the slug helper for consistent filename sanitization

                        # Determine image dimensions based on provider/model
                        if model_id.startswith("dall-e-3"):
                            px = 1024  # DALL·E 3 default square size
                        else:
                            px = 512  # default
                        
                        # Ensure the imageOutputs dictionary exists for the slot and model
                        slot_image_outputs = paper["contentSlots"][slot].setdefault("imageOutputs", {})
                        model_specific_outputs = slot_image_outputs.setdefault(mdl_key, {})
                        
                        # Check if image already exists (both JSON metadata AND actual file)
                        should_skip = False
                        existing_image = model_specific_outputs.get(pid) if file_existed else None
                        
                        if file_existed and not force_regenerate:  # Skip only if not forcing regeneration
                            if (existing_image and
                                isinstance(existing_image, dict) and
                                existing_image.get("imageUrl") and
                                isinstance(existing_image.get("imageUrl"), str) and
                                len(str(existing_image.get("imageUrl", "")).strip()) > 10 and
                                not existing_image.get("blocked", False)):
                                
                                # Also check if the actual image file exists in S3
                                image_filename = existing_image["imageUrl"]
                                image_s3_key = f"{PAPER_CONTENT_DIR}/{y}/{m}/{d}/{image_filename}"
                                
                                if s3_exists(image_s3_key):
                                    log.info(f"✅ Image already exists for {model_id} {pid} on {day} ({image_filename}) - skipping")
                                    should_skip = True
                                else:
                                    log.info(f"🔄 JSON has imageUrl but file missing from S3 for {model_id} {pid} on {day} - regenerating")
                            else:
                                log.info(f"🔄 Generating missing/invalid image for {model_id} {pid} on {day}")
                        elif force_regenerate:
                            log.info(f"🔥 Force regeneration enabled - regenerating {model_id} {pid} on {day}")
                        else:
                            log.info(f"🆕 New file - generating all images for {model_id} {pid} on {day}")
                        
                        if should_skip:
                            # Treat previously-existing images as successful for success-rate calculation
                            results_summary["skipped_images"] += 1
                            continue
                        
                        # Clean up any existing blocked data when force regenerating
                        if force_regenerate and existing_image:
                            if existing_image.get("blocked"):
                                log.info(f"🧹 Cleaning up old blocked data for {model_id} {pid} on {day}: {existing_image.get('reason', 'No reason')}")
                                del model_specific_outputs[pid]  # Remove old blocked entry
                            else:
                                log.info(f"🧹 Cleaning up existing image data for {model_id} {pid} on {day}: {existing_image.get('imageUrl', 'No URL')}")
                                del model_specific_outputs[pid]  # Remove old successful entry for fresh generation
                        
                        tag  = f"{pid}-{px}"
                        
                        # Use unified multi-provider image generation
                        response = invoke_image_model(model_id, prompt_txt)
                        
                        # Handle failed/blocked images uniformly for all slots
                        if not response.success:
                            log.error(f"❌ Image generation failed for {model_id} on {pid}: {response.error_message}")
                            model_specific_outputs[pid] = {
                                "blocked": True,
                                "reason": response.error_message[:120] if response.error_message else "Unknown error"
                            }
                            continue

                        # ─── successful image ────────────────────────────────────
                        img_bytes = base64.b64decode(response.image_data)
                        fname = f"{pid}_{mdl_slug}_{px}.png"
                        key   = f"{PAPER_CONTENT_DIR}/{y}/{m}/{d}/{fname}"
                        s3_put(key, img_bytes)

                        entry = {
                            "imageUrl": fname, 
                            "imageAlt": ALT_SLOT_TEXT.get(slot, "Illustration")
                        }

                        # All slots now use the same structure: store under specific prompt_id (pid)
                        model_specific_outputs[pid] = entry
                        results_summary["total_images"] += 1
                        log.info(f"✅ Generated image {pid} for {model_id} → {fname}")

                # Atomic save with race condition protection
                save_paper_json_atomic(paper_key, paper, model_ids[0] if len(model_ids) == 1 else "multi-model")
                results_summary["successful_dates"] += 1
                log.info("✅ Completed processing for %s", day)
                
            except Exception as e:
                log.error("❌ Failed to process date %s: %s", day, e)
                results_summary["failed_dates"] += 1
                continue

        processing_time = time.time() - start_time

        # ── Worker-mode health check ─────────────────────────────────────
        if event.get("worker_mode"):
            total_expected = len(prompt_ids) * len(model_ids) * len(dates)
            successful_prompts = results_summary["total_images"] + results_summary["skipped_images"]
            failed_prompts = total_expected - successful_prompts
            success_rate = successful_prompts / total_expected if total_expected > 0 else 1.0

            status_code = 200 if success_rate >= 0.8 else 500
            status_str  = "success" if status_code == 200 else "error"

            return {
                "statusCode": status_code,
                "body": json.dumps({
                    "status": status_str,
                    "prompts_processed": successful_prompts,
                    "prompts_failed": failed_prompts,
                    "success_rate": round(success_rate * 100, 1),
                    "processing_time": round(processing_time, 2),
                    "model": model_ids[0] if len(model_ids) == 1 else model_ids,
                    "date": dates[0] if len(dates) == 1 else dates
                })
            }
        
        # Legacy mode returns detailed response
        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "SUCCESS",
                "processing_time_seconds": round(processing_time, 2),
                "dates_processed": results_summary["successful_dates"],
                "dates_failed": results_summary["failed_dates"],
                "total_dates": len(dates),
                "total_images_generated": results_summary["total_images"],
                "prompt_ids": prompt_ids,
                "model_ids": model_ids,
                "configuration": {
                    "aws_region": AWS_REGION,
                    "prompt_bucket": PROMPT_BUCKET
                }
            })
        }
        
    except Exception as e:
        log.error("❌ Fatal error in image generation: %s", e)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
