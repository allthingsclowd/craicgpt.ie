#!/usr/bin/env python3
"""
CraicGPT Multi-Provider Prompt Generator
=======================================

PURPOSE:
Generates prompts for all supported model providers (AWS Bedrock, OpenAI, Anthropic, Gemini)
with proper secrets management and comprehensive prompt engineering parameters.

ARCHITECTURE:
- Single prompt generator handling all providers
- AWS Secrets Manager for secure API key retrieval  
- Explicit prompt engineering parameters (temperature, max_tokens, top_p, etc.)
- Component-based prompt building with clear influence relationships
- Backward compatible S3 storage format for existing handlers

SUPPORTED PROVIDERS:
- AWS Bedrock: Claude, Titan Text/Image, Nova Canvas (IAM authentication)
- OpenAI: GPT-4, O3 Mini, DALL-E 3 (API key via Secrets Manager)
- Anthropic Direct: Claude 3.5 Sonnet with vision (API key via Secrets Manager)
- Google Gemini: Gemini Pro, Pro Vision, Ultra (API key via Secrets Manager)

PROMPT STRUCTURE:
Each prompt has explicit parameters showing prompt engineering best practices:
- Temperature: 0.2 (factual) to 0.9 (creative)
- Max tokens: 150 (short) to 800 (long)
- Top-p: 0.3 (focused) to 0.95 (diverse)
- Presence/frequency penalties for repetition control

COMPONENT INFLUENCE MAPPING:
- Weather Context → Natural mood setting and opening material
- News Headlines → "Headline hijacking" for personal connection
- Family Context → Content for "family follies" section  
- Tech Trends → Work-related anecdotes and technical context
- Local Events → Community-based story material

ENVIRONMENT VARIABLES:
- START_DATE, END_DATE: Date range for generation
- PROMPT_BUCKET: S3 bucket for prompt storage
- OPENAI_SECRET_NAME: AWS Secrets Manager secret name for OpenAI API key
- ANTHROPIC_SECRET_NAME: AWS Secrets Manager secret name for Anthropic API key  
- GOOGLE_SECRET_NAME: AWS Secrets Manager secret name for Google API key

PERMISSIONS REQUIRED:
- s3:GetObject, s3:PutObject on PROMPT_BUCKET
- secretsmanager:GetSecretValue for API key secrets
"""

import os
import json
import logging
import urllib.request
import html
import re
import random
import boto3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum

# Configure comprehensive logging for debugging and monitoring
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("multi_provider_prompt_generator")

# =================================
# CONFIGURATION AND CONSTANTS
# =================================

# AWS clients for S3 storage and secrets management
s3_client = boto3.client("s3")
secrets_client = boto3.client("secretsmanager")

# S3 configuration - must match existing handler expectations
PROMPT_BUCKET = os.environ["PROMPT_BUCKET"]
BASE_PROMPT_PREFIX = "static_assets/content/prompts"  # Match existing handlers

# Secrets Manager configuration for secure API key retrieval
OPENAI_SECRET_NAME = os.getenv("OPENAI_SECRET_NAME", "craicgpt/openai-api-key")
ANTHROPIC_SECRET_NAME = os.getenv("ANTHROPIC_SECRET_NAME", "craicgpt/anthropic-api-key")
GOOGLE_SECRET_NAME = os.getenv("GOOGLE_SECRET_NAME", "craicgpt/google-api-key")

# Location configuration for weather and local context
LOCATION_ID = "2640129"  # Pontesbury, Shropshire OpenWeatherMap ID
LOCATION_NAME = "Pontesbury, Shropshire"

# News sources for contextual content generation
NEWS_SOURCES = {
    "tech": [
        "https://www.theregister.com/",
        "https://arstechnica.com/",
        "https://techcrunch.com/"
    ],
    "local": [
        "https://www.shropshirestar.com/",
        "https://www.bbc.co.uk/news/england/shropshire"
    ],
    "security": [
        "https://krebsonsecurity.com/",
        "https://www.bleepingcomputer.com/"
    ]
}

# =================================
# PROMPT ENGINEERING PARAMETERS
# =================================

class PromptParameters:
    """
    Centralized prompt engineering parameters with clear documentation.
    These parameters control model behavior and output characteristics.
    """
    
    # TEMPERATURE: Controls randomness and creativity in model responses
    # Lower values = more focused, deterministic responses
    # Higher values = more creative, varied responses
    TEMP_FACTUAL = 0.2      # For technical comparisons, precise content
    TEMP_BALANCED = 0.6     # For balanced content like author bios
    TEMP_CREATIVE = 0.9     # For creative writing like diary entries
    
    # MAX_TOKENS: Controls maximum response length
    # Consider model context limits and leave room for prompt + response
    TOKENS_SHORT = 150      # For jokes, headlines, brief content
    TOKENS_MEDIUM = 500     # For stories, bios, moderate content
    TOKENS_LONG = 800       # For articles, detailed content
    
    # TOP_P: Controls diversity via nucleus sampling
    # Lower values = more focused vocabulary selection
    # Higher values = more diverse word choices
    TOP_P_FOCUSED = 0.3     # For formal, technical content
    TOP_P_BALANCED = 0.7    # For general content
    TOP_P_CREATIVE = 0.95   # For creative, expressive content
    
    # PRESENCE_PENALTY: Reduces repetition of concepts
    # 0.0 = no penalty, allows natural repetition
    # Higher values = stronger penalty against repeating ideas
    PRESENCE_PENALTY_LIGHT = 0.1
    PRESENCE_PENALTY_MODERATE = 0.3
    
    # FREQUENCY_PENALTY: Reduces repetition of specific tokens
    # 0.0 = no penalty, allows token repetition
    # Higher values = stronger penalty against repeating words
    FREQUENCY_PENALTY_LIGHT = 0.1
    FREQUENCY_PENALTY_MODERATE = 0.3

# =================================
# MODEL PROVIDER CONFIGURATIONS
# =================================

class ModelProvider(Enum):
    """Model provider enumeration for categorizing different API endpoints"""
    AWS_BEDROCK = "bedrock"
    OPENAI = "openai"
    ANTHROPIC_DIRECT = "anthropic"
    GOOGLE_GEMINI = "gemini"

class ModelCapability(Enum):
    """Model capability enumeration for proper model selection"""
    TEXT_GENERATION = "text"
    IMAGE_GENERATION = "image"
    MULTIMODAL = "multimodal"

