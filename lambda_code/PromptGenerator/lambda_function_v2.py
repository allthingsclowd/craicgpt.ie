#!/usr/bin/env python3
"""
CraicGPT Educational Prompt Generator - Phase 0 MVP
==================================================

EDUCATIONAL PURPOSE:
This code serves as a training exercise for AI engineers learning prompt engineering 
best practices. Each component is clearly documented with explicit parameters and 
influence relationships.

ARCHITECTURE:
- Clear separation of concerns
- Explicit prompt engineering parameters
- Educational comments explaining decisions
- Support for multiple model providers (AWS Bedrock, OpenAI, Anthropic, Gemini)

LEARNING OBJECTIVES:
1. Understand prompt component relationships
2. See prompt engineering parameters in action
3. Learn model-specific configuration patterns
4. Practice with real-world prompt templates

Phase 0: Basic prompt generation with clear educational structure
Phase 1: Migration to agentic approach (future)
"""

import os
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Union, Any
from dataclasses import dataclass, field
from enum import Enum

# Educational imports - clearly show what each does
import boto3  # AWS SDK for Bedrock models
import urllib.request  # For web scraping context
import html  # For HTML parsing
import re  # For pattern matching
import random  # For variation in generated content

# Configure logging for educational visibility
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("educational_prompt_generator")

# ====================================
# PROMPT ENGINEERING BEST PRACTICES
# ====================================

class PromptParameters:
    """
    Educational class showing prompt engineering parameters.
    Each parameter has a clear purpose and recommended values.
    """
    
    # TEMPERATURE: Controls randomness/creativity
    # - 0.0-0.3: Focused, deterministic responses (good for factual content)
    # - 0.4-0.7: Balanced creativity and coherence (good for articles)
    # - 0.8-1.0: High creativity, more variation (good for creative writing)
    TEMPERATURE_FACTUAL = 0.2      # For technical comparisons
    TEMPERATURE_BALANCED = 0.6     # For author bios, stories
    TEMPERATURE_CREATIVE = 0.9     # For diary entries, jokes
    
    # MAX_TOKENS: Controls response length
    # - Consider model context limits
    # - Leave room for prompt + response
    MAX_TOKENS_SHORT = 150         # For jokes, headlines
    MAX_TOKENS_MEDIUM = 500        # For stories, bios
    MAX_TOKENS_LONG = 800          # For articles, detailed content
    
    # TOP_P: Controls diversity via nucleus sampling
    # - 0.1-0.5: Focused vocabulary (formal content)
    # - 0.6-0.9: Balanced diversity (general content)
    # - 0.9-1.0: High diversity (creative content)
    TOP_P_FOCUSED = 0.3
    TOP_P_BALANCED = 0.7
    TOP_P_CREATIVE = 0.95
    
    # PRESENCE_PENALTY: Reduces repetition
    # - 0.0: No penalty (allows repetition)
    # - 0.1-0.3: Light penalty (natural repetition)
    # - 0.4-0.6: Moderate penalty (reduced repetition)
    PRESENCE_PENALTY_LIGHT = 0.1
    PRESENCE_PENALTY_MODERATE = 0.3
    
    # FREQUENCY_PENALTY: Reduces common phrases
    # - 0.0: No penalty
    # - 0.1-0.5: Light to moderate penalty
    FREQUENCY_PENALTY_LIGHT = 0.1
    FREQUENCY_PENALTY_MODERATE = 0.3

# ====================================
# MODEL CONFIGURATION
# ====================================

class ModelProvider(Enum):
    """Educational enum showing different model providers"""
    AWS_BEDROCK = "bedrock"
    OPENAI = "openai"
    ANTHROPIC_DIRECT = "anthropic"
    GOOGLE_GEMINI = "gemini"

@dataclass
class ModelConfig:
    """
    Educational model configuration showing how different providers
    are configured with their specific parameters.
    """
    provider: ModelProvider
    model_id: str
    display_name: str
    supports_text: bool = True
    supports_image: bool = False
    
    # Prompt engineering parameters
    temperature: float = 0.7
    max_tokens: int = 500
    top_p: float = 0.9
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    
    # Model-specific settings
    api_endpoint: Optional[str] = None
    requires_api_key: bool = False
    
    def __post_init__(self):
        """Educational validation of model configuration"""
        if self.temperature < 0.0 or self.temperature > 1.0:
            raise ValueError(f"Temperature must be 0.0-1.0, got {self.temperature}")
        if self.max_tokens < 1:
            raise ValueError(f"Max tokens must be positive, got {self.max_tokens}")

# ====================================
# EDUCATIONAL MODEL DEFINITIONS
# ====================================

