#!/usr/bin/env python3
"""
CraicGPT Educational Model Runner - Phase 0
==========================================

EDUCATIONAL PURPOSE:
Universal model runner supporting multiple providers with clear educational structure.
Shows how to handle different APIs and authentication methods.

SUPPORTED PROVIDERS:
- AWS Bedrock (current Phase 0)
- OpenAI (new Phase 0 addition)
- Anthropic Direct (new Phase 0 addition)
- Google Gemini (new Phase 0 addition)

LEARNING OBJECTIVES:
1. Understand different API authentication patterns
2. See how to handle various response formats
3. Learn error handling across providers
4. Practice with real model integrations
"""

import os
import json
import logging
import time
import base64
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass
from enum import Enum

# Educational imports - clearly show what each provider needs
try:
    import boto3  # AWS Bedrock
    from botocore.config import Config
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False
    logging.warning("boto3 not available - Bedrock models disabled")

try:
    import requests  # OpenAI, Anthropic, Gemini
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    logging.warning("requests not available - External APIs disabled")

# Import our educational configurations
from model_configurations import (
    ModelProvider, ModelCapability, ModelConfig,
    get_educational_model_configs, get_available_models
)

logger = logging.getLogger(__name__)

# ====================================
# EDUCATIONAL RESPONSE CLASSES
# ====================================

@dataclass
class ModelResponse:
    """
    Educational response class showing standardized output format.
    All providers return this format for consistency.
    """
    success: bool
    content: str
    model_used: str
    provider: str
    
    # Educational metadata
    tokens_used: Optional[int] = None
    processing_time_ms: Optional[int] = None
    finish_reason: Optional[str] = None
    
    # Provider-specific data
    raw_response: Optional[Dict[str, Any]] = None
    
    # Error information
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    
    # Educational metrics
    educational_notes: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.educational_notes is None:
            self.educational_notes = {}

# ====================================
# EDUCATIONAL API HANDLERS
# ====================================