@dataclass
class ModelConfig:
    """
    Complete model configuration including all prompt engineering parameters
    and provider-specific settings for authentication and API access.
    """
    # Basic model identification
    provider: ModelProvider
    model_id: str
    display_name: str
    capability: ModelCapability
    
    # Prompt engineering parameters with defaults
    temperature: float = 0.7
    max_tokens: int = 500
    top_p: float = 0.9
    top_k: Optional[int] = None
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    
    # API configuration for non-Bedrock providers
    api_endpoint: Optional[str] = None
    requires_api_key: bool = False
    secret_name: Optional[str] = None
    
    # Provider-specific settings
    bedrock_region: str = "us-east-1"
    anthropic_version: str = "2023-06-01"
    
    # Image-specific parameters
    image_size: str = "512x512"
    image_quality: str = "standard"
    
    # Rate limiting to prevent API abuse
    requests_per_minute: int = 60
    tokens_per_minute: int = 10000

def get_model_configurations() -> Dict[str, ModelConfig]:
    """
    Comprehensive model configuration for all supported providers.
    Each model includes explicit prompt engineering parameters and API settings.
    """
    
    configs = {}
    
    # ====================================
    # AWS BEDROCK MODELS
    # ====================================
    # Bedrock models use IAM authentication, no API keys required
    
    configs["claude-3-sonnet-bedrock"] = ModelConfig(
        provider=ModelProvider.AWS_BEDROCK,
        model_id="anthropic.claude-3-sonnet-20240229-v1:0",
        display_name="Claude 3 Sonnet (AWS Bedrock)",
        capability=ModelCapability.TEXT_GENERATION,
        temperature=PromptParameters.TEMP_BALANCED,
        max_tokens=PromptParameters.TOKENS_LONG,
        top_p=PromptParameters.TOP_P_BALANCED,
        bedrock_region="us-east-1"
    )
    
    configs["claude-3-haiku-bedrock"] = ModelConfig(
        provider=ModelProvider.AWS_BEDROCK,
        model_id="anthropic.claude-3-haiku-20240307-v1:0",
        display_name="Claude 3 Haiku (AWS Bedrock)",
        capability=ModelCapability.TEXT_GENERATION,
        temperature=PromptParameters.TEMP_BALANCED,
        max_tokens=PromptParameters.TOKENS_MEDIUM,
        top_p=PromptParameters.TOP_P_BALANCED,
        bedrock_region="us-east-1"
    )
    
    configs["titan-text"] = ModelConfig(
        provider=ModelProvider.AWS_BEDROCK,
        model_id="amazon.titan-text-express-v1",
        display_name="Amazon Titan Text Express",
        capability=ModelCapability.TEXT_GENERATION,
        temperature=PromptParameters.TEMP_BALANCED,
        max_tokens=PromptParameters.TOKENS_MEDIUM,
        top_p=PromptParameters.TOP_P_BALANCED,
        bedrock_region="us-east-1"
    )
    
    configs["titan-image"] = ModelConfig(
        provider=ModelProvider.AWS_BEDROCK,
        model_id="amazon.titan-image-generator-v1",
        display_name="Amazon Titan Image Generator",
        capability=ModelCapability.IMAGE_GENERATION,
        temperature=0.0,  # Image models don't use temperature
        max_tokens=0,
        top_p=0.0,
        image_size="512x512",
        image_quality="standard",
        bedrock_region="us-east-1"
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
        bedrock_region="us-east-1"
    )
    
    # ====================================
    # OPENAI MODELS
    # ====================================
    # OpenAI models require API key from Secrets Manager
    
    configs["gpt-4"] = ModelConfig(
        provider=ModelProvider.OPENAI,
        model_id="gpt-4",
        display_name="GPT-4 (OpenAI)",
        capability=ModelCapability.TEXT_GENERATION,
        temperature=PromptParameters.TEMP_BALANCED,
        max_tokens=PromptParameters.TOKENS_LONG,
        top_p=PromptParameters.TOP_P_BALANCED,
        presence_penalty=PromptParameters.PRESENCE_PENALTY_LIGHT,
        frequency_penalty=PromptParameters.FREQUENCY_PENALTY_LIGHT,
        api_endpoint="https://api.openai.com/v1/chat/completions",
        requires_api_key=True,
        secret_name=OPENAI_SECRET_NAME,
        requests_per_minute=60,
        tokens_per_minute=10000
    )
    
    configs["o3-mini"] = ModelConfig(
        provider=ModelProvider.OPENAI,
        model_id="o3-mini",
        display_name="O3 Mini (OpenAI)",
        capability=ModelCapability.TEXT_GENERATION,
        temperature=PromptParameters.TEMP_CREATIVE,
        max_tokens=PromptParameters.TOKENS_LONG,
        top_p=PromptParameters.TOP_P_CREATIVE,
        presence_penalty=PromptParameters.PRESENCE_PENALTY_MODERATE,
        frequency_penalty=PromptParameters.FREQUENCY_PENALTY_MODERATE,
        api_endpoint="https://api.openai.com/v1/chat/completions",
        requires_api_key=True,
        secret_name=OPENAI_SECRET_NAME,
        requests_per_minute=100,
        tokens_per_minute=15000
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
        api_endpoint="https://api.openai.com/v1/images/generations",
        requires_api_key=True,
        secret_name=OPENAI_SECRET_NAME,
        requests_per_minute=5
    )
    
    # ====================================
    # ANTHROPIC DIRECT MODELS
    # ====================================
    # Anthropic direct API models require API key from Secrets Manager
    
    configs["claude-3-opus"] = ModelConfig(
        provider=ModelProvider.ANTHROPIC_DIRECT,
        model_id="claude-3-opus-20240229",
        display_name="Claude 3 Opus (Anthropic Direct)",
        capability=ModelCapability.TEXT_GENERATION,
        temperature=PromptParameters.TEMP_BALANCED,
        max_tokens=PromptParameters.TOKENS_LONG * 2,  # Opus can handle longer responses
        top_p=PromptParameters.TOP_P_BALANCED,
        api_endpoint="https://api.anthropic.com/v1/messages",
        requires_api_key=True,
        secret_name=ANTHROPIC_SECRET_NAME,
        anthropic_version="2023-06-01",
        requests_per_minute=50,
        tokens_per_minute=40000
    )
    
    configs["claude-3-5-sonnet"] = ModelConfig(
        provider=ModelProvider.ANTHROPIC_DIRECT,
        model_id="claude-3-5-sonnet-20241022",
        display_name="Claude 3.5 Sonnet Latest (Anthropic)",
        capability=ModelCapability.MULTIMODAL,
        temperature=PromptParameters.TEMP_BALANCED,
        max_tokens=PromptParameters.TOKENS_LONG,
        top_p=PromptParameters.TOP_P_BALANCED,
        api_endpoint="https://api.anthropic.com/v1/messages",
        requires_api_key=True,
        secret_name=ANTHROPIC_SECRET_NAME,
        anthropic_version="2023-06-01",
        requests_per_minute=60,
        tokens_per_minute=20000
    )
    
    # ====================================
    # GOOGLE GEMINI MODELS
    # ====================================
    # Gemini models require API key from Secrets Manager
    
    configs["gemini-pro"] = ModelConfig(
        provider=ModelProvider.GOOGLE_GEMINI,
        model_id="gemini-pro",
        display_name="Gemini Pro (Google)",
        capability=ModelCapability.TEXT_GENERATION,
        temperature=PromptParameters.TEMP_BALANCED,
        max_tokens=PromptParameters.TOKENS_LONG,
        top_p=PromptParameters.TOP_P_BALANCED,
        top_k=40,
        api_endpoint="https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent",
        requires_api_key=True,
        secret_name=GOOGLE_SECRET_NAME,
        requests_per_minute=60,
        tokens_per_minute=32000
    )
    
    configs["gemini-pro-vision"] = ModelConfig(
        provider=ModelProvider.GOOGLE_GEMINI,
        model_id="gemini-pro-vision",
        display_name="Gemini Pro Vision (Google)",
        capability=ModelCapability.MULTIMODAL,
        temperature=PromptParameters.TEMP_FACTUAL,
        max_tokens=PromptParameters.TOKENS_LONG,
        top_p=PromptParameters.TOP_P_BALANCED,
        top_k=32,
        api_endpoint="https://generativelanguage.googleapis.com/v1beta/models/gemini-pro-vision:generateContent",
        requires_api_key=True,
        secret_name=GOOGLE_SECRET_NAME,
        requests_per_minute=30
    )
    
    return configs

