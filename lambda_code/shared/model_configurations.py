#!/usr/bin/env python3
"""
CraicGPT Model Configurations - Educational Phase 0
==================================================

EDUCATIONAL PURPOSE:
Centralized model configuration for all CraicGPT services.
Shows how to handle multiple model providers with different APIs.

SUPPORTED PROVIDERS:
- AWS Bedrock (Phase 0 - current)
- OpenAI (Phase 0 - addition)
- Anthropic Direct (Phase 0 - addition)  
- Google Gemini (Phase 0 - addition)

LEARNING OBJECTIVES:
1. Understand different API patterns
2. See how to handle authentication
3. Learn about model-specific parameters
4. Practice error handling across providers
"""

import os
import json
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union

logger = logging.getLogger(__name__)

class ModelProvider(Enum):
    """Educational enum for different model providers"""
    AWS_BEDROCK = "bedrock"
    OPENAI = "openai"
    ANTHROPIC_DIRECT = "anthropic"
    GOOGLE_GEMINI = "gemini"

class ModelCapability(Enum):
    """Educational enum for model capabilities"""
    TEXT_GENERATION = "text"
    IMAGE_GENERATION = "image"
    MULTIMODAL = "multimodal"

@dataclass
class ModelConfig:
    """
    Educational model configuration class.
    Shows all parameters needed for different providers.
    """
    # Basic identification
    provider: ModelProvider
    model_id: str
    display_name: str
    capability: ModelCapability
    
    # Prompt engineering parameters
    temperature: float = 0.7
    max_tokens: int = 500
    top_p: float = 0.9
    top_k: Optional[int] = None
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    
    # API configuration
    api_endpoint: Optional[str] = None
    requires_api_key: bool = False
    api_key_env_var: Optional[str] = None
    
    # Provider-specific settings
    bedrock_region: str = "us-east-1"
    openai_organization: Optional[str] = None
    anthropic_version: str = "2023-06-01"
    gemini_project_id: Optional[str] = None
    
    # Image-specific parameters
    image_size: str = "512x512"
    image_quality: str = "standard"
    image_style: Optional[str] = None
    
    # Rate limiting
    requests_per_minute: int = 60
    tokens_per_minute: int = 10000
    
    # Educational metadata
    educational_notes: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        """Educational validation"""
        if self.temperature < 0.0 or self.temperature > 2.0:
            raise ValueError(f"Temperature must be 0.0-2.0, got {self.temperature}")
        # Only validate max_tokens for text models; image models can have max_tokens=0
        if self.capability == ModelCapability.TEXT_GENERATION and self.max_tokens < 1:
            raise ValueError(f"Max tokens must be positive for text models, got {self.max_tokens}")
        if self.top_p < 0.0 or self.top_p > 1.0:
            raise ValueError(f"Top-p must be 0.0-1.0, got {self.top_p}")