class BedrockHandler:
    """
    Educational AWS Bedrock handler.
    Shows how to work with AWS services and IAM authentication.
    """
    
    def __init__(self, region: str = "us-east-1"):
        if not HAS_BOTO3:
            raise ImportError("boto3 required for Bedrock - install with: pip install boto3")
        
        self.region = region
        self.logger = logging.getLogger(f"{__name__}.BedrockHandler")
        
        # Educational: Show Bedrock client configuration
        config = Config(
            region_name=region,
            retries={'max_attempts': 3, 'mode': 'adaptive'},
            max_pool_connections=50
        )
        
        self.bedrock_runtime = boto3.client('bedrock-runtime', config=config)
        self.logger.info(f"Initialized Bedrock client for region: {region}")
    
    def invoke_text_model(self, model_config: ModelConfig, prompt: str) -> ModelResponse:
        """
        Educational method: Invoke Bedrock text model.
        Shows how to handle different Bedrock model formats.
        """
        self.logger.info(f"Invoking Bedrock text model: {model_config.model_id}")
        start_time = time.time()
        
        try:
            # Educational: Different models need different request formats
            if "anthropic.claude" in model_config.model_id:
                request_body = self._build_claude_request(model_config, prompt)
            elif "amazon.titan-text" in model_config.model_id:
                request_body = self._build_titan_text_request(model_config, prompt)
            else:
                raise ValueError(f"Unsupported Bedrock text model: {model_config.model_id}")
            
            # Educational: Show Bedrock invoke_model API
            response = self.bedrock_runtime.invoke_model(
                modelId=model_config.model_id,
                body=json.dumps(request_body),
                contentType="application/json",
                accept="application/json"
            )
            
            # Educational: Parse response
            response_body = json.loads(response['body'].read())
            processing_time = int((time.time() - start_time) * 1000)
            
            # Educational: Extract content based on model type
            if "anthropic.claude" in model_config.model_id:
                content = response_body['content'][0]['text']
                tokens_used = response_body['usage']['output_tokens']
                finish_reason = response_body.get('stop_reason', 'completed')
            elif "amazon.titan-text" in model_config.model_id:
                content = response_body['results'][0]['outputText']
                tokens_used = response_body['inputTextTokenCount'] + response_body['results'][0]['tokenCount']
                finish_reason = response_body['results'][0].get('completionReason', 'FINISHED')
            
            return ModelResponse(
                success=True,
                content=content,
                model_used=model_config.model_id,
                provider="bedrock",
                tokens_used=tokens_used,
                processing_time_ms=processing_time,
                finish_reason=finish_reason,
                raw_response=response_body,
                educational_notes={
                    "api_pattern": "AWS Bedrock InvokeModel",
                    "authentication": "IAM role/credentials",
                    "request_format": "JSON body with model-specific schema"
                }
            )
            
        except Exception as e:
            self.logger.error(f"Bedrock text model error: {e}")
            return ModelResponse(
                success=False,
                content="",
                model_used=model_config.model_id,
                provider="bedrock",
                error_message=str(e),
                error_code="BEDROCK_ERROR",
                educational_notes={
                    "error_type": "Bedrock API error",
                    "troubleshooting": "Check IAM permissions, model availability, request format"
                }
            )
    
    def invoke_image_model(self, model_config: ModelConfig, prompt: str) -> ModelResponse:
        """
        Educational method: Invoke Bedrock image model.
        Shows how to handle image generation APIs.
        """
        self.logger.info(f"Invoking Bedrock image model: {model_config.model_id}")
        start_time = time.time()
        
        try:
            # Educational: Image models have different request formats
            if "amazon.titan-image" in model_config.model_id:
                request_body = self._build_titan_image_request(model_config, prompt)
            elif "amazon.nova-canvas" in model_config.model_id:
                request_body = self._build_nova_canvas_request(model_config, prompt)
            else:
                raise ValueError(f"Unsupported Bedrock image model: {model_config.model_id}")
            
            response = self.bedrock_runtime.invoke_model(
                modelId=model_config.model_id,
                body=json.dumps(request_body),
                contentType="application/json",
                accept="application/json"
            )
            
            response_body = json.loads(response['body'].read())
            processing_time = int((time.time() - start_time) * 1000)
            
            # Educational: Extract base64 image data
            if "amazon.titan-image" in model_config.model_id:
                image_data = response_body['images'][0]
            elif "amazon.nova-canvas" in model_config.model_id:
                image_data = response_body['images'][0]['data']
            
            return ModelResponse(
                success=True,
                content=image_data,  # Base64 encoded image
                model_used=model_config.model_id,
                provider="bedrock",
                processing_time_ms=processing_time,
                finish_reason="completed",
                raw_response=response_body,
                educational_notes={
                    "api_pattern": "AWS Bedrock InvokeModel",
                    "response_format": "Base64 encoded image data",
                    "storage_note": "Save to S3 or convert to image file"
                }
            )
            
        except Exception as e:
            self.logger.error(f"Bedrock image model error: {e}")
            return ModelResponse(
                success=False,
                content="",
                model_used=model_config.model_id,
                provider="bedrock",
                error_message=str(e),
                error_code="BEDROCK_IMAGE_ERROR"
            )
    
    def _build_claude_request(self, config: ModelConfig, prompt: str) -> Dict[str, Any]:
        """Educational: Build Anthropic Claude request for Bedrock"""
        return {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "top_p": config.top_p,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
    
    def _build_titan_text_request(self, config: ModelConfig, prompt: str) -> Dict[str, Any]:
        """Educational: Build Amazon Titan Text request"""
        return {
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": config.max_tokens,
                "temperature": config.temperature,
                "topP": config.top_p,
                "stopSequences": []
            }
        }
    
    def _build_titan_image_request(self, config: ModelConfig, prompt: str) -> Dict[str, Any]:
        """Educational: Build Amazon Titan Image request"""
        return {
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {
                "text": prompt,
                "height": int(config.image_size.split('x')[1]),
                "width": int(config.image_size.split('x')[0])
            },
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "height": int(config.image_size.split('x')[1]),
                "width": int(config.image_size.split('x')[0]),
                "cfgScale": 8.0
            }
        }
    
    def _build_nova_canvas_request(self, config: ModelConfig, prompt: str) -> Dict[str, Any]:
        """Educational: Build Amazon Nova Canvas request"""
        return {
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {
                "text": prompt,
                "height": int(config.image_size.split('x')[1]),
                "width": int(config.image_size.split('x')[0])
            },
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "height": int(config.image_size.split('x')[1]),
                "width": int(config.image_size.split('x')[0]),
                "cfgScale": 7.0,
                "seed": 42
            }
        }

