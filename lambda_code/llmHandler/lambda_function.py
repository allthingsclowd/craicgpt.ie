#!/usr/bin/env python3
"""
CraicGPT Multi-Provider LLM Text Generation Handler
==================================================

PURPOSE:
Generate text content for CraicGPT newspaper using multiple model providers
(AWS Bedrock, OpenAI, Anthropic Direct, Google Gemini) with secrets management.

ARCHITECTURE:
- Single handler supporting all model providers
- AWS Secrets Manager for secure API key retrieval
- Backward compatible with existing paper_content.json format
- Atomic saves to prevent concurrent modification issues
- Comprehensive error handling and retry logic

SUPPORTED PROVIDERS:
- AWS Bedrock: Claude, Titan Text (IAM authentication)
- OpenAI: GPT-4, O3 Mini (API key via Secrets Manager)
- Anthropic Direct: Claude 3.5 Sonnet (API key via Secrets Manager)
- Google Gemini: Gemini Pro, Ultra (API key via Secrets Manager)

USAGE:
    Single date: {"date": "2025-01-15"}
    Date range:  {"start_date": "2025-01-10", "end_date": "2025-01-15"}
    Worker mode: {"date": "2025-01-15", "model_id": "gpt-4", "worker_mode": true}

PROMPT-ID → NEWSPAPER SLOT MAP:
    llm_01 → mainArticle        {title, text}
    llm_02 → comparisonArticle  {title, text}
    llm_03 → llmStory           {content}
    llm_04 → joke               {content}
    llm_05 → authorBio          {content}

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
from datetime import datetime, date, timedelta
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

# Model configuration
ALLOW_EMBED = os.getenv("ALLOW_EMBED_MODELS", "").lower() == "true"
DEFAULT_MODELS = [
    "anthropic.claude-3-sonnet-20240229-v1:0",  # Bedrock
    "gpt-4",  # OpenAI
    "claude-3-5-sonnet-20241022",  # Anthropic Direct
    "gemini-pro"  # Google
]

# AWS clients with proper configuration
config = Config(
    region_name=AWS_REGION,
    retries={'max_attempts': 3, 'mode': 'adaptive'},
    max_pool_connections=50
)

s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION, config=config)
secrets = boto3.client("secretsmanager", region_name=AWS_REGION)

# API key cache for performance
_api_key_cache = {}

slug = lambda m: re.sub(r'[:.\/]', '_', m)       # safe filename helper

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("llm_runner")

# ─── Small helpers (dates, S3 I/O) ──────────────────────────────────────
today_iso   = lambda: datetime.now(ZoneInfo("Europe/London")).date().isoformat()

def s3_read(key: str) -> str:
    return s3.get_object(Bucket=PROMPT_BUCKET, Key=key)["Body"].read().decode()

def s3_put(key: str, data, ct="text/plain; charset=utf-8"):
    s3.put_object(
        Bucket=PROMPT_BUCKET, Key=key,
        Body=data.encode() if isinstance(data, str) else data,
        ContentType=ct
    )

# ─── Newspaper JSON skeleton & helpers ──────────────────────────────────
def load_paper_json(y, m, d):
    key = f"{PAPER_CONTENT_DIR}/{y}/{m}/{d}/paper_content.json"
    try:
        existing_paper = json.loads(s3_read(key))
        log.info(f"📄 Found existing paper_content.json for {y}-{m}-{d}")
        return key, existing_paper, True  # True = file existed
    except s3.exceptions.NoSuchKey:
        log.info(f"📄 Creating new paper_content.json for {y}-{m}-{d}")
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
    s3_put(key, json.dumps(obj, indent=2), "application/json")

# ─── Atomic save (LLM) ───────────────────────────────────────────────────

def save_paper_json_atomic_llm(key: str, paper_to_save: dict, worker_model_id: str, max_retries: int = 3):
    """Atomic save that merges only this worker's llmOutputs into the existing paper file."""
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                log.info(f"🔄 Retry {attempt}/{max_retries} atomic LLM save for {key} (worker: {worker_model_id})")
                time.sleep(0.4 * attempt)

            # Load current version if present
            try:
                current_raw = s3_read(key)
                current_paper = json.loads(current_raw)
            except Exception:
                current_paper = paper_to_save  # File missing or unreadable

            # Merge llmOutputs for this worker's model
            for slot_name, slot_data in paper_to_save.get("contentSlots", {}).items():
                if "llmOutputs" not in slot_data:
                    continue

                if slot_name not in current_paper.get("contentSlots", {}):
                    current_paper.setdefault("contentSlots", {})[slot_name] = {"llmOutputs": {}, "imageOutputs": {}}

                cur_slot = current_paper["contentSlots"][slot_name].setdefault("llmOutputs", {})
                new_data = slot_data["llmOutputs"].get(worker_model_id)
                if new_data is not None:
                    cur_slot[worker_model_id] = new_data

            # Save
            save_paper_json(key, current_paper)
            log.info(f"✅ Atomic LLM save complete for {key} (worker: {worker_model_id})")
            return
        except Exception as e:
            log.warning(f"⚠️ Atomic LLM save attempt {attempt+1} failed for {key}: {e}")
            if attempt == max_retries - 1:
                log.error("❌ Falling back to direct save – may overwrite concurrent changes")
                save_paper_json(key, paper_to_save)