# =================================
# PROMPT COMPONENT DEFINITIONS
# =================================

@dataclass
class PromptComponent:
    """
    Individual prompt component showing clear influence on final output.
    Each component has documented purpose and effect on generation.
    """
    name: str
    description: str
    influence_on_output: str
    required: bool = True
    static_data: Optional[Dict[str, Any]] = None
    dynamic_data: Optional[Dict[str, Any]] = None

@dataclass
class PromptTemplate:
    """
    Complete prompt template with explicit engineering parameters.
    Templates show how different components combine for specific outputs.
    """
    prompt_id: str
    name: str
    description: str
    output_format: str
    
    # Explicit prompt engineering parameters
    temperature: float
    max_tokens: int
    top_p: float
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    
    # Components that influence this prompt
    components: List[PromptComponent] = field(default_factory=list)
    
    # Template structure
    system_prompt: str = ""
    user_prompt_template: str = ""
    
    # Model filtering
    supported_capabilities: List[ModelCapability] = field(default_factory=list)

# =================================
# CONTEXT BUILDING FUNCTIONS
# =================================

def fetch_url_safely(url: str, timeout: int = 15) -> str:
    """
    Safely fetch URL content with proper error handling and user agent.
    Used for gathering real-time news and weather context.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CraicGPT-Bot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return ""

def extract_headlines_from_html(html_content: str, limit: int = 10) -> List[str]:
    """
    Extract news headlines from HTML content using multiple patterns.
    Provides material for "headline hijacking" in diary entries.
    """
    # Multiple patterns to catch different HTML structures
    headline_patterns = [
        re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", re.S | re.I),
        re.compile(r'<a[^>]*class="[^"]*headline[^"]*"[^>]*>(.*?)</a>', re.S | re.I),
        re.compile(r'<span[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</span>', re.S | re.I)
    ]
    
    headlines = []
    for pattern in headline_patterns:
        matches = pattern.findall(html_content)
        for match in matches:
            # Clean HTML tags and decode entities
            clean_text = html.unescape(re.sub(r"<[^>]*>", " ", match)).strip()
            if len(clean_text) > 20 and clean_text not in headlines:
                headlines.append(clean_text)
                if len(headlines) >= limit:
                    return headlines
    
    return headlines

def get_weather_context(target_date: str) -> Dict[str, str]:
    """
    Get weather context for prompt generation.
    Uses live data for recent dates, seasonal patterns for historical dates.
    Weather context influences mood and opening material in diary entries.
    """
    target_dt = datetime.fromisoformat(target_date).date()
    today = datetime.now(ZoneInfo("Europe/London")).date()
    days_difference = (target_dt - today).days
    
    if abs(days_difference) <= 2:
        # For recent dates, attempt to get real weather data
        return get_live_weather()
    else:
        # For historical dates, generate plausible seasonal weather
        return generate_seasonal_weather(target_dt)

def get_live_weather() -> Dict[str, str]:
    """
    Attempt to fetch live weather data from BBC Weather API.
    Falls back to seasonal weather if API is unavailable.
    """
    try:
        url = f"https://weather-broker-cdn.api.bbci.co.uk/en/forecast/aggregated/{LOCATION_ID}"
        content = fetch_url_safely(url)
        
        if content:
            data = json.loads(content)
            forecast = data.get("forecast", {})
            daily = forecast.get("daily", [{}])[0]
            
            return {
                "today": daily.get("summary", "Weather data unavailable"),
                "tonight": daily.get("detailed", [{}])[0].get("summary", ""),
                "source": "BBC Weather API"
            }
    except Exception as e:
        logger.warning(f"Live weather fetch failed: {e}")
    
    # Fallback to seasonal weather
    return generate_seasonal_weather(datetime.now().date())

def generate_seasonal_weather(date_obj: datetime.date) -> Dict[str, str]:
    """
    Generate plausible weather based on season and location.
    Used when live weather data is unavailable or for historical dates.
    """
    month = date_obj.month
    
    # Seasonal weather patterns for Shropshire, UK
    weather_patterns = {
        "winter": ["Frost and fog", "Light snow possible", "Cloudy and cold", "Mild but damp"],
        "spring": ["Spring showers", "Mild and breezy", "Sunny spells", "Fresh and bright"],
        "summer": ["Warm and sunny", "Scattered showers", "Pleasant breeze", "Hot and humid"],
        "autumn": ["Autumn mist", "Crisp and clear", "Golden sunshine", "Blustery showers"]
    }
    
    if month in [12, 1, 2]:
        season = "winter"
    elif month in [3, 4, 5]:
        season = "spring"
    elif month in [6, 7, 8]:
        season = "summer"
    else:
        season = "autumn"
    
    patterns = weather_patterns[season]
    today_weather = random.choice(patterns)
    tonight_weather = random.choice(patterns)
    
    return {
        "today": f"{today_weather} in {LOCATION_NAME}",
        "tonight": f"{tonight_weather} expected",
        "source": "seasonal_pattern"
    }

def get_news_context(target_date: str) -> Dict[str, List[str]]:
    """
    Get news context for prompt generation.
    Scrapes current news for recent dates, generates contextual news for historical dates.
    News provides material for headline hijacking and current event references.
    """
    target_dt = datetime.fromisoformat(target_date).date()
    today = datetime.now(ZoneInfo("Europe/London")).date()
    
    if abs((target_dt - today).days) <= 1:
        # For current dates, scrape live news
        return scrape_current_news()
    else:
        # For historical dates, generate contextual news
        return generate_historical_news(target_date)

def scrape_current_news() -> Dict[str, List[str]]:
    """
    Scrape current news from configured sources.
    Provides real headlines for topical content generation.
    """
    news_data = {}
    
    for category, urls in NEWS_SOURCES.items():
        headlines = []
        for url in urls:
            content = fetch_url_safely(url)
            if content:
                source_headlines = extract_headlines_from_html(content, limit=5)
                headlines.extend(source_headlines)
            
            # Prevent too many requests to any single source
            if len(headlines) >= 8:
                break
        
        news_data[category] = headlines[:8]  # Limit per category
    
    return news_data

def generate_historical_news(target_date: str) -> Dict[str, List[str]]:
    """
    Generate plausible news context for historical dates.
    Creates contextually appropriate headlines based on date and known trends.
    """
    dt = datetime.fromisoformat(target_date)
    
    # Generate contextual headlines based on date and technology trends
    historical_context = {
        "tech": [
            f"AI developments continue to shape industry trends in {dt.year}",
            f"New cybersecurity challenges emerge across sectors",
            f"Cloud computing adoption accelerates in enterprise environments"
        ],
        "local": [
            f"Shropshire community events planned for {dt.strftime('%B')}",
            f"Local businesses adapt to changing market conditions",
            f"Rural connectivity improvements announced for region"
        ],
        "security": [
            f"Security researchers identify new threat patterns",
            f"Best practices evolve for remote work environments",
            f"Industry collaboration strengthens cyber defenses"
        ]
    }
    
    return historical_context

def extract_trending_topics(news_data: Dict[str, List[str]]) -> List[str]:
    """
    Extract trending topics from news headlines for context.
    Used to inform technical content and work-related anecdotes.
    """
    all_text = " ".join([
        headline for headlines in news_data.values() 
        for headline in headlines
    ]).lower()
    
    # Technology and industry keywords relevant to CraicGPT content
    trending_keywords = [
        "ai", "artificial intelligence", "machine learning", "chatgpt", "openai",
        "cybersecurity", "cloud", "blockchain", "quantum", "startup",
        "funding", "acquisition", "breach", "hack", "vulnerability",
        "remote work", "automation", "privacy", "regulation", "sustainability"
    ]
    
    found_topics = []
    for keyword in trending_keywords:
        if keyword in all_text and keyword not in found_topics:
            found_topics.append(keyword)
    
    return found_topics[:6]  # Limit to most relevant topics

def generate_local_events(target_date: str) -> List[str]:
    """
    Generate plausible local Shropshire events for the date.
    Provides community context for story generation and local color.
    """
    dt = datetime.fromisoformat(target_date)
    month_name = dt.strftime("%B")
    
    # Season-appropriate local events for English village life
    seasonal_events = {
        "winter": ["village pub quiz night", "local craft fair", "parish council meeting"],
        "spring": ["garden center spring show", "village green clean-up", "local farmers market"],
        "summer": ["village fete planning", "cricket match on the green", "community BBQ"],
        "autumn": ["harvest festival preparations", "village bonfire planning", "autumn craft workshop"]
    }
    
    if dt.month in [12, 1, 2]:
        season = "winter"
    elif dt.month in [3, 4, 5]:
        season = "spring"
    elif dt.month in [6, 7, 8]:
        season = "summer"
    else:
        season = "autumn"
    
    return [f"Pontesbury {event} in {month_name}" for event in seasonal_events[season][:2]]

# =================================
# PROMPT TEMPLATE DEFINITIONS
# =================================

def create_prompt_templates() -> Dict[str, PromptTemplate]:
    """
    Create all prompt templates with explicit parameters and component relationships.
    Each template shows how prompt engineering parameters affect output.
    """
    templates = {}
    
    # ====================================
    # LLM PROMPT: MAIN ARTICLE (Graham's Diary)
    # ====================================
    
    main_article = PromptTemplate(
        prompt_id="llm_01",
        name="Main Article - Graham's Diary",
        description="Personal diary entry with weather, news, and family context",
        output_format="diary_entry",
        temperature=PromptParameters.TEMP_CREATIVE,  # High creativity for personal voice
        max_tokens=PromptParameters.TOKENS_LONG,     # Long enough for full diary entry
        top_p=PromptParameters.TOP_P_CREATIVE,       # High diversity for creative expression
        presence_penalty=PromptParameters.PRESENCE_PENALTY_LIGHT,
        frequency_penalty=PromptParameters.FREQUENCY_PENALTY_LIGHT,
        supported_capabilities=[ModelCapability.TEXT_GENERATION, ModelCapability.MULTIMODAL]
    )
    
    # Define components that influence the main article
    main_article.components = [
        PromptComponent(
            name="character_definition",
            description="Graham's personality, background, and writing style",
            influence_on_output="Determines voice, tone, and perspective of the diary entry",
        ),
        PromptComponent(
            name="weather_context",
            description="Current weather conditions for the diary date",
            influence_on_output="Provides natural opening material and mood setting",
        ),
        PromptComponent(
            name="news_headlines",
            description="Real news headlines for the diary date",
            influence_on_output="Provides material for 'headline hijacking' - connecting news to personal life",
        ),
        PromptComponent(
            name="family_context",
            description="Family members and their personalities",
            influence_on_output="Provides material for 'family follies' section",
        )
    ]
    
    main_article.system_prompt = """You are Graham Land, 'the Geek with the Peak,' aged 54 and a quarter. 