def get_model_configurations() -> Dict[str, ModelConfig]:
    """
    Educational function showing how to configure different model providers.
    Each model has explicit parameters for learning purposes.
    """
    return {
        # AWS BEDROCK MODELS (Phase 0 - current)
        "claude-3-sonnet": ModelConfig(
            provider=ModelProvider.AWS_BEDROCK,
            model_id="anthropic.claude-3-sonnet-20240229-v1:0",
            display_name="Claude 3 Sonnet (AWS Bedrock)",
            supports_text=True,
            supports_image=False,
            temperature=PromptParameters.TEMPERATURE_BALANCED,
            max_tokens=PromptParameters.MAX_TOKENS_LONG,
            top_p=PromptParameters.TOP_P_BALANCED
        ),
        
        "claude-3-haiku": ModelConfig(
            provider=ModelProvider.AWS_BEDROCK,
            model_id="anthropic.claude-3-haiku-20240307-v1:0",
            display_name="Claude 3 Haiku (AWS Bedrock)",
            supports_text=True,
            supports_image=False,
            temperature=PromptParameters.TEMPERATURE_BALANCED,
            max_tokens=PromptParameters.MAX_TOKENS_MEDIUM,
            top_p=PromptParameters.TOP_P_BALANCED
        ),
        
        "titan-text": ModelConfig(
            provider=ModelProvider.AWS_BEDROCK,
            model_id="amazon.titan-text-express-v1",
            display_name="Amazon Titan Text Express",
            supports_text=True,
            supports_image=False,
            temperature=PromptParameters.TEMPERATURE_BALANCED,
            max_tokens=PromptParameters.MAX_TOKENS_MEDIUM,
            top_p=PromptParameters.TOP_P_BALANCED
        ),
        
        "titan-image": ModelConfig(
            provider=ModelProvider.AWS_BEDROCK,
            model_id="amazon.titan-image-generator-v1",
            display_name="Amazon Titan Image Generator",
            supports_text=False,
            supports_image=True,
            temperature=0.0,  # Image models don't use temperature
            max_tokens=0,     # Image models don't use tokens
            top_p=0.0
        ),
        
        "nova-canvas": ModelConfig(
            provider=ModelProvider.AWS_BEDROCK,
            model_id="amazon.nova-canvas-v1:0",
            display_name="Amazon Nova Canvas",
            supports_text=False,
            supports_image=True,
            temperature=0.0,
            max_tokens=0,
            top_p=0.0
        ),
        
        # OPENAI MODELS (Phase 0 addition)
        "gpt-4": ModelConfig(
            provider=ModelProvider.OPENAI,
            model_id="gpt-4",
            display_name="GPT-4 (OpenAI)",
            supports_text=True,
            supports_image=False,
            temperature=PromptParameters.TEMPERATURE_BALANCED,
            max_tokens=PromptParameters.MAX_TOKENS_LONG,
            top_p=PromptParameters.TOP_P_BALANCED,
            presence_penalty=PromptParameters.PRESENCE_PENALTY_LIGHT,
            frequency_penalty=PromptParameters.FREQUENCY_PENALTY_LIGHT,
            api_endpoint="https://api.openai.com/v1/chat/completions",
            requires_api_key=True
        ),
        
        "o3-mini": ModelConfig(
            provider=ModelProvider.OPENAI,
            model_id="o3-mini",
            display_name="O3 Mini (OpenAI)",
            supports_text=True,
            supports_image=False,
            temperature=PromptParameters.TEMPERATURE_CREATIVE,
            max_tokens=PromptParameters.MAX_TOKENS_LONG,
            top_p=PromptParameters.TOP_P_CREATIVE,
            presence_penalty=PromptParameters.PRESENCE_PENALTY_MODERATE,
            frequency_penalty=PromptParameters.FREQUENCY_PENALTY_MODERATE,
            api_endpoint="https://api.openai.com/v1/chat/completions",
            requires_api_key=True
        ),
        
        "dall-e-3": ModelConfig(
            provider=ModelProvider.OPENAI,
            model_id="dall-e-3",
            display_name="DALL-E 3 (OpenAI)",
            supports_text=False,
            supports_image=True,
            temperature=0.0,
            max_tokens=0,
            top_p=0.0,
            api_endpoint="https://api.openai.com/v1/images/generations",
            requires_api_key=True
        ),
        
        # ANTHROPIC DIRECT MODELS
        "claude-3-opus": ModelConfig(
            provider=ModelProvider.ANTHROPIC_DIRECT,
            model_id="claude-3-opus-20240229",
            display_name="Claude 3 Opus (Anthropic Direct)",
            supports_text=True,
            supports_image=False,
            temperature=PromptParameters.TEMPERATURE_BALANCED,
            max_tokens=PromptParameters.MAX_TOKENS_LONG,
            top_p=PromptParameters.TOP_P_BALANCED,
            api_endpoint="https://api.anthropic.com/v1/messages",
            requires_api_key=True
        ),
        
        # GOOGLE GEMINI MODELS
        "gemini-pro": ModelConfig(
            provider=ModelProvider.GOOGLE_GEMINI,
            model_id="gemini-pro",
            display_name="Gemini Pro (Google)",
            supports_text=True,
            supports_image=False,
            temperature=PromptParameters.TEMPERATURE_BALANCED,
            max_tokens=PromptParameters.MAX_TOKENS_LONG,
            top_p=PromptParameters.TOP_P_BALANCED,
            api_endpoint="https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent",
            requires_api_key=True
        ),
        
        "gemini-vision": ModelConfig(
            provider=ModelProvider.GOOGLE_GEMINI,
            model_id="gemini-pro-vision",
            display_name="Gemini Pro Vision (Google)",
            supports_text=False,
            supports_image=True,
            temperature=0.0,
            max_tokens=0,
            top_p=0.0,
            api_endpoint="https://generativelanguage.googleapis.com/v1beta/models/gemini-pro-vision:generateContent",
            requires_api_key=True
        )
    }