# ─── Prompt → slot mapping ──────────────────────────────────────────────
PROMPT_TO_SLOT = {
    "llm_01": ("mainArticle",        "title_text"),
    "llm_02": ("comparisonArticle",  "title_text"),
    "llm_03": ("llmStory",           "content"),
    "llm_04": ("joke",               "content"),
    "llm_05": ("authorBio",          "content")
}

# =================================
# MULTI-PROVIDER SUPPORT CLASSES
# =================================

class ModelProvider(Enum):
    """Supported model providers"""
    AWS_BEDROCK = "bedrock"
    OPENAI = "openai"
    ANTHROPIC_DIRECT = "anthropic"
    GOOGLE_GEMINI = "gemini"

@dataclass
class ModelResponse:
    """Standardized response format for all providers"""
    success: bool
    content: str
    model_id: str
    provider: str
    tokens_used: Optional[int] = None
    processing_time_ms: Optional[int] = None
    finish_reason: Optional[str] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None

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

def get_anthropic_api_key() -> str:
    """Get Anthropic API key from AWS Secrets Manager"""
    return get_api_key(ANTHROPIC_SECRET_NAME, "anthropic")

def get_google_api_key() -> str:
    """Get Google API key from AWS Secrets Manager"""
    return get_api_key(GOOGLE_SECRET_NAME, "google")

# =================================
# MULTI-PROVIDER MODEL INVOCATION
# =================================

def determine_provider(model_id: str) -> ModelProvider:
    """Determine which provider to use based on model ID"""
    if model_id.startswith(("gpt-", "o3-", "text-davinci", "dall-e")):
        return ModelProvider.OPENAI
    elif model_id.startswith(("claude-3-5", "claude-3-opus")) and not model_id.startswith("anthropic."):
        return ModelProvider.ANTHROPIC_DIRECT
    elif model_id.startswith(("gemini-", "palm-")):
        return ModelProvider.GOOGLE_GEMINI
    else:
        return ModelProvider.AWS_BEDROCK