class OpenAIHandler:
    """
    Educational OpenAI handler.
    Shows how to work with REST APIs and API key authentication.
    """
    
    def __init__(self):
        if not HAS_REQUESTS:
            raise ImportError("requests required for OpenAI - install with: pip install requests")
        
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable required")
        
        self.logger = logging.getLogger(f"{__name__}.OpenAIHandler")
        self.logger.info("Initialized OpenAI handler")
    
    def invoke_text_model(self, model_config: ModelConfig, prompt: str) -> ModelResponse:
        """
        Educational method: Invoke OpenAI text model.
        Shows how to use the Chat Completions API.
        """
        self.logger.info(f"Invoking OpenAI text model: {model_config.model_id}")
        start_time = time.time()
        
        try:
            # Educational: OpenAI uses messages format
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # Educational: Build OpenAI request
            request_body = {
                "model": model_config.model_id,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": config.temperature,
                "max_tokens": config.max_tokens,
                "top_p": config.top_p,
                "presence_penalty": config.presence_penalty,
                "frequency_penalty": config.frequency_penalty
            }
            
            # Educational: Show HTTP POST request
            response = requests.post(
                model_config.api_endpoint,
                headers=headers,
                json=request_body,
                timeout=60
            )
            
            processing_time = int((time.time() - start_time) * 1000)
            
            if response.status_code == 200:
                response_data = response.json()
                
                # Educational: Extract OpenAI response format
                content = response_data['choices'][0]['message']['content']
                tokens_used = response_data['usage']['total_tokens']
                finish_reason = response_data['choices'][0]['finish_reason']
                
                return ModelResponse(
                    success=True,
                    content=content,
                    model_used=model_config.model_id,
                    provider="openai",
                    tokens_used=tokens_used,
                    processing_time_ms=processing_time,
                    finish_reason=finish_reason,
                    raw_response=response_data,
                    educational_notes={
                        "api_pattern": "OpenAI Chat Completions API",
                        "authentication": "Bearer token in Authorization header",
                        "request_format": "JSON with messages array"
                    }
                )
            else:
                error_data = response.json() if response.content else {}
                error_message = error_data.get('error', {}).get('message', f"HTTP {response.status_code}")
                
                return ModelResponse(
                    success=False,
                    content="",
                    model_used=model_config.model_id,
                    provider="openai",
                    error_message=error_message,
                    error_code=f"OPENAI_HTTP_{response.status_code}"
                )
                
        except Exception as e:
            self.logger.error(f"OpenAI text model error: {e}")
            return ModelResponse(
                success=False,
                content="",
                model_used=model_config.model_id,
                provider="openai",
                error_message=str(e),
                error_code="OPENAI_ERROR"
            )
    
    def invoke_image_model(self, model_config: ModelConfig, prompt: str) -> ModelResponse:
        """
        Educational method: Invoke OpenAI image model.
        Shows how to use the Images API.
        """
        self.logger.info(f"Invoking OpenAI image model: {model_config.model_id}")
        start_time = time.time()
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # Educational: DALL-E 3 request format
            request_body = {
                "model": model_config.model_id,
                "prompt": prompt,
                "n": 1,
                "size": config.image_size,
                "quality": config.image_quality,
                "response_format": "b64_json"  # Get base64 for consistency
            }
            
            if config.image_style:
                request_body["style"] = config.image_style
            
            response = requests.post(
                model_config.api_endpoint,
                headers=headers,
                json=request_body,
                timeout=120  # Images take longer
            )
            
            processing_time = int((time.time() - start_time) * 1000)
            
            if response.status_code == 200:
                response_data = response.json()
                image_data = response_data['data'][0]['b64_json']
                
                return ModelResponse(
                    success=True,
                    content=image_data,
                    model_used=model_config.model_id,
                    provider="openai",
                    processing_time_ms=processing_time,
                    finish_reason="completed",
                    raw_response=response_data,
                    educational_notes={
                        "api_pattern": "OpenAI Images API",
                        "response_format": "Base64 encoded image",
                        "special_features": "Style control, quality options"
                    }
                )
            else:
                error_data = response.json() if response.content else {}
                error_message = error_data.get('error', {}).get('message', f"HTTP {response.status_code}")
                
                return ModelResponse(
                    success=False,
                    content="",
                    model_used=model_config.model_id,
                    provider="openai",
                    error_message=error_message,
                    error_code=f"OPENAI_IMAGE_HTTP_{response.status_code}"
                )
                
        except Exception as e:
            self.logger.error(f"OpenAI image model error: {e}")
            return ModelResponse(
                success=False,
                content="",
                model_used=model_config.model_id,
                provider="openai",
                error_message=str(e),
                error_code="OPENAI_IMAGE_ERROR"
            )