# ====================================
# EDUCATIONAL PROMPT COMPONENTS
# ====================================

@dataclass
class PromptComponent:
    """
    Educational class showing how different components influence prompts.
    Each component has a clear purpose and influence on the final output.
    """
    name: str
    description: str
    influence_on_output: str
    required: bool = True
    
    # Context data
    static_data: Optional[Dict[str, Any]] = None
    dynamic_data: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.static_data is None:
            self.static_data = {}
        if self.dynamic_data is None:
            self.dynamic_data = {}

@dataclass
class PromptTemplate:
    """
    Educational prompt template showing explicit structure.
    Each template has clear components and parameters.
    """
    prompt_id: str
    name: str
    description: str
    output_format: str
    
    # Prompt engineering parameters
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
    
    def add_component(self, component: PromptComponent):
        """Educational method to add components with their influences"""
        self.components.append(component)
        logger.info(f"Added component '{component.name}' to prompt '{self.name}'")
        logger.info(f"  Influence: {component.influence_on_output}")

# ====================================
# EDUCATIONAL PROMPT DEFINITIONS
# ====================================

def create_educational_prompt_templates() -> Dict[str, PromptTemplate]:
    """
    Educational function creating prompt templates with clear component relationships.
    Each template shows how different components influence the final output.
    """
    templates = {}
    
    # ====== LLM PROMPT: MAIN ARTICLE (Graham's Diary) ======
    main_article = PromptTemplate(
        prompt_id="llm_01",
        name="Main Article - Graham's Diary",
        description="Personal diary entry with weather, news, and family context",
        output_format="diary_entry",
        temperature=PromptParameters.TEMPERATURE_CREATIVE,
        max_tokens=PromptParameters.MAX_TOKENS_LONG,
        top_p=PromptParameters.TOP_P_CREATIVE,
        presence_penalty=PromptParameters.PRESENCE_PENALTY_LIGHT,
        frequency_penalty=PromptParameters.FREQUENCY_PENALTY_LIGHT
    )
    
    # Educational component: Character definition
    main_article.add_component(PromptComponent(
        name="character_definition",
        description="Graham's personality, background, and writing style",
        influence_on_output="Determines voice, tone, and perspective of the diary entry",
        static_data={
            "name": "Graham 'Geek with the Peak' Land",
            "age": "54 and a quarter",
            "background": "Irish-born, UK-based AI engineer and former cybersecurity architect",
            "location": "Pontesbury, Shropshire",
            "writing_style": "Adrian Mole-style diary, cheeky-optimistic, Irish-flavored"
        }
    ))
    
    # Educational component: Weather context
    main_article.add_component(PromptComponent(
        name="weather_context",
        description="Current weather conditions for the diary date",
        influence_on_output="Provides natural opening material and mood setting",
        required=True
    ))
    
    # Educational component: News headlines
    main_article.add_component(PromptComponent(
        name="news_headlines",
        description="Real news headlines for the diary date",
        influence_on_output="Provides material for 'headline hijacking' - connecting news to personal life",
        required=True
    ))
    
    # Educational component: Family context
    main_article.add_component(PromptComponent(
        name="family_context",
        description="Family members and their personalities",
        influence_on_output="Provides material for 'family follies' section",
        static_data={
            "wife": "Ester - undisputed keystone, omniscient task-master",
            "eldest": "Nelly (19) - uni-bound, dating questionable choices",
            "middle": "Saoirse (17) - guitar-shredding Shropshire Kurt Cobain",
            "youngest": "Terrence (14) - aspiring Brian O'Driscoll, rugby player",
            "dog": "Eddie - spoilt pandemic pup",
            "cat": "Puddle - new kitten, motive for acquisition unknown"
        }
    ))
    
    main_article.system_prompt = """You are Graham Land, 'the Geek with the Peak,' aged 54 and a quarter. 
You keep a droll, self-aware diary in Adrian Mole style that logs the chaos of being a freshly-minted AI engineer.

EDUCATIONAL PROMPT ENGINEERING NOTES:
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
    
    # ====== LLM PROMPT: COMPARISON ARTICLE ======
    comparison_article = PromptTemplate(
        prompt_id="llm_02",
        name="LLM Comparison Article",
        description="Technical comparison of top 5 LLMs in JSON format",
        output_format="json_table",
        temperature=PromptParameters.TEMPERATURE_FACTUAL,
        max_tokens=PromptParameters.MAX_TOKENS_MEDIUM,
        top_p=PromptParameters.TOP_P_FOCUSED,
        presence_penalty=0.0,
        frequency_penalty=0.0
    )
    
    # Educational component: Tech context
    comparison_article.add_component(PromptComponent(
        name="tech_trends",
        description="Current AI/ML trends and developments",
        influence_on_output="Ensures comparison reflects current state of AI industry",
        required=True
    ))
    
    # Educational component: Cynical perspective
    comparison_article.add_component(PromptComponent(
        name="cynical_perspective",
        description="Humorous, skeptical view of AI hype",
        influence_on_output="Provides balance to technical strengths with real-world usage",
        static_data={
            "tone": "informed yet cheekily skeptical",
            "perspective": "practical engineer's view of AI marketing vs reality"
        }
    ))
    
    comparison_article.system_prompt = """You are an expert tech humorist creating a comparison table.