def invoke_bedrock_model(model_id: str, prompt: str) -> ModelResponse:
    """Invoke AWS Bedrock model with proper error handling"""
    start_time = time.time()
    
    try:
        # Build request body based on model family
        if model_id.startswith("anthropic."):
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "system": prompt,
                "messages": [{ "role": "user", "content": "Generate." }],
                "max_tokens": 800,
                "temperature": 0.7,
                "top_p": 0.9
            })
        elif model_id.startswith("amazon.titan-text"):
            body = json.dumps({
                "inputText": prompt,
                "textGenerationConfig": {
                    "maxTokenCount": 512,
                    "temperature": 0.7,
                    "topP": 0.9,
                    "stopSequences": []
                }
            })
        elif model_id.startswith("mistral."):
            body = json.dumps({
                "messages": [
                    { "role": "system", "content": prompt },
                    { "role": "user", "content": "Generate." }
                ],
                "max_tokens": 800,
                "temperature": 0.7,
                "top_p": 0.9
            })
        else:
            # Generic fallback
            body = json.dumps({ "prompt": prompt })
        
        # Invoke with retry logic
        response = safe_invoke(model_id, body, "bedrock")
        payload = json.loads(response["body"].read())
        
        # Extract content based on model type
        if "content" in payload:
            content = payload["content"][0]["text"]
        elif "results" in payload:
            content = payload["results"][0]["outputText"]
        else:
            content = str(payload)
        
        # Extract usage info
        usage = payload.get("usage", {})
        tokens_used = usage.get("output_tokens", 0)
        
        return ModelResponse(
            success=True,
            content=content.strip(),
            model_id=model_id,
            provider="bedrock",
            tokens_used=tokens_used,
            processing_time_ms=int((time.time() - start_time) * 1000),
            finish_reason="completed"
        )
        
    except Exception as e:
        log.error(f"Bedrock model {model_id} error: {e}")
        return ModelResponse(
            success=False,
            content="",
            model_id=model_id,
            provider="bedrock",
            error_message=str(e),
            error_code="BEDROCK_ERROR"
        )

def invoke_openai_model(model_id: str, prompt: str) -> ModelResponse:
    """Invoke OpenAI model via educational_runner"""
    try:
        from educational_runner import run_model
        
        response = run_model(model_id, prompt)
        
        if response.success:
            return ModelResponse(
                success=True,
                content=response.response_data.get("content", ""),
                model_id=model_id,
                provider="openai",
                processing_time_ms=response.processing_time_ms,
                tokens_used=response.usage.get("total_tokens", 0),
                finish_reason="completed"
            )
        else:
            return ModelResponse(
                success=False,
                content="",
                model_id=model_id,
                provider="openai",
                error_message=response.error_message,
                error_code="OPENAI_ERROR"
            )
    except Exception as e:
        return ModelResponse(
            success=False,
            content="",
            model_id=model_id,
            provider="openai",
            error_message=str(e),
            error_code="OPENAI_ERROR"
        )
    
    start_time = time.time()
    
    try:
        api_key = get_openai_api_key()
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        request_body = {
            "model": model_id,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 800,
            "top_p": 0.9
        }
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=request_body,
            timeout=60
        )
        
        if response.status_code == 200:
            response_data = response.json()
            content = response_data['choices'][0]['message']['content']
            tokens_used = response_data['usage']['total_tokens']
            
            return ModelResponse(
                success=True,
                content=content.strip(),
                model_id=model_id,
                provider="openai",
                tokens_used=tokens_used,
                processing_time_ms=int((time.time() - start_time) * 1000),
                finish_reason=response_data['choices'][0]['finish_reason']
            )
        else:
            error_data = response.json() if response.content else {}
            error_msg = error_data.get('error', {}).get('message', f"HTTP {response.status_code}")
            
            return ModelResponse(
                success=False,
                content="",
                model_id=model_id,
                provider="openai",
                error_message=error_msg,
                error_code=f"OPENAI_HTTP_{response.status_code}"
            )
            
    except Exception as e:
        log.error(f"OpenAI model {model_id} error: {e}")
        return ModelResponse(
            success=False,
            content="",
            model_id=model_id,
            provider="openai",
            error_message=str(e),
            error_code="OPENAI_ERROR"
        )