class AnthropicHandler:
    """
    Educational Anthropic direct API handler.
    Shows how to use Anthropic's direct API vs Bedrock.
    """
    
    def __init__(self):
        if not HAS_REQUESTS:
            raise ImportError("requests required for Anthropic - install with: pip install requests")
        
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable required")
        
        self.logger = logging.getLogger(f"{__name__}.AnthropicHandler")
        self.logger.info("Initialized Anthropic handler")
    
    def invoke_text_model(self, model_config: ModelConfig, prompt: str) -> ModelResponse:
        """
        Educational method: Invoke Anthropic direct API.
        Shows differences from Bedrock implementation.
        """
        self.logger.info(f"Invoking Anthropic model: {model_config.model_id}")
        start_time = time.time()
        
        try:
            # Educational: Anthropic API headers
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": config.anthropic_version,
                "content-type": "application/json"
            }
            
            # Educational: Anthropic Messages API format
            request_body = {
                "model": model_config.model_id,
                "max_tokens": config.max_tokens,
                "temperature": config.temperature,
                "top_p": config.top_p,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }
            
            response = requests.post(
                model_config.api_endpoint,
                headers=headers,
                json=request_body,
                timeout=60
            )
            
            processing_time = int((time.time() - start_time) * 1000)
            
            if response.status_code == 200:
                response_data = response.json()
                
                # Educational: Anthropic response format
                content = response_data['content'][0]['text']
                tokens_used = response_data['usage']['output_tokens']
                finish_reason = response_data.get('stop_reason', 'end_turn')
                
                return ModelResponse(
                    success=True,
                    content=content,
                    model_used=model_config.model_id,
                    provider="anthropic",
                    tokens_used=tokens_used,
                    processing_time_ms=processing_time,
                    finish_reason=finish_reason,
                    raw_response=response_data,
                    educational_notes={
                        "api_pattern": "Anthropic Messages API",
                        "authentication": "x-api-key header",
                        "advantages": "Direct API access, latest features first",
                        "vs_bedrock": "More features but requires API key management"
                    }
                )
            else:
                error_data = response.json() if response.content else {}
                error_message = error_data.get('error', {}).get('message', f"HTTP {response.status_code}")
                
                return ModelResponse(
                    success=False,
                    content="",
                    model_used=model_config.model_id,
                    provider="anthropic",
                    error_message=error_message,
                    error_code=f"ANTHROPIC_HTTP_{response.status_code}"
                )
                
        except Exception as e:
            self.logger.error(f"Anthropic model error: {e}")
            return ModelResponse(
                success=False,
                content="",
                model_used=model_config.model_id,
                provider="anthropic",
                error_message=str(e),
                error_code="ANTHROPIC_ERROR"
            )

