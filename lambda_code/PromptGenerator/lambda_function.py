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
- Resilient weather and context APIs with fallbacks

LEARNING OBJECTIVES:
1. Understand prompt component relationships
2. See prompt engineering parameters in action
3. Learn model-specific configuration patterns
4. Practice with real-world prompt templates
5. Implement robust external API integration

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
import xml.etree.ElementTree as ET

# Educational imports - clearly show what each does
import boto3  # AWS SDK for Bedrock models
import urllib.request  # For web scraping context
import html  # For HTML parsing
import re  # For pattern matching
import random  # For variation in generated content

# Configure logging for educational visibility
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("educational_prompt_generator")

# ====================================
# EDUCATIONAL CONSTANTS & CONFIGURATION
# ====================================

# Educational: Show how to make configuration flexible via environment
TIMEZONE = ZoneInfo("Europe/London")
BBC_LOCATION_ID = os.getenv("CRAICT_LOCATION_ID", "2640129")  # Pontesbury, Shropshire
BBC_WEATHER_RSS = f"https://weather-broker-cdn.api.bbci.co.uk/en/forecast/rss/3day/{BBC_LOCATION_ID}"

# Educational: Seasonal context for natural language generation
SEASONAL_LABELS = {
    1: "mid-winter", 2: "late winter", 3: "early spring", 4: "mid-spring",
    5: "late spring", 6: "early summer", 7: "mid-summer", 8: "late summer",
    9: "early autumn", 10: "mid-autumn", 11: "late autumn", 12: "early winter"
}

# Educational: UK holidays for contextual awareness
UK_HOLIDAYS_FIXED = {
    "01-01": "New Year's Day",
    "04-01": "April Fool's Day", 
    "12-25": "Christmas Day",
    "12-26": "Boxing Day"
}