def invoke_anthropic_model(model_id: str, prompt: str) -> ModelResponse:
    """Invoke Anthropic model via direct API"""
    if not HAS_REQUESTS:
        return ModelResponse(
            success=False,
            content="",
            model_id=model_id,
            provider="anthropic",
            error_message="requests library not available",
            error_code="MISSING_DEPENDENCY"
        )
    
    start_time = time.time()
    
    try:
        api_key = get_anthropic_api_key()
        
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        request_body = {
            "model": model_id,
            "max_tokens": 800,
            "temperature": 0.7,
            "top_p": 0.9,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
        
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=request_body,
            timeout=60
        )
        
        if response.status_code == 200:
            response_data = response.json()
            content = response_data['content'][0]['text']
            tokens_used = response_data['usage']['output_tokens']
            
            return ModelResponse(
                success=True,
                content=content.strip(),
                model_id=model_id,
                provider="anthropic",
                tokens_used=tokens_used,
                processing_time_ms=int((time.time() - start_time) * 1000),
                finish_reason=response_data.get('stop_reason', 'end_turn')
            )
        else:
            error_data = response.json() if response.content else {}
            error_msg = error_data.get('error', {}).get('message', f"HTTP {response.status_code}")
            
            return ModelResponse(
                success=False,
                content="",
                model_id=model_id,
                provider="anthropic",
                error_message=error_msg,
                error_code=f"ANTHROPIC_HTTP_{response.status_code}"
            )
            
    except Exception as e:
        log.error(f"Anthropic model {model_id} error: {e}")
        return ModelResponse(
            success=False,
            content="",
            model_id=model_id,
            provider="anthropic",
            error_message=str(e),
            error_code="ANTHROPIC_ERROR"
        )

def invoke_gemini_model(model_id: str, prompt: str) -> ModelResponse:
    """Invoke Google Gemini model via REST API"""
    if not HAS_REQUESTS:
        return ModelResponse(
            success=False,
            content="",
            model_id=model_id,
            provider="gemini",
            error_message="requests library not available",
            error_code="MISSING_DEPENDENCY"
        )
    
    start_time = time.time()
    
    try:
        api_key = get_google_api_key()
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        request_body = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
                "topP": 0.9,
                "topK": 40,
                "maxOutputTokens": 800
            }
        }
        
        response = requests.post(
            url,
            headers=headers,
            json=request_body,
            timeout=60
        )
        
        if response.status_code == 200:
            response_data = response.json()
            content = response_data['candidates'][0]['content']['parts'][0]['text']
            
            # Gemini doesn't always provide token counts
            tokens_used = None
            usage_metadata = response_data.get('usageMetadata')
            if usage_metadata:
                tokens_used = usage_metadata.get('totalTokenCount')
            
            return ModelResponse(
                success=True,
                content=content.strip(),
                model_id=model_id,
                provider="gemini",
                tokens_used=tokens_used,
                processing_time_ms=int((time.time() - start_time) * 1000),
                finish_reason=response_data['candidates'][0].get('finishReason', 'STOP')
            )
        else:
            error_data = response.json() if response.content else {}
            error_msg = error_data.get('error', {}).get('message', f"HTTP {response.status_code}")
            
            return ModelResponse(
                success=False,
                content="",
                model_id=model_id,
                provider="gemini",
                error_message=error_msg,
                error_code=f"GEMINI_HTTP_{response.status_code}"
            )
            
    except Exception as e:
        log.error(f"Gemini model {model_id} error: {e}")
        return ModelResponse(
            success=False,
            content="",
            model_id=model_id,
            provider="gemini",
            error_message=str(e),
            error_code="GEMINI_ERROR"
        )

def invoke_external_model(model_id: str, prompt: str, provider: ModelProvider) -> ModelResponse:
    """Invoke external models using educational_runner"""
    try:
        from educational_runner import run_model
        
        response = run_model(model_id, prompt)
        
        if response.success:
            return ModelResponse(
                success=True,
                content=response.response_data.get("content", ""),
                model_id=model_id,
                provider=provider.value,
                processing_time_ms=response.processing_time_ms,
                tokens_used=response.usage.get("total_tokens", 0),
                finish_reason="completed"
            )
        else:
            return ModelResponse(
                success=False,
                content="",
                model_id=model_id,
                provider=provider.value,
                error_message=response.error_message,
                error_code=f"{provider.value.upper()}_ERROR"
            )
    except Exception as e:
        return ModelResponse(
            success=False,
            content="",
            model_id=model_id,
            provider=provider.value,
            error_message=str(e),
            error_code=f"{provider.value.upper()}_ERROR"
        )