You keep a droll, self-aware diary in Adrian Mole style that logs the chaos of being a freshly-minted AI engineer.

PROMPT ENGINEERING PARAMETERS:
- Temperature: {temperature} (high creativity for personal voice)
- Max tokens: {max_tokens} (long enough for full diary entry)
- Top-p: {top_p} (high diversity for creative expression)
- Presence penalty: {presence_penalty} (light penalty to avoid repetition)
- Frequency penalty: {frequency_penalty} (light penalty for natural variation)

STYLE REQUIREMENTS:
- Length: 250-400 words
- Tone: cheeky-optimistic, Irish-flavored, lightly self-deprecating
- Structure: Weather → Headlines → Work → Family → Pub → Reflection
- Include mild Irish idiom or phrase once per entry"""
    
    main_article.user_prompt_template = """Write a diary entry for {date} including:

WEATHER: {weather_today}
NEWS TO HIJACK: {news_headlines}
FAMILY CONTEXT: {family_updates}

Follow your standard diary structure with natural Irish humor."""
    
    templates["llm_01"] = main_article
    
    # ====================================
    # LLM PROMPT: COMPARISON ARTICLE
    # ====================================
    
    comparison_article = PromptTemplate(
        prompt_id="llm_02",
        name="LLM Comparison Article",
        description="Technical comparison of top 5 LLMs in JSON format",
        output_format="json_table",
        temperature=PromptParameters.TEMP_FACTUAL,    # Low temperature for factual accuracy
        max_tokens=PromptParameters.TOKENS_MEDIUM,    # Medium length for structured data
        top_p=PromptParameters.TOP_P_FOCUSED,         # Focused vocabulary for technical content
        presence_penalty=0.0,  # No penalties for structured output
        frequency_penalty=0.0,
        supported_capabilities=[ModelCapability.TEXT_GENERATION, ModelCapability.MULTIMODAL]
    )
    
    comparison_article.components = [
        PromptComponent(
            name="tech_trends",
            description="Current AI/ML trends and developments",
            influence_on_output="Ensures comparison reflects current state of AI industry",
        ),
        PromptComponent(
            name="cynical_perspective",
            description="Humorous, skeptical view of AI hype",
            influence_on_output="Provides balance to technical strengths with real-world usage",
        )
    ]
    
    comparison_article.system_prompt = """You are an expert tech humorist creating a comparison table.