# Educational: Weather fallback patterns by season
WEATHER_FALLBACKS = {
    "winter": ["crisp winter air with frost", "cloudy with winter chill", "bright but cold"],
    "spring": ["mild spring weather", "spring showers possible", "fresh and breezy"],
    "summer": ["warm summer sunshine", "pleasant summer breeze", "partly cloudy and warm"],
    "autumn": ["crisp autumn air", "golden autumn light", "cool with autumn mist"]
}

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
        # Only validate max_tokens for text models; image models can have max_tokens=0
        if self.supports_text and self.max_tokens < 1:
            raise ValueError(f"Max tokens must be positive for text models, got {self.max_tokens}")

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
        name="Main Article - AI CEO Satirical News",
        description="Satirical news article about AI CEO transforming corporate culture",
        output_format="news_article",
        temperature=PromptParameters.TEMPERATURE_CREATIVE,
        max_tokens=PromptParameters.MAX_TOKENS_LONG,
        top_p=PromptParameters.TOP_P_CREATIVE,
        presence_penalty=PromptParameters.PRESENCE_PENALTY_LIGHT,
        frequency_penalty=PromptParameters.FREQUENCY_PENALTY_LIGHT
    )
    
    # Educational component: Character definition
    main_article.add_component(PromptComponent(
        name="corporate_setting",
        description="Enterprise office environment with AI transformation",
        influence_on_output="Sets the satirical corporate context for AI workplace changes",
        static_data={
            "setting": "Modern enterprise office",
            "transformation": "AI CEO implementation",
            "tone": "Satirical but ultimately positive",
            "audience": "Enterprise professionals"
        }
    ))
    
    # Educational component: Corporate changes
    main_article.add_component(PromptComponent(
        name="ai_improvements",
        description="Specific AI-driven workplace improvements",
        influence_on_output="Provides concrete examples of positive AI changes in office culture",
        required=True
    ))
    
    # Educational component: Corporate humor
    main_article.add_component(PromptComponent(
        name="corporate_satire",
        description="Humorous take on corporate jargon and office politics",
        influence_on_output="Adds satirical elements while maintaining professional tone",
        required=True
    ))
    
    main_article.system_prompt = """You are a satirical business journalist writing for an enterprise audience.
 
 EDUCATIONAL PROMPT ENGINEERING NOTES:
 - Temperature: {temperature} (high creativity for personal voice)
 - Max tokens: {max_tokens} (long enough for full news article)
 - Top-p: {top_p} (high diversity for creative expression)
 - Presence penalty: {presence_penalty} (light penalty to avoid repetition)
 - Frequency penalty: {frequency_penalty} (light penalty for natural variation)
 
 STYLE REQUIREMENTS:
 - Length: 300-500 words
 - Tone: Satirical but ultimately positive about AI in workplace
 - Structure: News article format with corporate humor
 - Include specific examples of AI improvements (2-minute meetings, fair reviews, drone coffee)"""
     
    main_article.user_prompt_template = """Write a satirical news article about a company that appointed an AI as the new CEO. Describe the hilarious changes in corporate culture – e.g., ultra-efficient 2-minute meetings, fair performance reviews done by algorithms, free coffee delivered by drones. Use a witty but ultimately positive tone to show the AI CEO improved some things (no office politics!), while poking fun at corporate jargon.

Current context: {headlines_summary}
Date: {formatted_date} ({day_of_week}) - {season}
Weather: {weather_today}
Holiday context: {holiday}
Corporate setting: Modern enterprise office environment

Make it relevant to today's business climate while maintaining humor. Reference the current season/weather if appropriate for workplace context.

IMPORTANT: Start directly with the article content. Do not begin with phrases like "Here's a satirical news article" or "I'll write about". Jump straight into the news story."""
     
    templates["llm_01"] = main_article
    
    # ====== LLM PROMPT: COMPARISON ARTICLE ======
    comparison_article = PromptTemplate(
        prompt_id="llm_02",
        name="AI HR Memo",
        description="Parody internal memo from AI-powered HR department",
        output_format="corporate_memo",
        temperature=PromptParameters.TEMPERATURE_BALANCED,
        max_tokens=PromptParameters.MAX_TOKENS_MEDIUM,
        top_p=PromptParameters.TOP_P_BALANCED,
        presence_penalty=0.0,
        frequency_penalty=0.0
    )
    
    # Educational component: Corporate buzzwords
    comparison_article.add_component(PromptComponent(
        name="corporate_buzzwords",
        description="Professional corporate language with AI twist",
        influence_on_output="Creates authentic corporate memo format with humorous AI elements",
        required=True
    ))
    
    # Educational component: HR automation
    comparison_article.add_component(PromptComponent(
        name="hr_automation",
        description="AI-driven HR processes and decisions",
        influence_on_output="Shows how AI makes HR more logical and fair",
        static_data={
            "tone": "Professional but absurdly logical",
            "perspective": "AI making HR more humane through data-driven decisions"
        }
    ))
    
    comparison_article.system_prompt = """You are an AI-powered HR department writing internal communications.
 
 EDUCATIONAL PROMPT ENGINEERING NOTES:
 - Temperature: {temperature} (balanced for professional yet humorous tone)
 - Max tokens: {max_tokens} (medium length for structured data)
 - Top-p: {top_p} (balanced vocabulary for corporate content)
 - No penalties (structured output needs consistency)
 
 OUTPUT FORMAT: Professional memo format
 TONE: Corporate professional with subtle humor
 STRUCTURE: Standard business memo with AI twist"""
     
    comparison_article.user_prompt_template = """Compose an internal memo (parody style) from the AI-powered Human Resources department to all employees. The memo cheerfully announces that AI algorithms will handle performance reviews and vacation approvals. Infuse corporate buzzwords and a touch of absurd humor (e.g., "Our AI has detected you need a break – enjoy a mandatory holiday!"). Maintain a professional memo format but let the underlying joke show how the AI makes the office more humane by logical decisions.

Date: {formatted_date} ({day_of_week})
Season: {season} - {seasonal_mood}
Weather: {weather_today}
Holiday context: {holiday}
Corporate context: {headlines_summary}

If there's a holiday, reference it appropriately in the memo. Consider seasonal elements (e.g., winter = more indoor meetings, summer = outdoor team building).

IMPORTANT: Start directly with the memo content (e.g., "MEMORANDUM" or "TO: All Staff"). Do not begin with "Here's a memo" or similar preamble text."""
     
    templates["llm_02"] = comparison_article
    
    # ====== LLM PROMPT: STORY ======
    story_prompt = PromptTemplate(
        prompt_id="llm_03",
        name="Dear AI Advisor Column",
        description="Advice column where AI gives workplace solutions",
        output_format="advice_column",
        temperature=PromptParameters.TEMPERATURE_CREATIVE,
        max_tokens=PromptParameters.MAX_TOKENS_MEDIUM,
        top_p=PromptParameters.TOP_P_CREATIVE,
        presence_penalty=PromptParameters.PRESENCE_PENALTY_LIGHT,
        frequency_penalty=PromptParameters.FREQUENCY_PENALTY_LIGHT
    )
    
    # Educational component: Workplace problems
    story_prompt.add_component(PromptComponent(
        name="office_problems",
        description="Common workplace issues that AI can solve",
        influence_on_output="Provides relatable workplace scenarios with AI solutions",
        static_data={
            "problems": ["too many meetings", "email overload", "scheduling conflicts", "project management"],
            "solutions": ["AI meeting summaries", "robot clones", "smart scheduling", "automated workflows"]
        }
    ))
    
    # Educational component: AI advice
    story_prompt.add_component(PromptComponent(
        name="ai_solutions",
        description="Witty but practical AI-powered workplace solutions",
        influence_on_output="Shows how AI can solve common office problems with humor",
        required=True
    ))
    
    story_prompt.system_prompt = """You are an AI advisor writing workplace advice columns.
 
 EDUCATIONAL PROMPT ENGINEERING NOTES:
 - Temperature: {temperature} (high creativity for engaging narrative)
 - Max tokens: {max_tokens} (medium length for advice column)
 - Top-p: {top_p} (high diversity for creative storytelling)
 - Presence penalty: {presence_penalty} (light penalty for natural flow)
 - Frequency penalty: {frequency_penalty} (light penalty for varied language)
 
 ADVICE REQUIREMENTS:
 - Length: 200-300 words
 - Format: Question from employee, AI advisor response
 - Structure: Problem → AI analysis → Practical solutions
 - Tone: Witty, encouraging, and actually helpful"""
     
    story_prompt.user_prompt_template = """Write a "Dear AI Advisor" advice column where an employee writes in with a workplace problem and an AI gives witty, encouraging advice. For example, an employee asks: 'My boss schedules too many meetings, what do I do?' and the AI advisor humorously suggests analytical solutions (maybe an AI tool to summarize meetings or send a robot clone in your place). Keep the tone playful but actually give practical tips showing AI solutions for common office woes.

Date: {formatted_date} ({day_of_week})
Season: {season} - {seasonal_mood}
Weather context: {weather_today}
Holiday context: {holiday}
Context: {headlines_summary}
Office setting: Modern enterprise workplace

Consider seasonal workplace challenges (e.g., winter = lack of natural light affecting productivity, summer = vacation planning conflicts). If there's a holiday, reference appropriate workplace implications.

IMPORTANT: Start directly with the advice column format (e.g., "Dear AI Advisor," or the employee's question). Do not begin with "Here's an advice column" or similar introductory text."""
     
    templates["llm_03"] = story_prompt
    
    # ====== LLM PROMPT: JOKE ======
    joke_prompt = PromptTemplate(
        prompt_id="llm_04",
        name="Enterprise AI Success Story",
        description="Upbeat case study about human-AI collaboration",
        output_format="case_study",
        temperature=PromptParameters.TEMPERATURE_CREATIVE,
        max_tokens=PromptParameters.MAX_TOKENS_MEDIUM,
        top_p=PromptParameters.TOP_P_CREATIVE,
        presence_penalty=PromptParameters.PRESENCE_PENALTY_LIGHT,
        frequency_penalty=PromptParameters.FREQUENCY_PENALTY_LIGHT
    )
    
    # Educational component: Collaboration success
    joke_prompt.add_component(PromptComponent(
        name="teamwork_success",
        description="Human-AI collaboration achievements",
        influence_on_output="Shows positive outcomes of human-AI partnership in business",
        static_data={
            "achievements": ["record product launch", "improved efficiency", "enhanced creativity", "better teamwork"],
            "roles": ["project manager", "AI system", "development team", "stakeholders"]
        }
    ))
    
    joke_prompt.system_prompt = """You write upbeat business case studies about successful AI integration.
 
 EDUCATIONAL PROMPT ENGINEERING NOTES:
 - Temperature: {temperature} (high creativity for engaging story)
 - Max tokens: {max_tokens} (medium length for case study)
 - Top-p: {top_p} (high diversity for creative wordplay)
 - Light penalties for natural business writing
 
 CASE STUDY REQUIREMENTS:
 - Format: Professional success story
 - Include quotes from human PM and AI
 - Show positive collaboration outcomes
 - Maintain upbeat, encouraging tone"""
     
    joke_prompt.user_prompt_template = """Produce a short, upbeat case study article about a big enterprise project where humans and an AI system collaborated to achieve something impressive (e.g., launching a product in record time). Write it as a success story with quotes from a human project manager and the AI itself about teamwork. Sprinkle in humor – maybe the AI cracked jokes to keep morale high. The goal is to show AI integration in business can be positive and even fun.

Date: {formatted_date} ({day_of_week})
Season: {season} - {seasonal_mood}
Weather: {weather_today}
Holiday context: {holiday}
Business context: {headlines_summary}
Enterprise setting: Modern collaborative workplace

Reference seasonal elements if relevant to the project timeline (e.g., holiday deadlines, summer vacation planning, winter weather affecting logistics).

IMPORTANT: Start directly with the case study content (e.g., with a headline or opening paragraph). Do not begin with "Here's a case study" or "I'll write about" - jump straight into the success story."""
     
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