def invoke_model(model_id: str, prompt: str) -> ModelResponse:
    """Unified model invocation supporting all providers"""
    provider = determine_provider(model_id)
    
    if provider == ModelProvider.AWS_BEDROCK:
        return invoke_bedrock_model(model_id, prompt)
    elif provider in [ModelProvider.OPENAI, ModelProvider.ANTHROPIC_DIRECT, ModelProvider.GOOGLE_GEMINI]:
        return invoke_external_model(model_id, prompt, provider)
    else:
        return ModelResponse(
            success=False,
            content="",
            model_id=model_id,
            provider="unknown",
            error_message=f"Unsupported provider for model: {model_id}",
            error_code="UNSUPPORTED_PROVIDER"
        )

# Keep original build_body function for backward compatibility with legacy Bedrock invocation
def build_body(model_id: str, prompt: str, *, chat: bool) -> str:
    """Legacy function for backward compatibility with existing safe_invoke calls"""
    if model_id.startswith("anthropic."):
        return json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "system": prompt,
            "messages": [{ "role": "user", "content": "Generate." }],
            "max_tokens": 800, "temperature": 0.7, "top_p": 0.9
        })
    elif model_id.startswith("amazon.titan-text"):
        return json.dumps({
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": 512,
                "temperature": 0.7,
                "topP": 0.9,
                "stopSequences": []
            }
        })
    elif model_id.startswith("mistral."):
        return json.dumps({
            "messages": [
                { "role": "system", "content": prompt },
                { "role": "user",   "content": "Generate." }
            ],
            "max_tokens": 800, "temperature": 0.7, "top_p": 0.9
        })
    else:
        return json.dumps({ "prompt": prompt })

# Legacy extract_text function for backward compatibility
def extract_text(model_id: str, payload: dict) -> str:
    """Legacy function for backward compatibility with existing Bedrock response parsing"""
    if "content"  in payload: return payload["content"][0]["text"].strip()
    if "message"  in payload: return payload["message"]["content"].strip()
    if "messages" in payload: return payload["messages"][0]["content"].strip()

    if "results" in payload:
        r0 = payload["results"][0]
        return (r0.get("text") or r0.get("generation") or
                r0.get("outputText") or r0.get("output") or
                json.dumps(r0)).strip()

    if "outputs"      in payload: return payload["outputs"][0]["text"].strip()
    if "generations"  in payload: return payload["generations"][0]["text"].strip()
    raise RuntimeError(f"Unknown response schema for {model_id}")

# ─── Bedrock invoke with exponential back-off ───────────────────────────
def safe_invoke(model_id: str, body_json: str, tag: str,
                max_retries: int = 6, base_delay: float = 0.25):
    for attempt in range(max_retries):
        try:
            return bedrock.invoke_model(
                modelId=model_id,
                body=body_json,
                contentType="application/json",
                accept="application/json"
            )
        except botocore.exceptions.ClientError as err:
            if err.response["Error"]["Code"] == "ThrottlingException":
                wait = base_delay * (2 ** attempt) + random.random() * 0.1
                log.warning("⏳  %s throttled (%s attempt %d) – sleep %.2fs",
                            model_id, tag, attempt+1, wait)
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"Throttled >{max_retries}× for model {model_id}")

# ═══════════════════════════════════════════════════════════════════════════
# DATE RANGE UTILITY
# ═══════════════════════════════════════════════════════════════════════════

def generate_date_range(start_date: str, end_date: str) -> list[str]:
    """Generate list of dates between start and end (inclusive)"""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    
    dates = []
    current = start
    while current <= end:
        dates.append(current.isoformat())
        current += timedelta(days=1)
    
    return dates