PROMPT ENGINEERING PARAMETERS:
- Temperature: {temperature} (low for factual accuracy)
- Max tokens: {max_tokens} (medium length for structured data)
- Top-p: {top_p} (focused vocabulary for technical content)
- No penalties (structured output needs consistency)

OUTPUT FORMAT: JSON only, no markdown, no explanations
TONE: Informed yet cheekily skeptical
STRUCTURE: Exactly 5 rows, 3 columns each"""
    
    comparison_article.user_prompt_template = """Create a JSON comparison table of top 5 LLMs with:
- Column 1: Model name (bolded)
- Column 2: Genuine strength
- Column 3: Cynical "what it's really used for"

Current tech context: {tech_trends}"""
    
    templates["llm_02"] = comparison_article
    
    # ====================================
    # LLM PROMPT: STORY
    # ====================================
    
    story_prompt = PromptTemplate(
        prompt_id="llm_03",
        name="LLM User Story",
        description="Light-hearted story about everyday LLM use",
        output_format="short_story",
        temperature=PromptParameters.TEMP_CREATIVE,
        max_tokens=PromptParameters.TOKENS_MEDIUM,
        top_p=PromptParameters.TOP_P_CREATIVE,
        presence_penalty=PromptParameters.PRESENCE_PENALTY_LIGHT,
        frequency_penalty=PromptParameters.FREQUENCY_PENALTY_LIGHT,
        supported_capabilities=[ModelCapability.TEXT_GENERATION, ModelCapability.MULTIMODAL]
    )
    
    story_prompt.components = [
        PromptComponent(
            name="relatable_character",
            description="Non-technical person using LLM",
            influence_on_output="Makes AI accessible to general audience",
        ),
        PromptComponent(
            name="humorous_outcome",
            description="Funny, unexpected result from LLM interaction",
            influence_on_output="Provides entertainment value and memorable conclusion",
        )
    ]
    
    story_prompt.system_prompt = """You write light-hearted, relatable stories about everyday LLM use.

PROMPT ENGINEERING PARAMETERS:
- Temperature: {temperature} (high creativity for engaging narrative)
- Max tokens: {max_tokens} (medium length for complete story)
- Top-p: {top_p} (high diversity for creative storytelling)
- Presence penalty: {presence_penalty} (light penalty for natural flow)
- Frequency penalty: {frequency_penalty} (light penalty for varied language)

STORY REQUIREMENTS:
- Length: ≤200 words
- Character: Everyday non-techie person
- Structure: Problem → LLM solution → Unexpected twist
- Tone: Relatable and chuckle-worthy"""
    
    story_prompt.user_prompt_template = """Write a story about {character_type} using an LLM to solve {problem}.
Include a humorous, unexpected outcome that makes the story memorable.
Local context: {local_events}"""
    
    templates["llm_03"] = story_prompt
    
    # ====================================
    # LLM PROMPT: JOKE
    # ====================================
    
    joke_prompt = PromptTemplate(
        prompt_id="llm_04",
        name="AI Industry Joke",
        description="One-liner joke about AI industry figures",
        output_format="one_liner",
        temperature=PromptParameters.TEMP_CREATIVE,
        max_tokens=PromptParameters.TOKENS_SHORT,
        top_p=PromptParameters.TOP_P_CREATIVE,
        presence_penalty=0.0,
        frequency_penalty=0.0,
        supported_capabilities=[ModelCapability.TEXT_GENERATION, ModelCapability.MULTIMODAL]
    )
    
    joke_prompt.components = [
        PromptComponent(
            name="ai_personalities",
            description="Well-known AI industry figures",
            influence_on_output="Provides recognizable references for industry humor",
        )
    ]
    
    joke_prompt.system_prompt = """You create clever one-liner jokes about the AI industry.