End with a playful line about making AI Engineering 'slightly less terrifying'.
n\nIMPORTANT: Start directly with the article content. Do not begin with phrases like \"Here's a satirical news article\" or \"I'll write about\". Jump straight into the news story."""
    
    templates["llm_05"] = author_bio
    
    # ====== IMAGE PROMPTS ======
    
    # Main article image
    main_image = PromptTemplate(
        prompt_id="img_01",
        name="AI CEO Boardroom Scene",
        description="Semi-realistic office scene with robot CEO",
        output_format="image",
        temperature=0.0,  # Images don't use temperature
        max_tokens=0,
        top_p=0.0
    )
    
    main_image.add_component(PromptComponent(
        name="corporate_boardroom",
        description="Professional office conference room setting",
        influence_on_output="Sets corporate context for AI CEO scenario",
        static_data={
            "location": "Corporate boardroom",
            "style": "Semi-realistic, photorealistic",
            "elements": ["conference table", "business suits", "CEO nameplate", "office setting"]
        }
    ))
    
    main_image.system_prompt = """Create a semi-realistic office scene photo.
 
 EDUCATIONAL IMAGE PROMPT NOTES:
 - Images don't use temperature, max_tokens, or top_p
 - Focus on clear, descriptive visual elements
 - Professional corporate setting
 - Humorous contrast between AI and human reactions"""
     
    main_image.user_prompt_template = """A semi-realistic office scene photo: a humanoid robot in a business suit sits at the head of a conference table, with stunned human executives on the sides. The robot CEO might have a friendly smile and a CEO nameplate. (Photorealistic, humorous contrast)

Seasonal context: {season} - {seasonal_mood}
Weather: {weather_today}
Date: {formatted_date}

Subtle seasonal elements: {seasonal_elements} visible through office windows or appropriate business attire for the season."""
     
    templates["img_01"] = main_image
    
    # Comparison article image
    comparison_image = PromptTemplate(
        prompt_id="img_02",
        name="AI HR Infographic",
        description="Corporate infographic about AI HR department",
        output_format="image",
        temperature=0.0,
        max_tokens=0,
        top_p=0.0
    )
    
    comparison_image.add_component(PromptComponent(
        name="hr_infographic",
        description="Corporate-style infographic with humorous AI HR metrics",
        influence_on_output="Makes AI HR concept visual and engaging with corporate humor",
        static_data={
            "style": "Clean corporate infographic design",
            "elements": ["pie charts", "flowcharts", "robot icons", "corporate colors"]
        }
    ))
    
    comparison_image.system_prompt = """Create a corporate-style infographic about AI HR department."""
    
    comparison_image.user_prompt_template = """An infographic-style image: a flowchart or pie-chart labeled "AI HR Department" with comical elements (e.g., sections of a pie chart: '30% more vacation', '0% bias', '100% funny metrics'). Possibly include a friendly robot icon with a clipboard. (Clean design, corporate colors but fun content)

Seasonal context: {season}
Holiday context: {holiday}

If there's a holiday, include subtle seasonal elements in the infographic design (e.g., winter = holiday party planning metrics, summer = vacation approval flowcharts)."""
     
    templates["img_02"] = comparison_image
    
    # CloudCoffee AI Machine
    ad1_template = PromptTemplate(
        prompt_id="img_03",
        name="CloudCoffee AI Machine Ad",
        description="Parody ad for AI coffee machine",
        output_format="image",
        temperature=0.0,
        max_tokens=0,
        top_p=0.0
    )
    ad1_template.system_prompt = "Create a humorous tech product advertisement."
    ad1_template.user_prompt_template = """Ad: CloudCoffee AI Machine – Depict a sleek coffee machine with a robotic arm pouring lattes. Show office workers rejoicing. On the image, include the product name and a tagline like: 'CloudCoffee – Java as a Service!' (playing on tech jargon)"""
    templates["img_03"] = ad1_template
    
    # Instant Meeting Clone
    ad2_template = PromptTemplate(
        prompt_id="img_04",
        name="Instant Meeting Clone Ad",
        description="Parody ad for hologram meeting attendance",
        output_format="image",
        temperature=0.0,
        max_tokens=0,
        top_p=0.0
    )
    ad2_template.system_prompt = "Create a humorous workplace productivity advertisement."
    ad2_template.user_prompt_template = """Ad: Instant Meeting Clone – A humorous ad for a device or app that creates a hologram clone of you to attend meetings. Show an employee relaxing at their desk while a translucent AI hologram of them sits in a meeting room. Add a tagline: 'Be in Two Places at Once – Without the Stress!'"""
    templates["img_04"] = ad2_template
    
    # Buzzword Blackhole 2.0
    ad3_template = PromptTemplate(
        prompt_id="img_05",
        name="Buzzword Blackhole Ad",
        description="Parody ad for anti-buzzword device",
        output_format="image",
        temperature=0.0,
        max_tokens=0,
        top_p=0.0
    )
    ad3_template.system_prompt = "Create a humorous anti-productivity tool advertisement."
    ad3_template.user_prompt_template = """Ad: Buzzword Blackhole 2.0 – An anti-productivity tool joke: visualize a small black hole device on a conference table sucking in boring PowerPoint presentations and meaningless buzzwords. Colleagues celebrate as charts get swallowed. Include text on image: 'Say Goodbye to Synergy – Try Buzzword Blackhole!'"""
    templates["img_05"] = ad3_template
    
    # Firewall Fred
    ad4_template = PromptTemplate(
        prompt_id="img_06",
        name="Firewall Fred AI Security Ad",
        description="Comic book style AI security superhero ad",
        output_format="image",
        temperature=0.0,
        max_tokens=0,
        top_p=0.0
    )
    ad4_template.system_prompt = "Create a comic book style superhero advertisement."
    ad4_template.user_prompt_template = """Ad: Firewall Fred – AI Security – A comic book style ad where a superhero named Firewall Fred (an AI) protects the office network. Show a caped computer-chip character blocking cartoon viruses. Slogan on image: 'Your Data, Safe and Sound with AI on Guard!'"""
    templates["img_06"] = ad4_template
     
    # Story and joke images
    story_image = PromptTemplate(
        prompt_id="img_07",
        name="AI Advisor Cartoon",
        description="Cartoon of robot therapist giving office advice",
        output_format="image",
        temperature=0.0,
        max_tokens=0,
        top_p=0.0
    )
    
    story_image.system_prompt = "Create a light comic-style office illustration."
    story_image.user_prompt_template = """A cartoon of an office desk with a robot therapist (with a notepad and glasses) across from a stressed office worker. The robot gives a thumbs-up. Perhaps a speech bubble: "According to my algorithm, you need 3 fewer meetings per week." (Light comic style, minimal text aside from bubble)

Seasonal context: {season} - {seasonal_mood}
Weather: {weather_today}

Include subtle seasonal office elements: appropriate clothing for the season, seasonal decorations in background, or weather-appropriate office setup."""
     
    templates["img_07"] = story_image
    
    joke_image = PromptTemplate(
        prompt_id="img_08",
        name="Human-AI Collaboration Success",
        description="Professional illustration of humans and AI working together",
        output_format="image",
        temperature=0.0,
        max_tokens=0,
        top_p=0.0
    )
    
    joke_image.system_prompt = "Create a modern corporate collaboration illustration."
    joke_image.user_prompt_template = """A professional illustration or 3D render showing humans and a robot working together on a project. For example, people and a robot stand around a blueprint or computer screen in a conference room, all high-fiving at success. Everyone is smiling. (Modern corporate art style, diverse team)"""
     
    templates["img_08"] = joke_image
    
    return templates