def get_educational_model_configs() -> Dict[str, ModelConfig]:
    """
    Educational function returning all model configurations.
    Each model shows different API patterns and parameters.
    """
    
    configs = {}
    
    # ====================================
    # AWS BEDROCK MODELS (Phase 0 Current)
    # ====================================
    
    # Educational: Anthropic Claude via Bedrock
    configs["claude-3-sonnet-bedrock"] = ModelConfig(
        provider=ModelProvider.AWS_BEDROCK,
        model_id="anthropic.claude-3-sonnet-20240229-v1:0",
        display_name="Claude 3 Sonnet (AWS Bedrock)",
        capability=ModelCapability.TEXT_GENERATION,
        temperature=0.7,
        max_tokens=1000,
        top_p=0.9,
        bedrock_region="us-east-1",
        educational_notes={
            "use_case": "Balanced reasoning and creativity",
            "best_for": "Articles, analysis, technical content",
            "api_pattern": "AWS Bedrock InvokeModel",
            "prompt_format": "Anthropic Messages API format"
        }
    )
    
    configs["claude-3-haiku-bedrock"] = ModelConfig(
        provider=ModelProvider.AWS_BEDROCK,
        model_id="anthropic.claude-3-haiku-20240307-v1:0",
        display_name="Claude 3 Haiku (AWS Bedrock)",
        capability=ModelCapability.TEXT_GENERATION,
        temperature=0.6,
        max_tokens=500,
        top_p=0.8,
        bedrock_region="us-east-1",
        educational_notes={
            "use_case": "Fast, efficient responses",
            "best_for": "Quick content, summaries, short responses",
            "api_pattern": "AWS Bedrock InvokeModel",
            "cost_efficiency": "Lower cost, faster response"
        }
    )
    
    # Educational: Amazon Titan Text
    configs["titan-text"] = ModelConfig(
        provider=ModelProvider.AWS_BEDROCK,
        model_id="amazon.titan-text-express-v1",
        display_name="Amazon Titan Text Express",
        capability=ModelCapability.TEXT_GENERATION,
        temperature=0.8,
        max_tokens=800,
        top_p=0.9,
        bedrock_region="us-east-1",
        educational_notes={
            "use_case": "General text generation",
            "best_for": "Creative writing, varied content",
            "api_pattern": "AWS Bedrock InvokeModel",
            "prompt_format": "Simple text prompt"
        }
    )
    
    # Educational: Amazon image models
    configs["titan-image"] = ModelConfig(
        provider=ModelProvider.AWS_BEDROCK,
        model_id="amazon.titan-image-generator-v1",
        display_name="Amazon Titan Image Generator",
        capability=ModelCapability.IMAGE_GENERATION,
        temperature=0.0,  # Images don't use temperature
        max_tokens=0,
        top_p=0.0,
        image_size="512x512",
        image_quality="standard",
        bedrock_region="us-east-1",
        educational_notes={
            "use_case": "Text-to-image generation",
            "best_for": "General illustrations, content images",
            "api_pattern": "AWS Bedrock InvokeModel",
            "prompt_format": "Text description with optional parameters"
        }
    )
    
    configs["nova-canvas"] = ModelConfig(
        provider=ModelProvider.AWS_BEDROCK,
        model_id="amazon.nova-canvas-v1:0",
        display_name="Amazon Nova Canvas",
        capability=ModelCapability.IMAGE_GENERATION,
        temperature=0.0,
        max_tokens=0,
        top_p=0.0,
        image_size="512x512",
        image_quality="high",
        bedrock_region="us-east-1",
        educational_notes={
            "use_case": "Advanced image generation",
            "best_for": "High-quality illustrations, artistic content",
            "api_pattern": "AWS Bedrock InvokeModel",
            "quality": "Higher quality than Titan"
        }
    )
    
    # ====================================
    # OPENAI MODELS (Phase 0 Addition)
    # ====================================
    
    configs["gpt-4"] = ModelConfig(
        provider=ModelProvider.OPENAI,
        model_id="gpt-4",
        display_name="GPT-4 (OpenAI)",
        capability=ModelCapability.TEXT_GENERATION,
        temperature=0.7,
        max_tokens=1500,
        top_p=0.9,
        presence_penalty=0.1,
        frequency_penalty=0.1,
        api_endpoint="https://api.openai.com/v1/chat/completions",
        requires_api_key=True,
        api_key_env_var="OPENAI_API_KEY",
        requests_per_minute=60,
        tokens_per_minute=10000,
        educational_notes={
            "use_case": "Advanced reasoning and coding",
            "best_for": "Complex analysis, technical content, creative writing",
            "api_pattern": "OpenAI Chat Completions API",
            "prompt_format": "Messages array with system/user/assistant roles",
            "special_features": "Function calling, JSON mode"
        }
    )
    
    configs["o3-mini"] = ModelConfig(
        provider=ModelProvider.OPENAI,
        model_id="o3-mini",
        display_name="O3 Mini (OpenAI)",
        capability=ModelCapability.TEXT_GENERATION,
        temperature=0.8,
        max_tokens=1000,
        top_p=0.95,
        presence_penalty=0.2,
        frequency_penalty=0.2,
        api_endpoint="https://api.openai.com/v1/chat/completions",
        requires_api_key=True,
        api_key_env_var="OPENAI_API_KEY",
        requests_per_minute=100,
        tokens_per_minute=15000,
        educational_notes={
            "use_case": "Reasoning-focused model",
            "best_for": "Problem solving, analysis, logical reasoning",
            "api_pattern": "OpenAI Chat Completions API",
            "special_features": "Enhanced reasoning capabilities",
            "note": "Newer model with improved reasoning"
        }
    )
    
    configs["dall-e-3"] = ModelConfig(
        provider=ModelProvider.OPENAI,
        model_id="dall-e-3",
        display_name="DALL-E 3 (OpenAI)",
        capability=ModelCapability.IMAGE_GENERATION,
        temperature=0.0,
        max_tokens=0,
        top_p=0.0,
        image_size="1024x1024",
        image_quality="hd",
        image_style="natural",
        api_endpoint="https://api.openai.com/v1/images/generations",
        requires_api_key=True,
        api_key_env_var="OPENAI_API_KEY",
        requests_per_minute=5,  # Lower for image generation
        educational_notes={
            "use_case": "High-quality image generation",
            "best_for": "Artistic content, detailed illustrations",
            "api_pattern": "OpenAI Images API",
            "prompt_format": "Text description",
            "special_features": "Style control, high resolution options"
        }
    )
    
    # ====================================
    # ANTHROPIC DIRECT MODELS
    # ====================================
    
    configs["claude-3-opus"] = ModelConfig(
        provider=ModelProvider.ANTHROPIC_DIRECT,
        model_id="claude-3-opus-20240229",
        display_name="Claude 3 Opus (Anthropic Direct)",
        capability=ModelCapability.TEXT_GENERATION,
        temperature=0.7,
        max_tokens=4000,
        top_p=0.9,
        api_endpoint="https://api.anthropic.com/v1/messages",
        requires_api_key=True,
        api_key_env_var="ANTHROPIC_API_KEY",
        anthropic_version="2023-06-01",
        requests_per_minute=50,
        tokens_per_minute=40000,
        educational_notes={
            "use_case": "Most capable Anthropic model",
            "best_for": "Complex reasoning, analysis, creative tasks",
            "api_pattern": "Anthropic Messages API",
            "prompt_format": "Messages array with role/content",
            "advantages": "Direct API access, latest features first"
        }
    )
    
    # Educational: Latest Claude model with image capabilities
    configs["claude-3-5-sonnet"] = ModelConfig(
        provider=ModelProvider.ANTHROPIC_DIRECT,
        model_id="claude-3-5-sonnet-20241022",
        display_name="Claude 3.5 Sonnet Latest (Anthropic)",
        capability=ModelCapability.MULTIMODAL,
        temperature=0.7,
        max_tokens=2000,
        top_p=0.9,
        api_endpoint="https://api.anthropic.com/v1/messages",
        requires_api_key=True,
        api_key_env_var="ANTHROPIC_API_KEY",
        anthropic_version="2023-06-01",
        requests_per_minute=60,
        tokens_per_minute=20000,
        educational_notes={
            "use_case": "Latest Anthropic model with vision",
            "best_for": "Text and image understanding, analysis",
            "api_pattern": "Anthropic Messages API",
            "special_features": "Vision capabilities, latest improvements",
            "note": "Can process both text and images"
        }
    )
    
    # ====================================
    # GOOGLE GEMINI MODELS
    # ====================================
    
    configs["gemini-pro"] = ModelConfig(
        provider=ModelProvider.GOOGLE_GEMINI,
        model_id="gemini-pro",
        display_name="Gemini Pro (Google)",
        capability=ModelCapability.TEXT_GENERATION,
        temperature=0.7,
        max_tokens=2048,
        top_p=0.8,
        top_k=40,
        api_endpoint="https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent",
        requires_api_key=True,
        api_key_env_var="GOOGLE_API_KEY",
        requests_per_minute=60,
        tokens_per_minute=32000,
        educational_notes={
            "use_case": "Google's general-purpose LLM",
            "best_for": "Text generation, reasoning, analysis",
            "api_pattern": "Google AI REST API",
            "prompt_format": "GenerateContent request with parts array",
            "special_features": "Integration with Google services"
        }
    )
    
    configs["gemini-pro-vision"] = ModelConfig(
        provider=ModelProvider.GOOGLE_GEMINI,
        model_id="gemini-pro-vision",
        display_name="Gemini Pro Vision (Google)",
        capability=ModelCapability.MULTIMODAL,
        temperature=0.4,
        max_tokens=2048,
        top_p=0.8,
        top_k=32,
        api_endpoint="https://generativelanguage.googleapis.com/v1beta/models/gemini-pro-vision:generateContent",
        requires_api_key=True,
        api_key_env_var="GOOGLE_API_KEY",
        requests_per_minute=30,
        educational_notes={
            "use_case": "Multimodal understanding and generation",
            "best_for": "Image analysis, visual content creation",
            "api_pattern": "Google AI REST API",
            "special_features": "Text and image processing",
            "note": "Can understand and describe images"
        }
    )
    
    # Educational: Latest Gemini with image generation
    configs["gemini-ultra"] = ModelConfig(
        provider=ModelProvider.GOOGLE_GEMINI,
        model_id="gemini-ultra",
        display_name="Gemini Ultra (Google)",
        capability=ModelCapability.MULTIMODAL,
        temperature=0.7,
        max_tokens=4096,
        top_p=0.9,
        top_k=40,
        api_endpoint="https://generativelanguage.googleapis.com/v1beta/models/gemini-ultra:generateContent",
        requires_api_key=True,
        api_key_env_var="GOOGLE_API_KEY",
        requests_per_minute=20,  # More conservative for premium model
        educational_notes={
            "use_case": "Google's most capable model",
            "best_for": "Complex reasoning, multimodal tasks",
            "api_pattern": "Google AI REST API",
            "special_features": "Enhanced capabilities, multimodal",
            "note": "Premium model with advanced capabilities"
        }
    )
    
    return configs