PROMPT ENGINEERING PARAMETERS:
- Temperature: {temperature} (high creativity for humor)
- Max tokens: {max_tokens} (short for one-liner format)
- Top-p: {top_p} (high diversity for creative wordplay)
- No penalties (short format doesn't need repetition control)

JOKE REQUIREMENTS:
- Format: One-liner, ≤40 words
- Include AI industry figures by name
- Clever, family-friendly, self-aware
- Non-political, non-tragic"""
    
    joke_prompt.user_prompt_template = """Create a one-liner joke about {ai_figure} related to {ai_topic}.
Current AI trends: {ai_trends}"""
    
    templates["llm_04"] = joke_prompt
    
    # ====================================
    # LLM PROMPT: AUTHOR BIO
    # ====================================
    
    author_bio = PromptTemplate(
        prompt_id="llm_05",
        name="Author Bio",
        description="Third-person bio of Graham Land",
        output_format="biography",
        temperature=PromptParameters.TEMP_BALANCED,
        max_tokens=PromptParameters.TOKENS_MEDIUM,
        top_p=PromptParameters.TOP_P_BALANCED,
        presence_penalty=PromptParameters.PRESENCE_PENALTY_LIGHT,
        frequency_penalty=PromptParameters.FREQUENCY_PENALTY_LIGHT,
        supported_capabilities=[ModelCapability.TEXT_GENERATION, ModelCapability.MULTIMODAL]
    )
    
    author_bio.components = [
        PromptComponent(
            name="professional_background",
            description="Graham's career progression and expertise",
            influence_on_output="Establishes credibility and expertise",
        )
    ]
    
    author_bio.system_prompt = """You write engaging third-person professional biographies.

PROMPT ENGINEERING PARAMETERS:
- Temperature: {temperature} (balanced for professional yet engaging tone)
- Max tokens: {max_tokens} (medium length for complete bio)
- Top-p: {top_p} (balanced diversity for professional writing)
- Presence penalty: {presence_penalty} (light penalty for natural flow)
- Frequency penalty: {frequency_penalty} (light penalty for varied language)

BIO REQUIREMENTS:
- Length: 120-150 words
- Style: Cheeky third-person
- End with playful line about AI Engineering"""
    
    author_bio.user_prompt_template = """Write a professional bio for Graham Land incorporating:
- Current role: {current_role}
- Background: {professional_background}
- Expertise: {technical_expertise}
- Personal: {personal_interests}

End with a playful line about making AI Engineering 'slightly less terrifying'."""
    
    templates["llm_05"] = author_bio
    
    # ====================================
    # IMAGE PROMPTS
    # ====================================
    
    # Main article image
    main_image = PromptTemplate(
        prompt_id="img_01",
        name="Main Article Image",
        description="Village scene illustration for diary entry",
        output_format="image",
        temperature=0.0,  # Images don't use temperature
        max_tokens=0,
        top_p=0.0,
        supported_capabilities=[ModelCapability.IMAGE_GENERATION]
    )
    
    main_image.components = [
        PromptComponent(
            name="village_setting",
            description="Quintessentially English village scene",
            influence_on_output="Sets location and atmosphere for diary context",
        ),
        PromptComponent(
            name="seasonal_elements",
            description="Weather and seasonal context",
            influence_on_output="Adds visual context matching diary date and weather",
        )
    ]
    
    main_image.user_prompt_template = """Comic-realistic English village scene, Pontesbury, Shropshire setting, 
with satellite in background sky. Include {seasonal_elements}, {weather_mood}, 
capturing {day_of_week} atmosphere in {date_formatted}."""
    
    templates["img_01"] = main_image
    
    # Comparison article image
    comparison_image = PromptTemplate(
        prompt_id="img_02",
        name="Comparison Article Image", 
        description="Data visualization for LLM comparison",
        output_format="image",
        temperature=0.0,
        max_tokens=0,
        top_p=0.0,
        supported_capabilities=[ModelCapability.IMAGE_GENERATION]
    )
    
    comparison_image.user_prompt_template = """D3.js realistic and colorful visualization comparing 5 LLMs, 
professional design, clear metrics, modern data visualization style."""
    
    templates["img_02"] = comparison_image
    
    # Advertisement images (4 variations)
    ad_descriptions = [
        "Tech product spoof ad with retro styling",
        "Fake cereal box ad with tech/AI theme", 
        "Vintage travel poster ad for sunny destination",
        "Mock luxury product ad with tech twist"
    ]
    
    for i in range(1, 5):
        ad_template = PromptTemplate(
            prompt_id=f"img_0{i+2}",
            name=f"Advertisement {i}",
            description=ad_descriptions[i-1],
            output_format="image",
            temperature=0.0,
            max_tokens=0,
            top_p=0.0,
            supported_capabilities=[ModelCapability.IMAGE_GENERATION]
        )
        
        ad_template.user_prompt_template = f"Comic-realistic, {ad_descriptions[i-1]}, colorful branding, retro styling."
        templates[f"img_0{i+2}"] = ad_template
    
    # Story and joke images
    story_image = PromptTemplate(
        prompt_id="img_07",
        name="Story Illustration",
        description="Single-panel comic for LLM story",
        output_format="image",
        temperature=0.0,
        max_tokens=0,
        top_p=0.0,
        supported_capabilities=[ModelCapability.IMAGE_GENERATION]
    )
    
    story_image.user_prompt_template = "Single-panel comic style, cozy domestic setting, cat and dog with slippers."
    templates["img_07"] = story_image
    
    joke_image = PromptTemplate(
        prompt_id="img_08",
        name="Joke Illustration",
        description="Editorial cartoon for AI industry joke",
        output_format="image",
        temperature=0.0,
        max_tokens=0,
        top_p=0.0,
        supported_capabilities=[ModelCapability.IMAGE_GENERATION]
    )
    
    joke_image.user_prompt_template = "Editorial cartoon style, AI industry satire, {ai_figure} caricature."
    templates["img_08"] = joke_image
    
    return templates

# =================================
# MODEL SELECTION FUNCTIONS
# =================================

def get_models_for_capability(capability: ModelCapability) -> List[str]:
    """
    Get all available models that support the specified capability.
    Used to match prompts with appropriate models.
    """
    configs = get_model_configurations()
    return [
        name for name, config in configs.items() 
        if config.capability == capability or 
        (capability == ModelCapability.TEXT_GENERATION and config.capability == ModelCapability.MULTIMODAL)
    ]

def get_default_models() -> Dict[str, List[str]]:
    """
    Get default model selections for text and image generation.
    Balances capability with reliability and cost.
    """
    return {
        "text": [
            "claude-3-sonnet-bedrock",  # Reliable Bedrock model
            "gpt-4",                    # High-quality OpenAI model
            "titan-text"                # Cost-effective Bedrock model
        ],
        "image": [
            "titan-image",              # Reliable Bedrock model
            "nova-canvas",              # Higher quality Bedrock model
            "dall-e-3"                  # High-quality OpenAI model
        ]
    }

# =================================
# PROMPT BUILDING FUNCTIONS
# =================================

def build_context_data(target_date: str) -> Dict[str, Any]:
    """
    Build comprehensive context data for prompt generation.
    Aggregates weather, news, and local information for the specified date.
    """
    logger.info(f"Building context data for {target_date}")
    
    # Get weather context - influences mood and opening material
    weather_context = get_weather_context(target_date)
    
    # Get news context - provides material for headline hijacking
    news_context = get_news_context(target_date)
    
    # Extract trending topics - informs technical content
    trending_topics = extract_trending_topics(news_context)
    
    # Generate local events - provides community context
    local_events = generate_local_events(target_date)
    
    # Build date-specific context
    date_obj = datetime.fromisoformat(target_date)
    day_of_week = date_obj.strftime("%A")
    date_formatted = date_obj.strftime("%B %d, %Y")
    
    return {
        "date": target_date,
        "weather_today": weather_context["today"],
        "weather_tonight": weather_context.get("tonight", ""),
        "weather_source": weather_context.get("source", "unknown"),
        "news_headlines": news_context.get("tech", [])[:3],
        "local_news": news_context.get("local", [])[:2],
        "security_news": news_context.get("security", [])[:2],
        "trending_topics": trending_topics,
        "local_events": local_events,
        "day_of_week": day_of_week,
        "date_formatted": date_formatted,
        
        # Static context data for character consistency
        "character_type": "busy parent",
        "problem": "planning family dinner",
        "ai_figure": "Sam Altman",
        "ai_topic": "AGI timeline",
        "current_role": "Technical Account Manager at Salt Security",
        "professional_background": "HashiCorp, cybersecurity, cloud architecture",
        "technical_expertise": "OpenStack, Vault, AWS, ITIL",
        "personal_interests": "motorbike, paddle-board, rpi projects",
        "family_updates": "Eddie's latest antics, Puddle's curtain climbing",
        
        # Dynamic visual context for images
        "seasonal_elements": get_seasonal_elements(date_obj),
        "weather_mood": get_weather_mood(weather_context["today"]),
        "ai_trends": trending_topics[:3]
    }

def get_seasonal_elements(date_obj: datetime.date) -> str:
    """Generate seasonal visual elements based on the date."""
    seasonal_elements = {
        12: "winter frost, bare trees, cozy holiday atmosphere",
        1: "new year energy, fresh start, winter clarity",
        2: "winter warmth, indoor comfort, February light",
        3: "spring awakening, fresh growth, March winds",
        4: "April showers, blooming flowers, spring renewal",
        5: "spring sunshine, vibrant colors, May blossoms",
        6: "summer warmth, outdoor activity, June brightness",
        7: "midsummer radiance, long days, July heat",
        8: "summer holidays, relaxed mood, August abundance",
        9: "autumn colors, harvest time, September transition",
        10: "golden autumn, crisp air, October beauty",
        11: "autumn mist, cozy preparations, November atmosphere"
    }
    return seasonal_elements.get(date_obj.month, "seasonal atmosphere")

def get_weather_mood(weather_description: str) -> str:
    """Generate visual mood based on weather description."""
    weather_lower = weather_description.lower()
    if "sun" in weather_lower or "clear" in weather_lower:
        return "bright natural lighting, sunny atmosphere"
    elif "cloud" in weather_lower or "overcast" in weather_lower:
        return "soft diffused lighting, cloudy atmospheric mood"
    elif "rain" in weather_lower or "shower" in weather_lower:
        return "cozy indoor lighting, rain-day atmosphere"
    else:
        return "balanced natural lighting"

def build_prompt_content(template: PromptTemplate, context_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build complete prompt content for a template using context data.
    Returns system prompt, user prompt, and parameters in standardized format.
    """
    # Format system prompt with parameters
    system_prompt = template.system_prompt.format(
        temperature=template.temperature,
        max_tokens=template.max_tokens,
        top_p=template.top_p,
        presence_penalty=template.presence_penalty,
        frequency_penalty=template.frequency_penalty
    )
    
    # Format user prompt with context data
    user_prompt = template.user_prompt_template.format(**context_data)
    
    # Combine for final prompt (this is what handlers expect in "prompt" field)
    if template.output_format == "image":
        # Image prompts use only the user prompt
        final_prompt = user_prompt
    else:
        # Text prompts combine system and user prompts
        final_prompt = f"{system_prompt}\n\n{user_prompt}"
    
    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "final_prompt": final_prompt,
        "parameters": {
            "temperature": template.temperature,
            "max_tokens": template.max_tokens,
            "top_p": template.top_p,
            "presence_penalty": template.presence_penalty,
            "frequency_penalty": template.frequency_penalty
        },
        "template_name": template.name,
        "components_used": [comp.name for comp in template.components]
    }