class GeminiHandler:
    """
    Educational Google Gemini handler.
    Shows how to work with Google AI APIs.
    """
    
    def __init__(self):
        if not HAS_REQUESTS:
            raise ImportError("requests required for Gemini - install with: pip install requests")
        
        self.api_key = os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY environment variable required")
        
        self.logger = logging.getLogger(f"{__name__}.GeminiHandler")
        self.logger.info("Initialized Gemini handler")
    
    def invoke_text_model(self, model_config: ModelConfig, prompt: str) -> ModelResponse:
        """
        Educational method: Invoke Google Gemini model.
        Shows Google AI API patterns.
        """
        self.logger.info(f"Invoking Gemini model: {model_config.model_id}")
        start_time = time.time()
        
        try:
            # Educational: Google API uses query parameter for API key
            url = f"{model_config.api_endpoint}?key={self.api_key}"
            
            headers = {
                "Content-Type": "application/json"
            }
            
            # Educational: Gemini request format
            request_body = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt}
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": config.temperature,
                    "topP": config.top_p,
                    "topK": config.top_k or 40,
                    "maxOutputTokens": config.max_tokens
                }
            }
            
            response = requests.post(
                url,
                headers=headers,
                json=request_body,
                timeout=60
            )
            
            processing_time = int((time.time() - start_time) * 1000)
            
            if response.status_code == 200:
                response_data = response.json()
                
                # Educational: Gemini response format
                content = response_data['candidates'][0]['content']['parts'][0]['text']
                finish_reason = response_data['candidates'][0].get('finishReason', 'STOP')
                
                # Educational: Gemini doesn't always provide token counts
                tokens_used = None
                usage_metadata = response_data.get('usageMetadata')
                if usage_metadata:
                    tokens_used = usage_metadata.get('totalTokenCount')
                
                return ModelResponse(
                    success=True,
                    content=content,
                    model_used=model_config.model_id,
                    provider="gemini",
                    tokens_used=tokens_used,
                    processing_time_ms=processing_time,
                    finish_reason=finish_reason,
                    raw_response=response_data,
                    educational_notes={
                        "api_pattern": "Google AI REST API",
                        "authentication": "API key as query parameter",
                        "request_format": "Contents array with parts",
                        "special_features": "Integration with Google services"
                    }
                )
            else:
                error_data = response.json() if response.content else {}
                error_message = error_data.get('error', {}).get('message', f"HTTP {response.status_code}")
                
                return ModelResponse(
                    success=False,
                    content="",
                    model_used=model_config.model_id,
                    provider="gemini",
                    error_message=error_message,
                    error_code=f"GEMINI_HTTP_{response.status_code}"
                )
                
        except Exception as e:
            self.logger.error(f"Gemini model error: {e}")
            return ModelResponse(
                success=False,
                content="",
                model_used=model_config.model_id,
                provider="gemini",
                error_message=str(e),
                error_code="GEMINI_ERROR"
            )

# ====================================
# EDUCATIONAL UNIFIED RUNNER
# ====================================