def get_models_by_capability(capability: ModelCapability) -> Dict[str, ModelConfig]:
    """Educational function to filter models by capability"""
    all_configs = get_educational_model_configs()
    return {
        name: config for name, config in all_configs.items()
        if config.capability == capability
    }

def get_models_by_provider(provider: ModelProvider) -> Dict[str, ModelConfig]:
    """Educational function to filter models by provider"""
    all_configs = get_educational_model_configs()
    return {
        name: config for name, config in all_configs.items()
        if config.provider == provider
    }

def get_available_models() -> Dict[str, ModelConfig]:
    """
    Educational function to get only available models based on environment.
    Checks for required API keys and configurations.
    """
    all_configs = get_educational_model_configs()
    available = {}
    
    for name, config in all_configs.items():
        try:
            if config.requires_api_key and config.api_key_env_var:
                api_key = os.getenv(config.api_key_env_var)
                if not api_key:
                    logger.warning(f"Model {name} unavailable - missing {config.api_key_env_var}")
                    continue
            
            # Educational: Add availability checks here
            # For now, assume all models with proper config are available
            available[name] = config
            
        except Exception as e:
            logger.warning(f"Model {name} availability check failed: {e}")
            continue
    
    logger.info(f"Available models: {len(available)}/{len(all_configs)}")
    return available