EDUCATIONAL PROMPT ENGINEERING NOTES:
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
    
    # ====== LLM PROMPT: STORY ======
    story_prompt = PromptTemplate(
        prompt_id="llm_03",
        name="LLM User Story",
        description="Light-hearted story about everyday LLM use",
        output_format="short_story",
        temperature=PromptParameters.TEMPERATURE_CREATIVE,
        max_tokens=PromptParameters.MAX_TOKENS_MEDIUM,
        top_p=PromptParameters.TOP_P_CREATIVE,
        presence_penalty=PromptParameters.PRESENCE_PENALTY_LIGHT,
        frequency_penalty=PromptParameters.FREQUENCY_PENALTY_LIGHT
    )
    
    # Educational component: Everyday character
    story_prompt.add_component(PromptComponent(
        name="relatable_character",
        description="Non-technical person using LLM",
        influence_on_output="Makes AI accessible to general audience",
        static_data={
            "character_types": ["grandmother", "busy parent", "local shop owner", "retired teacher"],
            "problems": ["planning family dinner", "writing complaint letter", "understanding technology", "organizing community event"]
        }
    ))
    
    # Educational component: Unexpected twist
    story_prompt.add_component(PromptComponent(
        name="humorous_outcome",
        description="Funny, unexpected result from LLM interaction",
        influence_on_output="Provides entertainment value and memorable conclusion",
        required=True
    ))
    
    story_prompt.system_prompt = """You write light-hearted, relatable stories about everyday LLM use.

EDUCATIONAL PROMPT ENGINEERING NOTES:
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
    
    # ====== LLM PROMPT: JOKE ======
    joke_prompt = PromptTemplate(
        prompt_id="llm_04",
        name="AI Industry Joke",
        description="One-liner joke about AI industry figures",
        output_format="one_liner",
        temperature=PromptParameters.TEMPERATURE_CREATIVE,
        max_tokens=PromptParameters.MAX_TOKENS_SHORT,
        top_p=PromptParameters.TOP_P_CREATIVE,
        presence_penalty=0.0,
        frequency_penalty=0.0
    )
    
    # Educational component: Industry figures
    joke_prompt.add_component(PromptComponent(
        name="ai_personalities",
        description="Well-known AI industry figures",
        influence_on_output="Provides recognizable references for industry humor",
        static_data={
            "figures": ["Sam Altman", "Elon Musk", "Demis Hassabis", "Yann LeCun", "Geoffrey Hinton"],
            "topics": ["AI safety", "AGI timeline", "compute costs", "training data", "model capabilities"]
        }
    ))
    
    joke_prompt.system_prompt = """You create clever one-liner jokes about the AI industry.