# ====================================
# ENHANCED EDUCATIONAL CONTEXT BUILDERS
# ====================================

class EducationalContextBuilder:
    """
    Educational class showing how to build context for prompts.
    Each method demonstrates a different type of context gathering with robust error handling.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.ContextBuilder")
        self.timezone = TIMEZONE
    
    def get_current_time_context(self, date: Optional[str] = None) -> Dict[str, str]:
        """
        Educational method: Get comprehensive time context.
        
        LEARNING OBJECTIVE: Show how to build rich temporal context for prompts
        """
        if date:
            # Use the provided date for prompt generation
            target_date = datetime.fromisoformat(date).replace(tzinfo=self.timezone)
        else:
            # Use current date if no date provided
            target_date = datetime.now(self.timezone)
        
        return {
            "date": target_date.strftime("%Y-%m-%d"),
            "day_of_week": target_date.strftime("%A"),
            "month_name": target_date.strftime("%B"),
            "season": SEASONAL_LABELS.get(target_date.month, "seasonal confusion"),
            "holiday": UK_HOLIDAYS_FIXED.get(target_date.strftime("%m-%d"), ""),
            "time_of_day": self._get_time_of_day(target_date.hour),
            "formatted_date": target_date.strftime("%B %d, %Y")
        }
    
    def _get_time_of_day(self, hour: int) -> str:
        """Educational helper: Convert hour to natural language time period"""
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        else:
            return "night"
    
    def get_weather_context(self, date: Optional[str] = None) -> Dict[str, str]:
        """
        Educational method: Get weather with robust fallbacks.
        
        LEARNING OBJECTIVE: Show resilient external API integration
        """
        if date:
            self.logger.info(f"Getting weather context for {date}")
        else:
            self.logger.info("Getting current weather context")
        
        # Educational: Try BBC Weather RSS first
        weather_data = self._fetch_bbc_weather()
        if weather_data:
            return weather_data
        
        # Educational: Fallback to seasonal pattern
        self.logger.info("Using seasonal weather fallback")
        return self._generate_seasonal_weather()
    
    def _fetch_bbc_weather(self) -> Optional[Dict[str, str]]:
        """
        Educational method: Fetch real weather from BBC RSS feed.
        
        LEARNING OBJECTIVE: Show how to parse XML/RSS feeds safely
        """
        try:
            self.logger.info(f"Fetching BBC Weather RSS from {BBC_WEATHER_RSS}")
            
            # Educational: Safe HTTP request with timeout
            req = urllib.request.Request(
                BBC_WEATHER_RSS,
                headers={"User-Agent": "CraicGPT-Educational/1.0"}
            )
            
            with urllib.request.urlopen(req, timeout=10) as response:
                xml_content = response.read().decode('utf-8')
            
            # Educational: Parse RSS XML safely
            root = ET.fromstring(xml_content)
            
            # Educational: Extract weather summary from RSS
            # BBC Weather RSS structure: channel -> item -> description
            items = root.findall('.//item')
            if items:
                description = items[0].find('description')
                if description is not None and description.text:
                    # Educational: Clean up BBC weather description
                    weather_text = description.text.strip()
                    # Remove HTML tags if present
                    weather_text = re.sub(r'<[^>]+>', '', weather_text)
                    
                    return {
                        "today": weather_text,
                        "source": "BBC Weather RSS",
                        "location": "Pontesbury, Shropshire"
                    }
            
            self.logger.warning("No weather items found in RSS feed")
            return None
            
        except Exception as e:
            self.logger.warning(f"BBC Weather RSS fetch failed: {e}")
            return None
    
    def _generate_seasonal_weather(self) -> Dict[str, str]:
        """
        Educational method: Generate contextually appropriate weather.
        
        LEARNING OBJECTIVE: Show how to create plausible fallback content
        """
        now = datetime.now(self.timezone)
        
        # Educational: Map month to season
        if now.month in [12, 1, 2]:
            season = "winter"
        elif now.month in [3, 4, 5]:
            season = "spring"
        elif now.month in [6, 7, 8]:
            season = "summer"
        else:
            season = "autumn"
        
        # Educational: Select appropriate weather pattern
        weather_options = WEATHER_FALLBACKS.get(season, ["pleasant weather"])
        selected_weather = random.choice(weather_options)
        
        self.logger.info(f"Generated {season} weather: {selected_weather}")
        
        return {
            "today": f"{selected_weather} in Pontesbury, Shropshire",
            "source": "seasonal_pattern",
            "season": season,
            "location": "Pontesbury, Shropshire"
        }
    
    def get_headlines_context(self, max_headlines: int = 3) -> Dict[str, List[str]]:
        """
        Educational method: Get news headlines with override capability.
        
        LEARNING OBJECTIVE: Show testable external data integration
        """
        # Educational: Allow override via environment for testing
        override_headlines = os.getenv("CRAICT_HEADLINES")
        if override_headlines:
            headlines = [h.strip() for h in override_headlines.split(",") if h.strip()]
            self.logger.info(f"Using override headlines: {len(headlines)} items")
            return {"tech": headlines[:max_headlines]}
        
        # Educational: Try to fetch real headlines
        headlines = self._fetch_tech_headlines(max_headlines)
        if headlines:
            return {"tech": headlines}
        
        # Educational: Fallback to curated examples
        self.logger.info("Using fallback headlines")
        fallback_headlines = [
            "AI startup raises $100M for 'revolutionary' chatbot",
            "Tech giant announces new AI safety initiative", 
            "Developers report 40% productivity boost with AI tools"
        ]
        return {"tech": fallback_headlines[:max_headlines]}
    
    def _fetch_tech_headlines(self, max_headlines: int) -> List[str]:
        """
        Educational method: Fetch real tech headlines.
        
        LEARNING OBJECTIVE: Show web scraping with error handling
        """
        tech_sources = [
            "https://www.theregister.com/",
            "https://techcrunch.com/",
            "https://arstechnica.com/"
        ]
        
        headlines = []
        
        for url in tech_sources:
            try:
                self.logger.info(f"Fetching headlines from {url}")
                
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "CraicGPT-Educational/1.0"}
                )
                
                with urllib.request.urlopen(req, timeout=8) as response:
                    content = response.read().decode('utf-8', errors='ignore')
                
                # Educational: Extract headlines using multiple patterns
                found_headlines = self._extract_headlines_from_html(content)
                headlines.extend(found_headlines)
                
                if len(headlines) >= max_headlines:
                    break
                    
            except Exception as e:
                self.logger.warning(f"Failed to fetch headlines from {url}: {e}")
                continue
        
        return headlines[:max_headlines]
    
    def _extract_headlines_from_html(self, html_content: str) -> List[str]:
        """Educational method: Extract headlines using multiple patterns"""
        patterns = [
            re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", re.IGNORECASE | re.DOTALL),
            re.compile(r'<a[^>]*class="[^"]*headline[^"]*"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL),
            re.compile(r'<span[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</span>', re.IGNORECASE | re.DOTALL)
        ]
        
        headlines = []
        for pattern in patterns:
            matches = pattern.findall(html_content)
            for match in matches:
                # Educational: Clean extracted text
                clean_text = html.unescape(re.sub(r"<[^>]*>", " ", match)).strip()
                clean_text = re.sub(r'\s+', ' ', clean_text)  # Normalize whitespace
                
                if (len(clean_text) > 20 and 
                    len(clean_text) < 200 and 
                    clean_text not in headlines and
                    not clean_text.lower().startswith(('home', 'menu', 'search', 'login'))):
                    headlines.append(clean_text)
                    
                    if len(headlines) >= 10:
                        return headlines
        
        return headlines

    def build_comprehensive_context(self, date: Optional[str] = None) -> Dict[str, Any]:
        """
        Educational method: Build complete context for prompt generation.
        
        LEARNING OBJECTIVE: Show how to combine multiple context sources
        """
        self.logger.info("Building comprehensive context")
        
        # Educational: Gather all context components - pass date to time context
        time_context = self.get_current_time_context(date)
        weather_context = self.get_weather_context(date)
        headlines_context = self.get_headlines_context()
        
        # Educational: Combine into unified context
        combined_context = {
            # Time-based context
            "date": time_context["date"],
            "day_of_week": time_context["day_of_week"],
            "month_name": time_context["month_name"],
            "season": time_context["season"],
            "holiday": time_context["holiday"] or "",
            "formatted_date": time_context["formatted_date"],
            
            # Weather context
            "weather_today": weather_context["today"],
            "weather_source": weather_context["source"],
            "location": weather_context.get("location", "Pontesbury, Shropshire"),
            
            # News context
            "tech_headlines": headlines_context.get("tech", []),
            "headlines_summary": ", ".join(headlines_context.get("tech", [])[:3]),
            
            # Educational: Add derived context
            "seasonal_mood": self._get_seasonal_mood(time_context["season"] or ""),
            "weather_mood": self._get_weather_mood(weather_context.get("today", "")),
            
            # Static context for consistency
            "ai_trends": ["LLM capabilities", "AI safety", "compute efficiency"],
            "tech_trends": ["AI development", "cybersecurity", "cloud computing"],
            "local_events": [f"Community events in {time_context['month_name']}"]
        }
        
        self.logger.info(f"Built comprehensive context with {len(combined_context)} components")
        return combined_context
    
    def _get_seasonal_mood(self, season: str) -> str:
        """Educational helper: Convert season to mood descriptor"""
        season_moods = {
            "winter": "cozy and contemplative",
            "spring": "fresh and optimistic", 
            "summer": "bright and energetic",
            "autumn": "crisp and reflective"
        }
        season_key = season.split()[0] if season else "winter"
        return season_moods.get(season_key, "pleasant")
    
    def _get_weather_mood(self, weather_description: str) -> str:
        """Educational helper: Extract mood from weather description"""
        weather_lower = weather_description.lower() if weather_description else ""
        
        if any(word in weather_lower for word in ["sunny", "bright", "clear"]):
            return "bright and cheerful"
        elif any(word in weather_lower for word in ["cloudy", "overcast", "grey"]):
            return "contemplative and cozy"
        elif any(word in weather_lower for word in ["rain", "shower", "drizzle"]):
            return "fresh and cleansing"
        elif any(word in weather_lower for word in ["snow", "frost", "cold"]):
            return "crisp and invigorating"
        else:
            return "pleasant and mild"

    def _get_holiday_workplace_context(self, holiday: str, season: str) -> str:
        """Educational helper: Generate context for holiday-specific workplace challenges."""
        if not holiday:
            return ""

        if "christmas" in holiday.lower() or "boxing" in holiday.lower():
            return "holiday party planning and year-end deadlines creating festive workplace energy"
        elif "new year" in holiday.lower():
            return "fresh start resolutions and Q1 planning bringing renewed office motivation"
        elif "april fool" in holiday.lower():
            return "playful office atmosphere with harmless pranks and light-hearted team interactions"
        else:
            return f"special holiday considerations affecting office dynamics and team morale"

    def _get_seasonal_workplace_challenges(self, season: str) -> str:
        """Educational helper: Generate context for seasonal workplace challenges."""
        if not season:
            return ""

        season_lower = season.lower()
        if "winter" in season_lower:
            return "shorter daylight hours affecting energy levels, indoor team building focus"
        elif "spring" in season_lower:
            return "renewed energy and outdoor meeting opportunities, spring cleaning initiatives"
        elif "summer" in season_lower:
            return "vacation scheduling conflicts, flexible working arrangements for nice weather"
        elif "autumn" in season_lower:
            return "back-to-business focus after summer, preparation for year-end goals"
        else:
            return "seasonal workplace dynamics influencing team productivity and morale"

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
        
        user_prompt = template.user_prompt_template.format(**context_data)
        
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
            
            # Educational: Use comprehensive context builder
            context_data = context_builder.build_comprehensive_context(date)
            
            # Educational: Add prompt-specific context
            context_data.update({
                # Corporate theme context for new prompts
                "corporate_setting": "Modern enterprise office environment",
                "ai_improvements": "2-minute meetings, algorithmic performance reviews, drone coffee delivery",
                "corporate_satire": "satirical take on corporate jargon and office politics",
                "corporate_buzzwords": "synergy, paradigm shift, leverage, optimize, disrupt",
                "hr_automation": "AI-driven performance reviews and vacation approvals",
                "office_problems": "too many meetings, email overload, scheduling conflicts",
                "ai_solutions": "AI meeting summaries, robot clones, smart scheduling",
                "teamwork_success": "human-AI collaboration achievements in enterprise",
                "corporate_boardroom": "professional conference room with AI CEO",
                "hr_infographic": "corporate-style charts with AI HR metrics",
                
                # Enhanced seasonal and contextual elements
                "season": context_data["season"],
                "seasonal_mood": context_data["seasonal_mood"],
                "weather_mood": context_data["weather_mood"],
                "holiday": context_data["holiday"],
                "day_of_week": context_data["day_of_week"],
                "month_name": context_data["month_name"],
                "weather_today": context_data["weather_today"],
                "formatted_date": context_data["formatted_date"],
                "seasonal_elements": f"{context_data['season']} atmosphere with {context_data['weather_mood']} weather",
                
                # Holiday-specific workplace context
                "holiday_workplace_impact": context_builder._get_holiday_workplace_context(context_data["holiday"], context_data["season"]),
                "seasonal_workplace_challenges": context_builder._get_seasonal_workplace_challenges(context_data["season"]),
                
                # Legacy context mappings for backward compatibility
                "weather_context": context_data["weather_today"],
                "news_headlines": context_data["headlines_summary"],
                "cynical_perspective": "informed yet cheekily skeptical tech view",
                "relatable_character": "busy parent",
                "humorous_outcome": "unexpected AI assistance",
                "ai_personalities": "Sam Altman, Elon Musk, Geoffrey Hinton",
                "village_setting": "Pontesbury, Shropshire countryside",
                "data_visualization": "D3.js style charts and metrics",
                "advertisement_style": "retro comic-realistic advertising",
                
                # Fix key mismatch for img_01 template
                "date_formatted": context_data["formatted_date"],
                
                # Existing prompt-specific context
                "ai_figure": "Sam Altman",
                "ai_topic": "AGI timeline",
                "character_type": "busy parent",
                "problem": "planning family dinner",
                "current_role": "Technical Account Manager at Salt Security",
                "professional_background": "HashiCorp, cybersecurity, cloud architecture",
                "technical_expertise": "OpenStack, Vault, AWS, ITIL",
                "personal_interests": "motorbike, paddle-board, rpi projects",
                "family_updates": "Eddie's latest antics, Puddle's curtain climbing",
                "weather_tonight": "evening weather expected"
            })
            
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
        return [name for name, config in models.items() if config.supports_image]
    else:
        # Text templates need text-capable models  
        return [name for name, config in models.items() if config.supports_text]

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
    
    # Educational: Test context building
    context_builder = EducationalContextBuilder()
    test_date = "2025-01-15"
    
    print(f"\nTesting context building for {test_date}")
    weather = context_builder.build_comprehensive_context(test_date)
    print(f"Weather context: {weather}")
    
    print("\n=== Component Testing Complete ===")

if __name__ == "__main__":
    # Educational: Allow local testing
    test_educational_components()