class EducationalModelRunner:
    """
    Educational unified model runner.
    Shows how to handle multiple providers through a single interface.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.ModelRunner")
        self.configs = get_educational_model_configs()
        
        # Educational: Initialize handlers based on availability
        self.handlers = {}
        
        if HAS_BOTO3:
            try:
                self.handlers[ModelProvider.AWS_BEDROCK] = BedrockHandler()
                self.logger.info("✅ Bedrock handler initialized")
            except Exception as e:
                self.logger.warning(f"❌ Bedrock handler failed: {e}")
        
        if HAS_REQUESTS and os.getenv("OPENAI_API_KEY"):
            try:
                self.handlers[ModelProvider.OPENAI] = OpenAIHandler()
                self.logger.info("✅ OpenAI handler initialized")
            except Exception as e:
                self.logger.warning(f"❌ OpenAI handler failed: {e}")
        
        if HAS_REQUESTS and os.getenv("ANTHROPIC_API_KEY"):
            try:
                self.handlers[ModelProvider.ANTHROPIC_DIRECT] = AnthropicHandler()
                self.logger.info("✅ Anthropic handler initialized")
            except Exception as e:
                self.logger.warning(f"❌ Anthropic handler failed: {e}")
        
        if HAS_REQUESTS and os.getenv("GOOGLE_API_KEY"):
            try:
                self.handlers[ModelProvider.GOOGLE_GEMINI] = GeminiHandler()
                self.logger.info("✅ Gemini handler initialized")
            except Exception as e:
                self.logger.warning(f"❌ Gemini handler failed: {e}")
        
        self.logger.info(f"Initialized {len(self.handlers)} model handlers")
    
    def invoke_model(self, model_name: str, prompt: str) -> ModelResponse:
        """
        Educational method: Invoke any model by name.
        Shows unified interface across all providers.
        """
        self.logger.info(f"Invoking model: {model_name}")
        
        if model_name not in self.configs:
            return ModelResponse(
                success=False,
                content="",
                model_used=model_name,
                provider="unknown",
                error_message=f"Unknown model: {model_name}",
                error_code="UNKNOWN_MODEL"
            )
        
        config = self.configs[model_name]
        
        if config.provider not in self.handlers:
            return ModelResponse(
                success=False,
                content="",
                model_used=model_name,
                provider=config.provider.value,
                error_message=f"Handler not available for provider: {config.provider.value}",
                error_code="HANDLER_NOT_AVAILABLE",
                educational_notes={
                    "troubleshooting": f"Check {config.provider.value} dependencies and configuration"
                }
            )
        
        handler = self.handlers[config.provider]
        
        # Educational: Route to appropriate method based on capability
        try:
            if config.capability == ModelCapability.TEXT_GENERATION:
                return handler.invoke_text_model(config, prompt)
            elif config.capability == ModelCapability.IMAGE_GENERATION:
                return handler.invoke_image_model(config, prompt)
            elif config.capability == ModelCapability.MULTIMODAL:
                # Educational: For now, treat multimodal as text
                # In Phase 1, we'll add proper multimodal handling
                return handler.invoke_text_model(config, prompt)
            else:
                return ModelResponse(
                    success=False,
                    content="",
                    model_used=model_name,
                    provider=config.provider.value,
                    error_message=f"Unsupported capability: {config.capability.value}",
                    error_code="UNSUPPORTED_CAPABILITY"
                )
        except Exception as e:
            self.logger.error(f"Model invocation error: {e}")
            return ModelResponse(
                success=False,
                content="",
                model_used=model_name,
                provider=config.provider.value,
                error_message=str(e),
                error_code="INVOCATION_ERROR"
            )
    
    def get_available_models(self) -> List[str]:
        """Educational method: Get list of available models"""
        available = []
        for name, config in self.configs.items():
            if config.provider in self.handlers:
                available.append(name)
        return available
    
    def get_educational_info(self) -> Dict[str, Any]:
        """Educational method: Get information about the runner"""
        return {
            "total_models": len(self.configs),
            "available_models": len(self.get_available_models()),
            "providers_available": [p.value for p in self.handlers.keys()],
            "providers_configured": [p.value for p in ModelProvider],
            "capabilities_supported": [c.value for c in ModelCapability],
            "educational_features": {
                "unified_interface": "Single invoke_model() method for all providers",
                "error_handling": "Standardized error responses across providers",
                "metadata": "Educational notes in all responses",
                "monitoring": "Processing time and token usage tracking"
            }
        }

# Educational testing function
def test_educational_runner():
    """Educational function to test the model runner"""
    print("=== Testing Educational Model Runner ===")
    
    runner = EducationalModelRunner()
    
    # Show educational info
    info = runner.get_educational_info()
    print(f"\nRunner info:")
    print(json.dumps(info, indent=2))
    
    # Test available models
    available = runner.get_available_models()
    print(f"\nAvailable models: {len(available)}")
    for model in available[:5]:  # Show first 5
        print(f"  - {model}")
    
    # Test a simple text prompt if any models are available
    if available:
        test_model = available[0]
        print(f"\nTesting model: {test_model}")
        
        response = runner.invoke_model(test_model, "Hello, this is a test prompt.")
        print(f"Success: {response.success}")
        if response.success:
            print(f"Content length: {len(response.content)}")
            print(f"Provider: {response.provider}")
            print(f"Tokens used: {response.tokens_used}")
            print(f"Processing time: {response.processing_time_ms}ms")
        else:
            print(f"Error: {response.error_message}")

if __name__ == "__main__":
    test_educational_runner()