def get_educational_summary() -> Dict[str, Any]:
    """
    Educational function to provide a summary of all configurations.
    Useful for learning and debugging.
    """
    configs = get_educational_model_configs()
    
    summary = {
        "total_models": len(configs),
        "by_provider": {},
        "by_capability": {},
        "api_patterns": set(),
        "educational_features": {
            "prompt_engineering_params": [
                "temperature", "max_tokens", "top_p", "top_k",
                "presence_penalty", "frequency_penalty"
            ],
            "provider_patterns": [
                "AWS Bedrock InvokeModel",
                "OpenAI Chat Completions API",
                "Anthropic Messages API",
                "Google AI REST API"
            ],
            "authentication_methods": [
                "AWS IAM (Bedrock)",
                "API Key (OpenAI, Anthropic, Google)",
                "Environment variables"
            ]
        }
    }
    
    for name, config in configs.items():
        # Count by provider
        provider_name = config.provider.value
        if provider_name not in summary["by_provider"]:
            summary["by_provider"][provider_name] = []
        summary["by_provider"][provider_name].append(name)
        
        # Count by capability
        capability_name = config.capability.value
        if capability_name not in summary["by_capability"]:
            summary["by_capability"][capability_name] = []
        summary["by_capability"][capability_name].append(name)
        
        # Collect API patterns
        if config.api_endpoint:
            summary["api_patterns"].add(config.api_endpoint.split("/")[2])  # domain
    
    summary["api_patterns"] = list(summary["api_patterns"])
    
    return summary

# Educational testing function
def test_configurations():
    """Educational function to test all configurations"""
    print("=== Testing Model Configurations ===")
    
    configs = get_educational_model_configs()
    print(f"\nTotal configurations: {len(configs)}")
    
    for name, config in configs.items():
        print(f"\n{name}:")
        print(f"  Provider: {config.provider.value}")
        print(f"  Capability: {config.capability.value}")
        print(f"  Temperature: {config.temperature}")
        print(f"  Max tokens: {config.max_tokens}")
        print(f"  Requires API key: {config.requires_api_key}")
        if config.educational_notes:
            print(f"  Use case: {config.educational_notes.get('use_case', 'N/A')}")
    
    # Test filtering functions
    text_models = get_models_by_capability(ModelCapability.TEXT_GENERATION)
    image_models = get_models_by_capability(ModelCapability.IMAGE_GENERATION)
    multimodal_models = get_models_by_capability(ModelCapability.MULTIMODAL)
    
    print(f"\nText models: {len(text_models)}")
    print(f"Image models: {len(image_models)}")
    print(f"Multimodal models: {len(multimodal_models)}")
    
    # Test provider filtering
    bedrock_models = get_models_by_provider(ModelProvider.AWS_BEDROCK)
    openai_models = get_models_by_provider(ModelProvider.OPENAI)
    anthropic_models = get_models_by_provider(ModelProvider.ANTHROPIC_DIRECT)
    gemini_models = get_models_by_provider(ModelProvider.GOOGLE_GEMINI)
    
    print(f"\nBedrock models: {len(bedrock_models)}")
    print(f"OpenAI models: {len(openai_models)}")
    print(f"Anthropic models: {len(anthropic_models)}")
    print(f"Gemini models: {len(gemini_models)}")
    
    # Test educational summary
    summary = get_educational_summary()
    print(f"\nEducational summary:")
    print(json.dumps(summary, indent=2, default=str))

if __name__ == "__main__":
    test_configurations()