EDUCATIONAL PROMPT ENGINEERING NOTES:
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
    
    # ====== LLM PROMPT: AUTHOR BIO ======
    author_bio = PromptTemplate(
        prompt_id="llm_05",
        name="Author Bio",
        description="Third-person bio of Graham Land",
        output_format="biography",
        temperature=PromptParameters.TEMPERATURE_BALANCED,
        max_tokens=PromptParameters.MAX_TOKENS_MEDIUM,
        top_p=PromptParameters.TOP_P_BALANCED,
        presence_penalty=PromptParameters.PRESENCE_PENALTY_LIGHT,
        frequency_penalty=PromptParameters.FREQUENCY_PENALTY_LIGHT
    )
    
    # Educational component: Professional background
    author_bio.add_component(PromptComponent(
        name="professional_background",
        description="Graham's career progression and expertise",
        influence_on_output="Establishes credibility and expertise",
        static_data={
            "current_role": "Technical Account Manager at Salt Security",
            "previous_roles": ["Manager CSM EMEA at HashiCorp", "CyberSecurity Architect"],
            "expertise": ["OpenStack", "Vault certification", "AWS SA cert", "ITIL", "AI Engineering"],
            "speaking": "Conference speaker and technical evangelist"
        }
    ))
    
    author_bio.system_prompt = """You write engaging third-person professional biographies.

EDUCATIONAL PROMPT ENGINEERING NOTES:
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
    
    # ====== IMAGE PROMPTS ======
    
    # Main article image
    main_image = PromptTemplate(
        prompt_id="img_01",
        name="Main Article Image",
        description="Village scene illustration for diary entry",
        output_format="image",
        temperature=0.0,  # Images don't use temperature
        max_tokens=0,
        top_p=0.0
    )
    
    main_image.add_component(PromptComponent(
        name="village_setting",
        description="Quintessentially English village scene",
        influence_on_output="Sets location and atmosphere for diary context",
        static_data={
            "location": "Pontesbury, Shropshire",
            "style": "Comic-realistic",
            "elements": ["English countryside", "village buildings", "satellite in sky"]
        }
    ))
    
    main_image.add_component(PromptComponent(
        name="seasonal_elements",
        description="Weather and seasonal context",
        influence_on_output="Adds visual context matching diary date and weather",
        required=True
    ))
    
    main_image.system_prompt = """Create a comic-realistic illustration of an English village scene.

EDUCATIONAL IMAGE PROMPT NOTES:
- Images don't use temperature, max_tokens, or top_p
- Focus on clear, descriptive visual elements
- Include seasonal and weather context
- Match the mood of the diary entry"""
    
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
        top_p=0.0
    )
    
    comparison_image.add_component(PromptComponent(
        name="data_visualization",
        description="Visual representation of LLM comparison data",
        influence_on_output="Makes technical comparison more accessible and engaging",
        static_data={
            "style": "D3.js realistic and colorful visualization",
            "elements": ["5 LLMs", "comparison metrics", "professional design"]
        }
    ))
    
    comparison_image.system_prompt = """Create a professional data visualization for LLM comparison."""
    
    comparison_image.user_prompt_template = """D3.js realistic and colorful visualization comparing 5 LLMs, 