# =================================
# S3 STORAGE FUNCTIONS
# =================================

def check_prompt_exists(prompt_id: str, date: str) -> bool:
    """
    Check if a prompt file already exists in S3 for idempotent behavior.
    Prevents overwriting existing prompts on retry.
    """
    try:
        year, month, day = date.split("-")
        key = f"{BASE_PROMPT_PREFIX}/{year}/{month}/{day}/{prompt_id}.json"
        
        s3_client.head_object(Bucket=PROMPT_BUCKET, Key=key)
        return True
    except s3_client.exceptions.NoSuchKey:
        return False
    except Exception as e:
        logger.warning(f"Error checking prompt existence for {prompt_id}/{date}: {e}")
        return True  # Assume exists to avoid overwrite on error

def store_prompt(prompt_id: str, date: str, prompt_content: Dict[str, Any], 
                template: PromptTemplate) -> Tuple[str, bool]:
    """
    Store prompt in S3 with backward-compatible format.
    Returns (s3_key, was_created) tuple for tracking.
    """
    year, month, day = date.split("-")
    s3_key = f"{BASE_PROMPT_PREFIX}/{year}/{month}/{day}/{prompt_id}.json"
    
    # Check if already exists (idempotent behavior)
    if check_prompt_exists(prompt_id, date):
        logger.info(f"⏩ Prompt already exists, skipping: {s3_key}")
        return s3_key, False
    
    # Get appropriate models for this template
    if template.output_format == "image":
        models = get_models_for_capability(ModelCapability.IMAGE_GENERATION)
    else:
        models = get_models_for_capability(ModelCapability.TEXT_GENERATION)
    
    # Build storage data in format expected by existing handlers
    storage_data = {
        "prompt_id": prompt_id,
        "prompt_type": template.output_format,
        "date": date,
        "prompt": prompt_content["final_prompt"],  # CRITICAL: This is what handlers read
        "models": models,
        "temperature": template.temperature,
        "max_tokens": template.max_tokens,
        "top_p": template.top_p,
        "presence_penalty": template.presence_penalty,
        "frequency_penalty": template.frequency_penalty,
        "context": {
            "template_name": template.name,
            "system_prompt": prompt_content["system_prompt"],
            "user_prompt": prompt_content["user_prompt"],
            "parameters": prompt_content["parameters"],
            "components_used": prompt_content["components_used"]
        }
    }
    
    try:
        s3_client.put_object(
            Bucket=PROMPT_BUCKET,
            Key=s3_key,
            Body=json.dumps(storage_data, indent=2, ensure_ascii=False),
            ContentType="application/json"
        )
        
        logger.info(f"✅ Prompt stored: {s3_key}")
        return s3_key, True
        
    except Exception as e:
        logger.error(f"❌ Failed to store prompt {s3_key}: {e}")
        raise