# ─── Lambda entrypoint ──────────────────────────────────────────────────
def lambda_handler(event, _ctx):
    """
    Enhanced worker handler - processes single model/date combinations
    
    Worker Mode (NEW - called by orchestrator):
    {"date": "2025-01-15", "model": "claude-3-sonnet", "worker_mode": true}
    
    Legacy Mode (fallback for backwards compatibility):
    Single date: {"date": "2025-01-15"}
    Date range:  {"start_date": "2025-01-10", "end_date": "2025-01-15"}
    Environment variables: START_DATE, END_DATE
    """
    
    try:
        # Check if this is single model worker mode (called by orchestrator)
        if event.get("worker_mode") and "model_id" in event and "date" in event:
            log.info("Running in WORKER MODE for single model/date combination")
            dates = [event["date"]]
            model_ids = [event["model_id"]]
            log.info("Processing: %s on %s", event["model_id"], event["date"])
        else:
            log.info("Running in LEGACY MODE with date range processing")
            
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
        
        prompt_ids = event.get("prompt_ids") or [f"llm_{i:02}" for i in range(1,6)]

        if not ALLOW_EMBED:
            embed_skip = [m for m in model_ids if "embed" in m.lower()]
            model_ids  = [m for m in model_ids if m not in embed_skip]
            if embed_skip:
                log.info("Skipping embedding models: %s", ", ".join(embed_skip))
        if not model_ids:
            raise ValueError("No generative models to run")

        result_map = {}
        start_time = time.time()

        # ── rolling token-budget globals ────────────────────────────────────
        global _tok_total, _tok_start
        _tok_total, _tok_start = 0, time.time()

        # Process each date
        for day in dates:
            log.info("Processing date: %s", day)
            y, m, d = day.split("-")
            
            try:
                paper_key, paper, file_existed = load_paper_json(y, m, d)
                result_map[day] = {}
                
                if file_existed:
                    log.info(f"🔍 Checking existing content for incremental processing on {day}")
                else:
                    log.info(f"🆕 Full content generation required for {day}")

                for pid in prompt_ids:
                    slot, ftype = PROMPT_TO_SLOT.get(pid, (None, None))
                    if slot is None:
                        log.warning("Unknown prompt_id %s – skipped", pid)
                        continue

                    try:
                        prompt_txt = json.loads(
                            s3_read(f"{PROMPT_ROOT}/{y}/{m}/{d}/{pid}.json"))["prompt"]
                    except Exception as e:
                        log.error("Failed to load prompt %s for %s: %s", pid, day, e)
                        continue

                    result_map[day][pid] = {}

                    for model_id in model_ids:
                        try:
                            # Check if content already exists for this model (only if file existed)
                            if file_existed:
                                mdl_key = model_id
                                slot_dict = paper["contentSlots"][slot].get("llmOutputs", {})
                                existing_content = slot_dict.get(mdl_key, {})
                                
                                # Check if meaningful content exists
                                has_content = False
                                if ftype == "title_text":
                                    has_content = (existing_content.get("title") and 
                                                 existing_content.get("text") and
                                                 len(existing_content.get("title", "").strip()) > 5 and
                                                 len(existing_content.get("text", "").strip()) > 20)
                                else:  # content type
                                    has_content = (existing_content.get("content") and
                                                 len(existing_content.get("content", "").strip()) > 20)
                                
                                if has_content:
                                    log.info(f"✅ Content already exists for {model_id} on {pid} for {day} - skipping")
                                    result_map[day][pid][model_id] = "SKIPPED: Content already exists"
                                    continue
                                else:
                                    log.info(f"🔄 Generating missing content for {model_id} on {pid} for {day}")
                            else:
                                log.info(f"🆕 New file - generating all content for {model_id} on {pid} for {day}")
                            
                            # Use unified model invocation
                            response = invoke_model(model_id, prompt_txt)
                            
                            if not response.success:
                                log.error(f"❌ Model {model_id} failed: {response.error_message}")
                                result_map[day][pid][model_id] = f"ERROR: {response.error_message}"
                                continue
                            
                            text = response.content
                            
                            # Token usage tracking
                            if response.tokens_used:
                                _tok_total += response.tokens_used
                                if time.time() - _tok_start >= 60:
                                    log.info("📊  Output-tokens last 60 s: %d", _tok_total)
                                    _tok_total, _tok_start = 0, time.time()

                            raw_key = f"results/{day}/{pid}/{slug(model_id)}.txt"
                            s3_put(raw_key, text)

                            # Use the full model ID as the key (same as image handler)
                            mdl_key = model_id
                            
                            # Store content in model-specific llmOutputs (all slots treated equally)
                            if "llmOutputs" not in paper["contentSlots"][slot]:
                                log.error(f"❌ CRITICAL: Missing llmOutputs section for slot '{slot}' - paper_content.json was created incompletely!")
                                log.error(f"Available keys in slot: {list(paper['contentSlots'][slot].keys())}")
                                raise RuntimeError(f"Missing llmOutputs section for slot '{slot}' - incomplete paper_content.json structure")
                            
                            slot_dict = paper["contentSlots"][slot]["llmOutputs"]
                            if ftype == "title_text":
                                # Split into lines and skip blank ones to find a reliable title
                                lines = [ln.strip() for ln in text.splitlines()]
                                lines = [ln for ln in lines if ln]  # remove blanks
                                if not lines:
                                    lines = [text.strip()]

                                # If the first non-blank line is just an opening brace we was a placeholder title
                                if lines[0].strip().startswith('{'):
                                    title_line = "AI League Table Top 5 Models and their Secret Powers"
                                else:
                                    title_line = lines[0][:200]  # cap length just in case
                                body_html = "<p>" + "\n".join(lines[1:]).strip() + "</p>" if len(lines) > 1 else "<p></p>"

                                slot_dict[mdl_key] = {
                                    "title": title_line,
                                    "text":  body_html
                                }
                            else:
                                slot_dict[mdl_key] = { "content": f"<p>{text}</p>" }

                            result_map[day][pid][model_id] = raw_key
                            log.info(f"✅ Generated {ftype} content for {model_id} on {pid}")
                            
                        except Exception as e:
                            log.error("❌ Failed to process %s for %s on %s: %s", 
                                      model_id, pid, day, e)
                            result_map[day][pid][model_id] = f"ERROR: {str(e)}"
                            continue

                save_paper_json(paper_key, paper)
                log.info("✅ Completed processing for %s", day)
                
            except Exception as e:
                log.error("❌ Failed to process date %s: %s", day, e)
                result_map[day] = {"error": str(e)}
                continue

        processing_time = time.time() - start_time
        successful_dates = [d for d in result_map.keys() if "error" not in result_map[d]]
        
        # Worker mode returns success/failure based on actual results
        if event.get("worker_mode"):
            # Count successful vs failed prompts
            successful_prompts = 0
            failed_prompts = 0
            total_expected = len(prompt_ids) * len(model_ids) * len(dates)
            
            for day_results in result_map.values():
                if "error" in day_results:
                    failed_prompts += len(prompt_ids) * len(model_ids)
                    continue
                    
                for pid_results in day_results.values():
                    for model_result in pid_results.values():
                        if str(model_result).startswith("ERROR"):
                            failed_prompts += 1
                        elif str(model_result).startswith("SKIPPED"):
                            # Skipped content counts as success if content already exists
                            successful_prompts += 1
                        else:
                            successful_prompts += 1
            
            # Determine if worker should report success or failure
            success_rate = successful_prompts / total_expected if total_expected > 0 else 0
            
            # Fail if less than 80% of expected content was generated/existed
            if success_rate < 0.8:
                return {
                    "statusCode": 500,
                    "body": json.dumps({
                        "status": "error",
                        "error": f"Low success rate: {successful_prompts}/{total_expected} ({success_rate:.1%}) successful",
                        "prompts_processed": successful_prompts,
                        "prompts_failed": failed_prompts,
                        "success_rate": round(success_rate * 100, 1),
                        "processing_time": round(processing_time, 2),
                        "model": model_ids[0] if len(model_ids) == 1 else model_ids,
                        "date": dates[0] if len(dates) == 1 else dates
                    })
                }
            else:
                return {
                    "statusCode": 200,
                    "body": json.dumps({
                        "status": "success",
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
                "dates_processed": len(successful_dates),
                "dates_failed": len(dates) - len(successful_dates),
                "total_dates": len(dates),
                "prompt_ids": prompt_ids,
                "models_used": model_ids,
                "result_map": result_map
            })
        }
        
    except Exception as e:
        log.error("LLM generation failed: %s", str(e))
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "error",
                "error": str(e),
                "model": event.get("model", "unknown"),
                "date": event.get("date", "unknown")
            })
        }