professional design, clear metrics, modern data visualization style."""
    
    templates["img_02"] = comparison_image
    
    # Advertisement images (4 variations)
    for i in range(1, 5):
        ad_descriptions = [
            "Tech product spoof ad with retro styling",
            "Fake cereal box ad with tech/AI theme",
            "Vintage travel poster ad for sunny destination",
            "Mock luxury product ad with tech twist"
        ]
        
        ad_template = PromptTemplate(
            prompt_id=f"img_0{i+2}",
            name=f"Advertisement {i}",
            description=ad_descriptions[i-1],
            output_format="image",
            temperature=0.0,
            max_tokens=0,
            top_p=0.0
        )
        
        ad_template.add_component(PromptComponent(
            name="advertisement_style",
            description="Retro advertising aesthetic",
            influence_on_output="Creates nostalgic, humorous advertising parody",
            static_data={
                "style": "Comic-realistic retro advertising",
                "elements": ["vintage typography", "bright colors", "marketing copy"],
                "mood": "humorous parody"
            }
        ))
        
        ad_template.system_prompt = "Create a humorous retro-style advertisement parody."
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
        top_p=0.0
    )
    
    story_image.system_prompt = "Create a single-panel comic illustration."
    story_image.user_prompt_template = "Single-panel comic style, cozy domestic setting, cat and dog with slippers."
    
    templates["img_07"] = story_image
    
    joke_image = PromptTemplate(
        prompt_id="img_08",
        name="Joke Illustration",
        description="Editorial cartoon for AI industry joke",
        output_format="image",
        temperature=0.0,
        max_tokens=0,
        top_p=0.0
    )
    
    joke_image.system_prompt = "Create an editorial cartoon illustration."
    joke_image.user_prompt_template = "Editorial cartoon style, AI industry satire, {ai_figure} caricature."
    
    templates["img_08"] = joke_image
    
    return templates

# ====================================
# EDUCATIONAL CONTEXT BUILDERS
# ====================================

class EducationalContextBuilder:
    """
    Educational class showing how to build context for prompts.
    Each method demonstrates a different type of context gathering.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.ContextBuilder")
    
    def build_weather_context(self, date: str) -> Dict[str, str]:
        """
        Educational method: Build weather context for prompts.
        
        LEARNING OBJECTIVE: Show how external data influences prompt generation
        """
        self.logger.info(f"Building weather context for {date}")
        
        # Educational: Show different approaches based on date
        target_date = datetime.fromisoformat(date).date()
        today = datetime.now(ZoneInfo("Europe/London")).date()
        days_difference = (target_date - today).days
        
        if abs(days_difference) <= 2:
            # Recent dates: try to get real weather
            self.logger.info("Using real weather data (recent date)")
            return self._get_real_weather()
        else:
            # Historical dates: generate plausible weather
            self.logger.info("Using seasonal weather pattern (historical date)")
            return self._generate_seasonal_weather(target_date)
    
    def _get_real_weather(self) -> Dict[str, str]:
        """Educational method: Demonstrate external API integration"""
        try:
            # Educational: Show how to safely fetch external data
            url = "https://weather-broker-cdn.api.bbci.co.uk/en/forecast/aggregated/2640129"
            req = urllib.request.Request(url, headers={"User-Agent": "CraicGPT-Educational/1.0"})
            
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                
            # Educational: Show data parsing
            forecast = data.get("forecast", {})
            daily = forecast.get("daily", [{}])[0]
            
            return {
                "today": daily.get("summary", "Weather data unavailable"),
                "tonight": daily.get("detailed", [{}])[0].get("summary", ""),
                "source": "BBC Weather API"
            }
        except Exception as e:
            self.logger.warning(f"Weather API failed: {e}")
            return self._generate_seasonal_weather(datetime.now().date())
    
    def _generate_seasonal_weather(self, date: datetime.date) -> Dict[str, str]:
        """Educational method: Generate contextually appropriate weather"""
        self.logger.info(f"Generating seasonal weather for {date}")
        
        # Educational: Show how to create plausible context
        seasonal_patterns = {
            "winter": ["Frost and fog", "Light snow possible", "Cloudy and cold"],
            "spring": ["Spring showers", "Mild and breezy", "Sunny spells"],
            "summer": ["Warm and sunny", "Scattered showers", "Pleasant breeze"],
            "autumn": ["Autumn mist", "Crisp and clear", "Golden sunshine"]
        }
        
        # Educational: Simple season calculation
        month = date.month
        if month in [12, 1, 2]:
            season = "winter"
        elif month in [3, 4, 5]:
            season = "spring"
        elif month in [6, 7, 8]:
            season = "summer"
        else:
            season = "autumn"
        
        patterns = seasonal_patterns[season]
        weather = random.choice(patterns)
        
        return {
            "today": f"{weather} in Pontesbury, Shropshire",
            "tonight": f"{random.choice(patterns)} expected",
            "source": "seasonal_pattern"
        }
    
    def build_news_context(self, date: str) -> Dict[str, List[str]]:
        """
        Educational method: Build news context for prompts.
        
        LEARNING OBJECTIVE: Show how current events influence content generation
        """
        self.logger.info(f"Building news context for {date}")
        
        # Educational: Show different sources and their purposes
        news_sources = {
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
        
        news_context = {}
        
        for category, urls in news_sources.items():
            headlines = []
            for url in urls:
                try:
                    # Educational: Show safe web scraping
                    req = urllib.request.Request(url, headers={"User-Agent": "CraicGPT-Educational/1.0"})
                    with urllib.request.urlopen(req, timeout=10) as response:
                        content = response.read().decode('utf-8', errors='ignore')
                    
                    # Educational: Show headline extraction
                    found_headlines = self._extract_headlines(content)
                    headlines.extend(found_headlines[:3])  # Limit per source
                    
                    if len(headlines) >= 5:  # Limit per category
                        break
                        
                except Exception as e:
                    self.logger.warning(f"Failed to fetch {url}: {e}")
                    continue
            
            news_context[category] = headlines[:5]  # Final limit
        
        return news_context
    
    def _extract_headlines(self, html_content: str) -> List[str]:
        """Educational method: Extract headlines from HTML"""
        patterns = [
            re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", re.IGNORECASE | re.DOTALL),
            re.compile(r'<a[^>]*class="[^"]*headline[^"]*"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL),
            re.compile(r'<span[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</span>', re.IGNORECASE | re.DOTALL)
        ]
        
        headlines = []
        for pattern in patterns:
            matches = pattern.findall(html_content)
            for match in matches:
                # Educational: Show text cleaning
                clean_text = html.unescape(re.sub(r"<[^>]*>", " ", match)).strip()
                if len(clean_text) > 20 and clean_text not in headlines:
                    headlines.append(clean_text)
                    if len(headlines) >= 10:
                        return headlines
        
        return headlines

# ====================================
# EDUCATIONAL PROMPT BUILDER
# ====================================

class EducationalPromptBuilder:
    """
    Educational class for building complete prompts.
    Demonstrates how components combine to create effective prompts.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.PromptBuilder")
        self.context_builder = EducationalContextBuilder()
        self.templates = create_educational_prompt_templates()
        self.models = get_model_configurations()
    
    def build_prompt(self, prompt_id: str, date: str, context_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Educational method: Build complete prompt with all components.
        
        LEARNING OBJECTIVE: Show how all components combine into final prompt
        """
        self.logger.info(f"Building prompt {prompt_id} for {date}")
        
        if prompt_id not in self.templates:
            raise ValueError(f"Unknown prompt template: {prompt_id}")
        
        template = self.templates[prompt_id]
        
        # Educational: Show component processing
        self.logger.info(f"Processing {len(template.components)} components:")
        for component in template.components:
            self.logger.info(f"  - {component.name}: {component.description}")
        
        # Educational: Build context for each component
        component_data = {}
        for component in template.components:
            if component.name in context_data:
                component_data[component.name] = context_data[component.name]
            else:
                self.logger.warning(f"Missing context data for component: {component.name}")
        
        # Educational: Show prompt assembly
        system_prompt = template.system_prompt.format(
            temperature=template.temperature,
            max_tokens=template.max_tokens,
            top_p=template.top_p,
            presence_penalty=template.presence_penalty,
            frequency_penalty=template.frequency_penalty
        )
        
        user_prompt = template.user_prompt_template.format(
            date=date,
            **component_data
        )
        
        # Educational: Show final prompt structure
        final_prompt = {
            "prompt_id": prompt_id,
            "template_name": template.name,
            "date": date,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "parameters": {
                "temperature": template.temperature,
                "max_tokens": template.max_tokens,
                "top_p": template.top_p,
                "presence_penalty": template.presence_penalty,
                "frequency_penalty": template.frequency_penalty
            },
            "components_used": [comp.name for comp in template.components],
            "context_data": component_data
        }
        
        self.logger.info(f"Built prompt with {len(final_prompt['system_prompt'])} system chars, "
                        f"{len(final_prompt['user_prompt'])} user chars")
        
        return final_prompt

# ====================================
# EDUCATIONAL MAIN HANDLER
# ====================================

def lambda_handler(event, context):
    """
    Educational Lambda handler showing complete prompt generation workflow.
    
    LEARNING OBJECTIVES:
    1. See how all components work together
    2. Understand error handling and logging
    3. Learn about configuration and flexibility
    4. Practice with real-world prompt engineering
    """
    
    logger.info("=== Educational Prompt Generator Started ===")
    logger.info(f"Event: {json.dumps(event, indent=2)}")
    
    try:
        # Educational: Show configuration reading
        start_date = event.get("START_DATE", os.getenv("START_DATE"))
        end_date = event.get("END_DATE", os.getenv("END_DATE"))
        
        if not start_date:
            start_date = datetime.now(ZoneInfo("Europe/London")).date().isoformat()
        if not end_date:
            end_date = start_date
        
        logger.info(f"Processing date range: {start_date} to {end_date}")
        
        # Educational: Show date range generation
        dates = []
        current_date = datetime.fromisoformat(start_date).date()
        end_date_obj = datetime.fromisoformat(end_date).date()
        
        while current_date <= end_date_obj:
            dates.append(current_date.isoformat())
            current_date += timedelta(days=1)
        
        logger.info(f"Generated {len(dates)} dates: {dates}")
        
        # Educational: Initialize builders
        context_builder = EducationalContextBuilder()
        prompt_builder = EducationalPromptBuilder()
        
        # Educational: Show AWS S3 configuration
        s3_client = boto3.client("s3")
        bucket_name = os.environ.get("PROMPT_BUCKET", "craicgpt-prompts")
        
        generated_prompts = []
        
        # Educational: Process each date
        for date in dates:
            logger.info(f"\n=== Processing {date} ===")
            
            # Educational: Build context for this date
            logger.info("Building context components...")
            
            weather_context = context_builder.build_weather_context(date)
            news_context = context_builder.build_news_context(date)
            
            # Educational: Show context aggregation
            context_data = {
                "weather_today": weather_context["today"],
                "weather_tonight": weather_context.get("tonight", ""),
                "news_headlines": news_context.get("tech", [])[:3],
                "local_events": [f"Community event in {date}"],
                "tech_trends": ["AI development", "cybersecurity", "cloud computing"],
                "ai_trends": ["LLM capabilities", "AI safety", "compute efficiency"],
                "ai_figure": "Sam Altman",
                "ai_topic": "AGI timeline",
                "character_type": "busy parent",
                "problem": "planning family dinner",
                "current_role": "Technical Account Manager at Salt Security",
                "professional_background": "HashiCorp, cybersecurity, cloud architecture",
                "technical_expertise": "OpenStack, Vault, AWS, ITIL",
                "personal_interests": "motorbike, paddle-board, rpi projects",
                "family_updates": "Eddie's latest antics, Puddle's curtain climbing",
                "seasonal_elements": "winter frost, cozy atmosphere",
                "weather_mood": "crisp winter air",
                "day_of_week": datetime.fromisoformat(date).strftime("%A"),
                "date_formatted": datetime.fromisoformat(date).strftime("%B %d, %Y")
            }
            
            logger.info(f"Context built with {len(context_data)} components")
            
            # Educational: Generate all prompts for this date
            prompt_templates = create_educational_prompt_templates()
            
            for prompt_id, template in prompt_templates.items():
                logger.info(f"\n--- Generating {prompt_id}: {template.name} ---")
                
                try:
                    # Educational: Build the prompt
                    prompt_data = prompt_builder.build_prompt(prompt_id, date, context_data)
                    
                    # Educational: Show storage key generation (MUST match existing format)
                    year, month, day = date.split("-")
                    s3_key = f"static_assets/content/prompts/{year}/{month}/{day}/{prompt_id}.json"
                    
                    # Educational: Store in S3 with BACKWARD COMPATIBLE format
                    # The existing llmHandler and imageGenHandler expect this exact structure
                    storage_data = {
                        "prompt_id": prompt_id,
                        "prompt_type": template.output_format,
                        "date": date,
                        "prompt": prompt_data["user_prompt"],  # <-- CRITICAL: This is what handlers read
                        "models": get_models_for_template(template),
                        "context": prompt_data["context_data"],
                        "educational_metadata": {
                            "template_name": template.name,
                            "system_prompt": prompt_data["system_prompt"],
                            "parameters": prompt_data["parameters"],
                            "components_used": prompt_data["components_used"]
                        }
                    }
                    
                    # Add educational parameters to root level for visibility
                    if template.temperature is not None:
                        storage_data["temperature"] = template.temperature
                    if template.max_tokens is not None:
                        storage_data["max_tokens"] = template.max_tokens
                    if template.top_p is not None:
                        storage_data["top_p"] = template.top_p
                    
                    s3_client.put_object(
                        Bucket=bucket_name,
                        Key=s3_key,
                        Body=json.dumps(storage_data, indent=2, ensure_ascii=False),
                        ContentType="application/json"
                    )
                    
                    generated_prompts.append(s3_key)
                    logger.info(f"✅ Stored: {s3_key}")
                    
                except Exception as e:
                    logger.error(f"❌ Error generating {prompt_id}: {e}")
                    continue
        
        # Educational: Show final summary
        logger.info(f"\n=== Generation Complete ===")
        logger.info(f"Total prompts generated: {len(generated_prompts)}")
        logger.info(f"Dates processed: {len(dates)}")
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "SUCCESS",
                "dates_processed": dates,
                "prompts_generated": len(generated_prompts),
                "s3_keys": generated_prompts,
                "educational_summary": {
                    "components_demonstrated": [
                        "Weather context building",
                        "News scraping and processing",
                        "Prompt template system",
                        "Parameter configuration",
                        "Multi-model support",
                        "Context aggregation",
                        "S3 storage patterns"
                    ],
                    "prompt_engineering_techniques": [
                        "Temperature tuning for creativity vs accuracy",
                        "Token limits for response length",
                        "Top-p for vocabulary diversity",
                        "Presence/frequency penalties for repetition control",
                        "System vs user prompt separation",
                        "Component-based prompt building"
                    ]
                }
            })
        }
        
    except Exception as e:
        logger.error(f"❌ Handler error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "ERROR",
                "error": str(e),
                "educational_note": "Check logs for detailed error analysis"
            })
        }