# =================================
# DATE RANGE UTILITIES
# =================================

def generate_date_range(start_date: str, end_date: str) -> List[str]:
    """
    Generate list of dates between start and end (inclusive).
    Used for processing date ranges in batch operations.
    """
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()
    
    dates = []
    current = start
    while current <= end:
        dates.append(current.isoformat())
        current += timedelta(days=1)
    
    return dates

# =================================
# MAIN LAMBDA HANDLER
# =================================

def lambda_handler(event, context):
    """
    Main Lambda handler for multi-provider prompt generation.
    
    Supports date range processing with idempotent behavior for reliable operation.
    Generates prompts for all supported model providers with explicit parameters.
    
    Input Formats:
    - Single date: {"date": "2025-01-15"}
    - Date range: {"START_DATE": "2025-01-10", "END_DATE": "2025-01-15"}
    - Environment variables: START_DATE, END_DATE
    
    Output:
    - Prompts stored in S3 in backward-compatible format
    - Summary of generation results
    """
    
    logger.info("=== Multi-Provider Prompt Generator Started ===")
    logger.info(f"Event: {json.dumps(event, default=str)}")
    
    try:
        # Determine date range from multiple sources with fallback priority
        start_date = (
            event.get("START_DATE") or 
            os.getenv("START_DATE") or 
            event.get("start_date") or 
            event.get("date") or
            datetime.now(ZoneInfo("Europe/London")).date().isoformat()
        )
        
        end_date = (
            event.get("END_DATE") or 
            os.getenv("END_DATE") or 
            event.get("end_date") or 
            start_date
        )
        
        logger.info(f"Processing date range: {start_date} to {end_date}")
        
        # Generate date list for processing
        dates = generate_date_range(start_date, end_date)
        logger.info(f"Generated {len(dates)} dates: {dates[0]} to {dates[-1]}")
        
        # Load prompt templates with explicit parameters
        templates = create_prompt_templates()
        logger.info(f"Loaded {len(templates)} prompt templates")
        
        # Track generation results
        generated_prompts = []
        skipped_prompts = []
        errors = []
        
        # Process each date
        for target_date in dates:
            logger.info(f"\n{'='*50}")
            logger.info(f"PROCESSING DATE: {target_date}")
            logger.info(f"{'='*50}")
            
            # Build context data for this date
            try:
                context_data = build_context_data(target_date)
                logger.info(f"Context built - Weather: {context_data['weather_source']}, "
                           f"News categories: {len([k for k in context_data.keys() if 'news' in k])}, "
                           f"Trending topics: {len(context_data['trending_topics'])}")
            except Exception as e:
                logger.error(f"❌ Failed to build context for {target_date}: {e}")
                errors.append(f"Context building failed for {target_date}: {e}")
                continue
            
            # Generate prompts for each template
            for prompt_id, template in templates.items():
                logger.info(f"\n  ┌─ {template.name}")
                logger.info(f"  │  ID: {prompt_id}")
                logger.info(f"  │  Type: {template.output_format}")
                logger.info(f"  │  Temperature: {template.temperature}")
                logger.info(f"  │  Max tokens: {template.max_tokens}")
                logger.info(f"  │  Components: {len(template.components)}")
                
                try:
                    # Build prompt content with parameters
                    prompt_content = build_prompt_content(template, context_data)
                    
                    # Store prompt with idempotent behavior
                    s3_key, was_created = store_prompt(prompt_id, target_date, prompt_content, template)
                    
                    if was_created:
                        generated_prompts.append(s3_key)
                        status = "Generated"
                    else:
                        skipped_prompts.append(s3_key)
                        status = "Skipped (exists)"
                    
                    logger.info(f"  │  Prompt length: {len(prompt_content['final_prompt'])} characters")
                    logger.info(f"  │  Models: {len(get_models_for_capability(template.supported_capabilities[0]))}")
                    logger.info(f"  └─ ✓ {status}")
                    
                except Exception as e:
                    logger.error(f"  └─ ✗ Error generating {prompt_id}: {e}")
                    errors.append(f"Prompt generation failed for {prompt_id}/{target_date}: {e}")
                    continue
        
        # Generate summary statistics
        total_prompts = len(generated_prompts) + len(skipped_prompts)
        llm_count = len([p for p in generated_prompts + skipped_prompts if "llm_" in p])
        image_count = len([p for p in generated_prompts + skipped_prompts if "img_" in p])
        
        logger.info(f"\n{'='*50}")
        logger.info(f"GENERATION COMPLETE")
        logger.info(f"{'='*50}")
        logger.info(f"Dates processed: {len(dates)}")
        logger.info(f"New prompts generated: {len(generated_prompts)}")
        logger.info(f"Existing prompts skipped: {len(skipped_prompts)}")
        logger.info(f"Errors encountered: {len(errors)}")
        logger.info(f"Total prompts: {total_prompts} (LLM: {llm_count}, Image: {image_count})")
        
        # Build response
        response = {
            "status": "SUCCESS" if len(errors) == 0 else "PARTIAL_SUCCESS",
            "dates_processed": dates,
            "prompts_generated": len(generated_prompts),
            "prompts_skipped": len(skipped_prompts),
            "errors": len(errors),
            "error_details": errors[:10],  # Limit error details
            "prompt_breakdown": {
                "llm_prompts": llm_count,
                "image_prompts": image_count,
                "by_date": {
                    date: len([p for p in generated_prompts + skipped_prompts if f"/{date}/" in p])
                    for date in dates
                }
            },
            "sample_generated": generated_prompts[:5],
            "sample_skipped": skipped_prompts[:5]
        }
        
        return {
            "statusCode": 200,
            "body": json.dumps(response, default=str)
        }
        
    except Exception as e:
        logger.error(f"❌ Handler error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "ERROR",
                "error": str(e),
                "message": "Prompt generation failed - check logs for details"
            })
        }

# Entry point for local testing
if __name__ == "__main__":
    # Test with sample event
    test_event = {
        "START_DATE": "2025-01-15",
        "END_DATE": "2025-01-15"
    }
    
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2, default=str))