# ====================================
# EDUCATIONAL TESTING FUNCTIONS
# ====================================

def get_models_for_template(template: PromptTemplate) -> List[str]:
    """
    Educational function: Get appropriate models for a template.
    Shows how to filter models by capability.
    """
    models = get_model_configurations()
    
    if template.output_format == "image":
        # Image templates need image-capable models
        return [name for name, config in models.items() if config.capability == ModelCapability.IMAGE_GENERATION]
    else:
        # Text templates need text-capable models  
        return [name for name, config in models.items() if config.capability == ModelCapability.TEXT_GENERATION or config.capability == ModelCapability.MULTIMODAL]

def test_educational_components():
    """
    Educational function to test prompt components.
    Run this locally to understand how components work.
    """
    print("=== Educational Component Testing ===")
    
    # Test model configurations
    models = get_model_configurations()
    print(f"\nConfigured models: {len(models)}")
    for name, config in models.items():
        print(f"  {name}: {config.display_name}")
        print(f"    Provider: {config.provider.value}")
        print(f"    Temperature: {config.temperature}")
        print(f"    Max tokens: {config.max_tokens}")
        print(f"    Supports: text={config.supports_text}, image={config.supports_image}")
    
    # Test prompt templates
    templates = create_educational_prompt_templates()
    print(f"\nPrompt templates: {len(templates)}")
    for prompt_id, template in templates.items():
        print(f"  {prompt_id}: {template.name}")
        print(f"    Components: {len(template.components)}")
        print(f"    Temperature: {template.temperature}")
        print(f"    Max tokens: {template.max_tokens}")
        for comp in template.components:
            print(f"      - {comp.name}: {comp.description}")
    
    # Test context building
    context_builder = EducationalContextBuilder()
    test_date = "2025-01-15"
    
    print(f"\nTesting context building for {test_date}")
    weather = context_builder.build_weather_context(test_date)
    print(f"Weather context: {weather}")
    
    print("\n=== Component Testing Complete ===")

if __name__ == "__main__":
    # Educational: Allow local testing
    test_educational_components()