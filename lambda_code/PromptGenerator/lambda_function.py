# ╔══════════════════════════════════════════════════════════════════════════╗
#  CRAICGPT PROMPT GENERATOR - Enhanced Edition
# ╟──────────────────────────────────────────────────────────────────────────╢
#  PURPOSE: Generate daily prompts with 3 clear context sources:
#    1. BASE CONTEXT: Consistent theme and purpose (easily configurable)
#    2. DAILY CONTEXT: Fresh news, events, trends for specific dates
#    3. WEATHER/LOCATION: Weather and location context for specific dates
#
#  NEW FEATURES:
#    • Date range support via environment variables
#    • Context data embedded directly into prompts
#    • HTML placement references for each prompt
#    • Enhanced context summaries
#    • Date-specific prompt variation
#
#  ENVIRONMENT VARIABLES:
#    START_DATE - Start date for generation (YYYY-MM-DD)
#    END_DATE - End date for generation (YYYY-MM-DD) 
#    PROMPT_BUCKET - S3 bucket for storage
#    BEDROCK_MODEL_IDS - LLM models (comma-separated)  
#    BEDROCK_IMAGE_MODEL_IDS - Image models (comma-separated)
#    ENABLE_FRESH_CONTEXT - Enable news scraping (default: true)
#    ENABLE_HISTORICAL_WEATHER - Enable historical weather (default: true)
# ╚══════════════════════════════════════════════════════════════════════════╝

import os, re, json, html, urllib.request, random, logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import boto3
from typing import Union, Optional, Dict, List, Tuple
from dataclasses import dataclass
try:
    from botocore.exceptions import ClientError as _BotoClientError  # type: ignore
except ImportError:  # Local linting environment may lack botocore
    class _BotoClientError(Exception):
        pass

# Set up module-level logger (used for idempotent skip messages)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("prompt_generator")

# ═══════════════════════════════ CONFIGURATION ════════════════════════════════

# AWS Configuration
PROMPT_BUCKET = os.environ["PROMPT_BUCKET"]
BASE_PROMPT_PREFIX = "static_assets/content/prompts"
s3 = boto3.client("s3")

# Date Configuration - will be read at runtime to allow event payload override
# Removed module-level environment variable reads to prevent conflicts

# Model Configuration
LLM_MODELS = [m.strip() for m in os.getenv(
    "BEDROCK_MODEL_IDS",
    "anthropic.claude-3-sonnet-20240229-v1:0"
).split(",") if m.strip()]

IMG_MODELS = [m.strip() for m in os.getenv(
    "BEDROCK_IMAGE_MODEL_IDS", 
    "amazon.titan-image-generator-v1"
).split(",") if m.strip()]

# Feature Toggles
ENABLE_FRESH_CONTEXT = os.getenv("ENABLE_FRESH_CONTEXT", "true").lower() == "true"
ENABLE_HISTORICAL_WEATHER = os.getenv("ENABLE_HISTORICAL_WEATHER", "true").lower() == "true"

# Location Configuration (Pontesbury, Shropshire)
LOCATION_ID = "2640129"
LOCATION_NAME = "Pontesbury, Shropshire"

# HTML Placement References for Frontend Integration
HTML_PLACEMENTS = {
    "main_article": {
        "title": "#main-article-title",
        "content": "#main-article-text", 
        "image": "#main-article-image"
    },
    "comparison_article": {
        "content": "#comparison-article-content",
        "image": "#comparison-article-image"
    },
    "llm_story": {
        "content": "#llm-story-content",
        "image": "#llm-story-image"
    },
    "joke": {
        "content": "#joke-content",
        "image": "#joke-image"
    },
    "author_bio": {
        "content": "#author-bio-content"
    },
    "advertisements": [
        "#advertisement-1",
        "#advertisement-2", 
        "#advertisement-3",
        "#advertisement-4"
    ]
}

# ═══════════════════════════════ CONTEXT SOURCES ═══════════════════════════════

# 1. BASE CONTEXT - Consistent themes and purposes (easily configurable)
BASE_CONTEXTS = {
    "main_article": {
        "character": "Graham, 'the Geek with the Peak,' aged 54 and a quarter - freshly-minted AI engineer who formerly moon-lighted as cybersecurity architect, cloud architect, and (in glorious, Guinness-stained dawn of time) barman",
        "style": "Adrian Mole-style diary that logs the chaos, cheeky-optimistic, Irish-flavored, peppered with dry one-liners (dad-joke meets DevSecOps stand-up)",
        "location": "Pontesbury, Shropshire",
        "family": {
            "Ester": "wife, undisputed keystone, omniscient task-master",
            "Nelly (19)": "uni-bound, dating a Peter Sutcliffe look-alike - gulp", 
            "Saoirse (17)": "guitar-shredding Shropshire Kurt Cobain",
            "Terrence (14)": "would-be Brian O'Driscoll; you coach his rugby team",
            "Eddie": "spoilt pandemic pup, worth more than the family car - at purchase, anyway",
            "Puddle": "new kitten; motive for acquisition still pending investigation"
        },
        "work_context": "trials, triumphs, and tech-jargon tantrums from today's AI & cloud trenches",
        "pub_philosophy": "The Pub: your spiritual R&D lab, essential for 'networking' and Pint-Driven Development",
        "tone": "cheeky-optimistic, Irish-flavored, lightly self-deprecating, avoid sentimentality",
        "humor_mechanics": "exaggeration, unexpected analogies, playful gripes, buzzwords (CNAPP, zero-trust, YAML-induced trauma) but translate for non-geeks",
        "irishisms": "drop a mild idiom or Gaelic phrase once per entry for flavor",
        "length": "250-400 words",
        "template_structure": {
            "headline": "catchy one-line headline you'll invent",
            "weather": "short meteorological quip for location",
            "headline_hijack": "borrow a real news headline, twist it into a segue about your life or today's tech debacle",
            "diary_dump": "Morning Mayhem (1-2 sentences), Work Wonders/Woes (2-3 sentences on AI/cloud/security antics), Family Follies (comic snapshot), Pub Post-mortem (did you make it? what excuse? philosophical revelation?)",
            "reflections": "snappy observation about middle-aged ambition (fitness, 10k dreams, weight, learning curve) and half-serious plan for tomorrow",
            "signoff": "one-liner Irish blessing, curse, or tech pun"
        },
        "requirements": "Generate as if posting raw to personal blog; minimal editing, maximum personality. Remember yesterday's cliff-hangers (Eddie's vet bill, Puddle's curtain-climbing stats, sprint deadlines). No Lists of Excuses—turn them into punchlines."
    },
    
    "comparison_article": {
        "topic": "Top-10 LLMs ranking (mid-2025)",
        "format": "JSON table structure",
        "output_requirement": "JSON string (no extra text) with exact structure specified",
        "table_structure": {
            "columns": [
                "Model name & vendor (bolded)",
                "Genuine strength", 
                "Cynical 'what it's really used for'"
            ],
            "rows_required": 10,
            "cell_requirements": "<=60 words per cell"
        },
        "content_requirements": {
            "model_format": "Bold using Markdown (e.g. **GPT-4 Turbo (OpenAI)**)",
            "genuine_strength": "1-2-sentence genuine strength, <=60 words",
            "cynical_use": "1-2-sentence cynical use, <=60 words"
        },
        "tone": "informed yet cheekily sceptical",
        "json_example": {
            "comparison_article": {
                "topic": "Top-10 LLMs ranking (mid-2025)",
                "format": "table",
                "columns": ["Model name & vendor (bolded)", "Genuine strength", "Cynical 'what it's really used for'"],
                "rows": [
                    ["**GPT-4 Turbo (OpenAI)**", "Exceptional reasoning and coding abilities", "Writing homework for students"],
                    ["**Claude 3 Sonnet (Anthropic)**", "Strong safety and helpfulness balance", "Corporate email writing assistant"],
                    ["**Gemini Pro (Google)**", "Multimodal understanding and search integration", "Making Google Search even more dominant"]
                ]
            }
        }
    },
    
    "llm_story": {
        "style": "light-hearted, jargon-free story",
        "character": "everyday non-techie (e.g., retired postman)",
        "plot": "uses LLM to fix small life problem with unexpectedly funny twist",
        "structure": "request, LLM reply, humorous outcome",
        "tone": "relatable and chuckle-worthy",
        "length": "400 words"
    },
    
    "joke": {
        "topic": "AI hype and industry",
        "format": "one-liner, 40 words or less",
        "requirements": "Include Sam Altman by name, clever, family-friendly, self-aware"
    },
    
    "author_bio": {
        "subject": "Graham Land", 
        "style": "cheeky third-person bio",
        "length": "120-150 words",
        "background": "Irish-born, UK-based technologist; Technical Customer Success Manager at Aqua Security",
        "experience": "ex-Manager CSM EMEA at HashiCorp (2018-23, grew portfolio 3M to 60M)",
        "expertise": "OpenStack evangelist, Vault-certified, AWS SA cert, ITIL, conference speaker",
        "hobbies": "motorbike & paddle-board addict",
        "ending": "playful line about making DevOps 'slightly less terrifying'"
    }
}

# Image base contexts
IMAGE_BASE_CONTEXTS = {
    "main_article": "Comic-realistic family scene with Graz and family members, Shropshire setting",
    "comparison_article": "Data visualization or infographic style, professional but playful",
    "llm_story": "Single-panel comic style, cozy domestic setting", 
    "joke": "Editorial cartoon style, AI industry satire",
    "advertisements": [
        "Spoof tech product billboard, retro styling",
        "Fake cereal box, tech/AI theme", 
        "Vintage travel poster, AI location theme",
        "Mock luxury product ad, tech twist"
    ]
}

# 2. DAILY CONTEXT SOURCES - Fresh content for specific dates
NEWS_SOURCES = {
    "tech": {
        "TheRegister": "https://www.theregister.com/",
        "BBCTech": "https://www.bbc.com/news/technology", 
        "ArsTechnica": "https://arstechnica.com/",
        "TechCrunch": "https://techcrunch.com/"
    },
    "local": {
        "ShropshireStar": "https://www.shropshirestar.com/",
        "IrishTimes": "https://www.irishtimes.com/",
        "BBCShropshire": "https://www.bbc.co.uk/news/england/shropshire"
    },
    "security": {
        "KrebsOnSecurity": "https://krebsonsecurity.com/",
        "SchneierOnSecurity": "https://www.schneier.com/",
        "BleepingComputer": "https://www.bleepingcomputer.com/"
    }
}

# 3. WEATHER/LOCATION SOURCES
WEATHER_SOURCES = {
    "current": {
        "json": f"https://weather-broker-cdn.api.bbci.co.uk/en/forecast/aggregated/{LOCATION_ID}",
        "rss": f"https://weather-broker-cdn.api.bbci.co.uk/en/forecast/rss/3day/{LOCATION_ID}",
        "html": f"https://www.bbc.co.uk/weather/{LOCATION_ID}"
    },
    "historical": "https://api.openweathermap.org/data/3.0/onecall/timemachine"  # Requires API key
}

# ═══════════════════════════════ DATA CLASSES ═══════════════════════════════

@dataclass  
class DailyContext:
    """Daily context for a specific date"""
    date: str
    weather: Dict[str, str]
    news_headlines: Dict[str, List[str]]
    trending_topics: List[str]
    local_events: List[str]
    
    def __post_init__(self):
        if not self.trending_topics:
            self.trending_topics = []
        if not self.local_events:
            self.local_events = []

@dataclass
class PromptData:
    """Complete prompt data with all context"""
    prompt_id: str
    prompt_type: str  # "llm" or "image" 
    date: str
    base_context: Dict
    daily_context: DailyContext
    final_prompt: str
    models: List[str]
    temperature: Optional[float] = None
    size: Optional[str] = None

# ═══════════════════════════════ UTILITY FUNCTIONS ═══════════════════════════

def fetch_url(url: str, timeout: int = 15) -> str:
    """Safely fetch URL content"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CraicGPT-Bot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
        return ""

def extract_headlines(html_content: str, limit: int = 10) -> List[str]:
    """Extract headlines from HTML content"""
    headline_patterns = [
        re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", re.S | re.I),
        re.compile(r'<a[^>]*class="[^"]*headline[^"]*"[^>]*>(.*?)</a>', re.S | re.I),
        re.compile(r'<span[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</span>', re.S | re.I)
    ]
    
    headlines = []
    for pattern in headline_patterns:
        matches = pattern.findall(html_content)
        for match in matches:
            clean_text = html.unescape(re.sub(r"<[^>]*>", " ", match)).strip()
            if len(clean_text) > 20 and clean_text not in headlines:
                headlines.append(clean_text)
                if len(headlines) >= limit:
                    return headlines
    
    return headlines

def generate_date_range(start_date: str, end_date: str) -> List[str]:
    """Generate list of dates between start and end (inclusive)"""
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()
    
    dates = []
    current = start
    while current <= end:
        dates.append(current.isoformat())
        current += timedelta(days=1)
    
    return dates

# ═══════════════════════════════ CONTEXT BUILDERS ═══════════════════════════

def get_weather_context(target_date: str) -> Dict[str, str]:
    """Get weather context for specific date"""
    target_dt = datetime.fromisoformat(target_date).date()
    today = datetime.now(ZoneInfo("Europe/London")).date()
    
    # For current/recent dates, use live weather
    if abs((target_dt - today).days) <= 2:
        return get_current_weather()
    
    # For historical dates, generate plausible weather
    if ENABLE_HISTORICAL_WEATHER:
        return get_historical_weather(target_date)
    
    return get_seasonal_weather(target_date)

def get_current_weather() -> Dict[str, str]:
    """Get current weather from BBC"""
    for source_type, url in WEATHER_SOURCES["current"].items():
        try:
            content = fetch_url(url)
            if source_type == "json":
                result = parse_weather_json(content)
            elif source_type == "rss":
                result = parse_weather_rss(content)
            else:  # html
                result = parse_weather_html(content)
            
            if result:
                return {"today": result[0], "tonight": result[1], "source": source_type}
        except Exception:
            continue
    
    return {"today": "Weather unavailable", "tonight": "Weather unavailable", "source": "fallback"}

def parse_weather_json(content: str) -> Optional[Tuple[str, str]]:
    """Parse BBC weather JSON"""
    try:
        data = json.loads(content)
        forecast = data.get("forecast", {})
        
        # Try different JSON paths
        for path in [("daily", 0, "summary"), ("daily", 0, "generalSummary")]:
            try:
                node = forecast
                for key in path:
                    node = node[key]
                today = str(node)
                tonight = forecast.get("daily", [{}])[0].get("detailed", [{}])[0].get("summary", today)
                return (today, tonight)
            except (KeyError, IndexError, TypeError):
                continue
    except json.JSONDecodeError:
        pass
    return None

def parse_weather_rss(content: str) -> Optional[Tuple[str, str]]:
    """Parse BBC weather RSS"""
    descriptions = re.findall(r"<description>(.*?)</description>", content, re.S)
    if len(descriptions) >= 2:
        today = html.unescape(re.sub(r"^Today:\s*", "", descriptions[0])).strip()
        tonight = html.unescape(re.sub(r"^Tonight:\s*", "", descriptions[1])).strip()
        return (today, tonight)
    return None

def parse_weather_html(content: str) -> Optional[Tuple[str, str]]:
    """Parse BBC weather HTML"""
    today_match = re.search(r"<h2[^>]*>\s*Today\s*</h2>(.*?)<h2", content, re.S | re.I)
    tonight_match = re.search(r"<h2[^>]*>\s*Tonight\s*</h2>(.*?)<h2", content, re.S | re.I)
    
    if today_match and tonight_match:
        today_p = re.search(r"<p[^>]*>(.*?)</p>", today_match.group(1), re.S)
        tonight_p = re.search(r"<p[^>]*>(.*?)</p>", tonight_match.group(1), re.S)
        
        if today_p and tonight_p:
            today = html.unescape(re.sub("<[^>]*>", " ", today_p.group(1))).strip()
            tonight = html.unescape(re.sub("<[^>]*>", " ", tonight_p.group(1))).strip()
            return (today, tonight)
    return None

def get_historical_weather(target_date: str) -> Dict[str, str]:
    """Generate plausible historical weather based on season and patterns"""
    # For now, generate seasonal weather - could be enhanced with weather history API
    return get_seasonal_weather(target_date)

def get_seasonal_weather(target_date: str) -> Dict[str, str]:
    """Generate plausible weather based on season and location"""
    dt = datetime.fromisoformat(target_date)
    month = dt.month
    
    # Shropshire seasonal patterns
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

def get_daily_news_context(target_date: str) -> Dict[str, List[str]]:
    """Get news context for specific date"""
    target_dt = datetime.fromisoformat(target_date).date()
    today = datetime.now(ZoneInfo("Europe/London")).date()
    
    # For current dates, scrape live news
    if abs((target_dt - today).days) <= 1 and ENABLE_FRESH_CONTEXT:
        return scrape_current_news()
    
    # For historical dates, generate contextual news
    return generate_historical_news_context(target_date)

def scrape_current_news() -> Dict[str, List[str]]:
    """Scrape current news from configured sources"""
    news_data = {}
    
    for category, sources in NEWS_SOURCES.items():
        headlines = []
        for source_name, url in sources.items():
            content = fetch_url(url)
            if content:
                source_headlines = extract_headlines(content, limit=5)
                headlines.extend(source_headlines)
        
        news_data[category] = headlines[:8]  # Limit per category
    
    return news_data

def generate_historical_news_context(target_date: str) -> Dict[str, List[str]]:
    """Generate plausible news context for historical dates"""
    dt = datetime.fromisoformat(target_date)
    
    # Generate contextual headlines based on date and known trends
    historical_context = {
        "tech": [
            f"AI developments continue to shape industry trends",
            f"New cybersecurity challenges emerge in {dt.year}",
            f"Cloud computing adoption accelerates across sectors"
        ],
        "local": [
            f"Shropshire community events planned for {dt.strftime('%B')}",
            f"Local businesses adapt to changing market conditions",
            f"Rural connectivity improvements announced"
        ],
        "security": [
            f"Security researchers identify new threat patterns",
            f"Best practices evolve for remote work environments",
            f"Industry collaboration strengthens cyber defenses"
        ]
    }
    
    return historical_context

def extract_trending_topics(news_data: Dict[str, List[str]]) -> List[str]:
    """Extract trending topics from news headlines"""
    all_text = " ".join([
        headline for headlines in news_data.values() 
        for headline in headlines
    ]).lower()
    
    # Enhanced keyword extraction
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
    
    return found_topics[:6]

def generate_local_events(target_date: str) -> List[str]:
    """Generate plausible local Shropshire events for the date"""
    dt = datetime.fromisoformat(target_date)
    month_name = dt.strftime("%B")
    
    # Season-appropriate local events
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

def build_daily_context(target_date: str) -> DailyContext:
    """Build complete daily context for a specific date"""
    weather = get_weather_context(target_date)
    news = get_daily_news_context(target_date)
    trending = extract_trending_topics(news)
    events = generate_local_events(target_date)
    
    return DailyContext(
        date=target_date,
        weather=weather,
        news_headlines=news,
        trending_topics=trending,
        local_events=events
    )

# ═══════════════════════════════ PROMPT BUILDERS ═══════════════════════════

def build_llm_prompt(prompt_type: str, base_context: Dict, daily_context: DailyContext) -> str:
    """Build complete LLM prompt with all context sources"""
    
    if prompt_type == "main_article":
        return build_main_article_prompt(base_context, daily_context)
    elif prompt_type == "comparison_article":
        return build_comparison_article_prompt(base_context, daily_context)
    elif prompt_type == "llm_story":
        return build_llm_story_prompt(base_context, daily_context)
    elif prompt_type == "joke":
        return build_joke_prompt(base_context, daily_context)
    elif prompt_type == "author_bio":
        return build_author_bio_prompt(base_context, daily_context)
    else:
        raise ValueError(f"Unknown prompt type: {prompt_type}")

def build_main_article_prompt(base_context: Dict, daily_context: DailyContext) -> str:
    """Build main article prompt with embedded context data using Graham's diary template"""
    date_obj = datetime.fromisoformat(daily_context.date)
    date_formatted = date_obj.strftime("%A, %d %B %Y")
    day_of_week = date_obj.strftime("%A")
    
    # System/Role Instructions
    system_section = f"""
SYSTEM / ROLE INSTRUCTIONS:

You are {base_context['character']}.

You keep a droll, self-aware, {base_context['style']}.

STYLE GUIDE:
• Length: {base_context['length']}
• Tone: {base_context['tone']}
• Humour Mechanics: {base_context['humor_mechanics']}
• Irishisms: {base_context['irishisms']}
• {base_context['requirements']}

WORK CONTEXT: {base_context['work_context']}
PUB PHILOSOPHY: {base_context['pub_philosophy']}

FAMILY MEMBERS:"""
    
    for name, desc in base_context['family'].items():
        system_section += f"\n• {name}: {desc}"
    
    # Template Structure Guide
    template_guide = f"""
DIARY TEMPLATE STRUCTURE:

🗓️ {day_of_week}, {date_obj.strftime('%d %B %Y')} - [Catchy one-line headline you'll invent]

🌦️ Weather in {base_context['location']}: [short meteorological quip]

Headline Hijack 🔥
{base_context['template_structure']['headline_hijack']}

Diary Dump 📔
• Morning Mayhem: {base_context['template_structure']['diary_dump'].split(',')[0]}
• Work Wonders (or Woes): {base_context['template_structure']['diary_dump'].split(',')[1]}
• Family Follies: {base_context['template_structure']['diary_dump'].split(',')[2]}
• Pub Post-mortem: {base_context['template_structure']['diary_dump'].split(',')[3]}

Reflections & Resolutions 💡
{base_context['template_structure']['reflections']}

Sign-off 🍀
{base_context['template_structure']['signoff']}"""
    
    # Current Context Data
    context_section = f"""
TODAY'S CONTEXT DATA:

WEATHER FOR {date_formatted}:
• Conditions: {daily_context.weather['today']}"""
    if daily_context.weather.get('tonight'):
        context_section += f"\n• Tonight: {daily_context.weather['tonight']}"
    context_section += f"\n• Source: {daily_context.weather.get('source', 'seasonal pattern')}"
    
    # News Headlines for Hijacking
    context_section += f"""

REAL NEWS HEADLINES TO HIJACK:"""
    for category, headlines in daily_context.news_headlines.items():
        if headlines:
            context_section += f"\n{category.upper()}:"
            for i, headline in enumerate(headlines[:2], 1):
                context_section += f"\n  {i}. {headline}"
    
    # Tech/Work Context
    if daily_context.trending_topics:
        tech_trends = [t for t in daily_context.trending_topics if any(keyword in t.lower() for keyword in ['ai', 'tech', 'cyber', 'cloud', 'security'])]
        if tech_trends:
            context_section += f"""

TECH TRENDS FOR WORK WOES: {', '.join(tech_trends[:4])}"""
    
    # Local Context
    if daily_context.local_events:
        context_section += f"""

SHROPSHIRE LOCAL EVENTS: {', '.join(daily_context.local_events[:2])}"""
    
    # Day-specific Diary Inspiration
    day_inspiration = {
        "Monday": "Weekend recovery, new week dread, Eddie's Monday blues, sprint planning chaos",
        "Tuesday": "Mid-week tech momentum, Terrence's rugby training night, Ester's task-master mode activated",
        "Wednesday": "Hump day observations, Saoirse's guitar practice disrupting calls, pub midweek temptation",
        "Thursday": "Weekend anticipation building, Nelly's university updates, YAML-induced trauma peak",
        "Friday": "End-of-week reflection, weekend plans, pub research finally justified",
        "Saturday": "Family time, rugby coaching duty, Eddie's weekend chaos, pub philosophy sessions",
        "Sunday": "Sunday reflections, week ahead preparation, Puddle's latest kitten shenanigans"
    }.get(day_of_week, "Daily tech chaos and family follies")
    
    context_section += f"""

{day_of_week.upper()} DIARY INSPIRATION: {day_inspiration}"""
    
    return f"""{system_section}

{template_guide}

{context_section}

NOW WRITE YOUR DIARY ENTRY for {date_formatted} following the template structure above. Embed the weather naturally, hijack one of the real headlines to segue into your tech life, include authentic family interactions with the personalities described, and make it feel like this specific {day_of_week} with these exact conditions. Remember: this goes straight to your personal blog - maximum personality, minimal editing!"""

def build_comparison_article_prompt(base_context: Dict, daily_context: DailyContext) -> str:
    """Build comparison article prompt for JSON table generation"""
    
    date_obj = datetime.fromisoformat(daily_context.date)
    date_formatted = date_obj.strftime("%B %d, %Y")
    
    # System instructions
    system_section = f"""
You are an expert tech humorist. Today is {date_formatted}.

CRITICAL INSTRUCTIONS:
• Output ONLY valid JSON - no markdown, no code blocks, no explanations
• Start with {{ and end with }}
• Follow the EXACT structure shown below

REQUIRED JSON FORMAT (copy this structure exactly):
{json.dumps(base_context['json_example'], indent=2)}

STRICT REQUIREMENTS:
• Use ONLY array format for rows: ["text1", "text2", "text3"]
• NO markdown code blocks like ``` or ```json
• NO object format like {{"Model name": "value"}}
• {base_context['content_requirements']['model_format']}
• Each cell text must be {base_context['table_structure']['cell_requirements']}
• Tone: {base_context['tone']}
• Include exactly {base_context['table_structure']['rows_required']} complete rows
• Each row must have exactly 3 string elements

CONTENT RULES:
• Column 1: {base_context['content_requirements']['model_format']}
• Column 2: {base_context['content_requirements']['genuine_strength']}
• Column 3: {base_context['content_requirements']['cynical_use']}

WARNING: Do not wrap in code blocks. Output raw JSON only."""
    
    # Current tech context for informed ranking
    context_section = ""
    if daily_context.news_headlines.get('tech'):
        context_section += "\nCURRENT TECH LANDSCAPE:"
        for headline in daily_context.news_headlines['tech'][:4]:
            context_section += f"\n• {headline}"
    
    if daily_context.trending_topics:
        ai_topics = [t for t in daily_context.trending_topics if any(keyword in t.lower() for keyword in ['ai', 'llm', 'gpt', 'claude', 'gemini', 'anthropic', 'openai'])]
        if ai_topics:
            context_section += f"\n\nAI/LLM TRENDS: {', '.join(ai_topics[:5])}"
    
    # Security context for informed cynicism
    if daily_context.news_headlines.get('security'):
        context_section += f"\n\nSECURITY CONTEXT (for cynical insights):"
        for headline in daily_context.news_headlines['security'][:2]:
            context_section += f"\n• {headline}"
    
    return f"""{system_section}

{context_section}

Generate your {base_context['topic']} JSON table considering current industry developments.

CRITICAL FINAL INSTRUCTIONS:
• Output starts with {{ and ends with }}
• NO markdown blocks or ``` wrapping
• ALL 10 rows must be complete
• Use this EXACT structure:

{{"comparison_article": {{"topic": "Top-10 LLMs ranking (mid-2025)", "format": "table", "columns": ["Model name & vendor (bolded)", "Genuine strength", "Cynical 'what it's really used for'"], "rows": [["**Model1**", "strength1", "use1"], ["**Model2**", "strength2", "use2"], ...complete all 10...]}}}}

Begin your JSON output now:"""

def build_llm_story_prompt(base_context: Dict, daily_context: DailyContext) -> str:
    """Build LLM story prompt"""
    
    base_section = f"""
STORY STYLE: {base_context['style']}
CHARACTER: {base_context['character']}
PLOT: {base_context['plot']}
STRUCTURE: {base_context['structure']}
TONE: {base_context['tone']}
LENGTH: {base_context['length']}"""
    
    daily_section = ""
    if daily_context.local_events:
        daily_section += f"\nLOCAL INSPIRATION: {daily_context.local_events[0]}"
    
    if daily_context.news_headlines.get('local'):
        daily_section += "\nLOCAL NEWS CONTEXT:"
        for headline in daily_context.news_headlines['local'][:2]:
            daily_section += f"\n• {headline}"
    
    return f"""{base_section}

{daily_section}

Write a story where your everyday character uses an LLM in an unexpected way related to their daily life."""

def build_joke_prompt(base_context: Dict, daily_context: DailyContext) -> str:
    """Build joke prompt"""
    
    base_section = f"""
TOPIC: {base_context['topic']}
FORMAT: {base_context['format']}
REQUIREMENTS: {base_context['requirements']}"""
    
    daily_section = ""
    if daily_context.trending_topics:
        ai_topics = [t for t in daily_context.trending_topics if 'ai' in t.lower()]
        if ai_topics:
            daily_section += f"\nAI TRENDS TO REFERENCE: {', '.join(ai_topics)}"
    
    if daily_context.news_headlines.get('tech'):
        ai_headlines = [h for h in daily_context.news_headlines['tech'] if 'ai' in h.lower() or 'openai' in h.lower()]
        if ai_headlines:
            daily_section += f"\nCURRENT AI NEWS: {ai_headlines[0]}"
    
    return f"""{base_section}

{daily_section}

Create a witty one-liner that references current AI developments."""

def build_author_bio_prompt(base_context: Dict, daily_context: DailyContext) -> str:
    """Build author bio prompt"""
    
    base_section = f"""
SUBJECT: {base_context['subject']}
STYLE: {base_context['style']}
LENGTH: {base_context['length']}
BACKGROUND: {base_context['background']}
EXPERIENCE: {base_context['experience']}
EXPERTISE: {base_context['expertise']}
HOBBIES: {base_context['hobbies']}
ENDING: {base_context['ending']}"""
    
    daily_section = ""
    if daily_context.news_headlines.get('security'):
        daily_section += "\nCURRENT SECURITY LANDSCAPE:"
        for headline in daily_context.news_headlines['security'][:2]:
            daily_section += f"\n• {headline}"
    
    return f"""{base_section}

{daily_section}

Write the bio incorporating current industry context where relevant."""

def build_image_prompt(prompt_type: str, base_context: str, daily_context: DailyContext) -> str:
    """Build image prompt with embedded context data and date-specific variation"""
    
    date_obj = datetime.fromisoformat(daily_context.date)
    day_of_week = date_obj.strftime("%A")
    
    # Seasonal elements based on month
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
    
    seasonal_hint = seasonal_elements.get(date_obj.month, "seasonal atmosphere")
    
    # Weather-based mood and lighting
    weather_today = daily_context.weather['today'].lower()
    if "sun" in weather_today or "clear" in weather_today:
        weather_mood = "bright natural lighting, sunny atmosphere"
    elif "cloud" in weather_today or "overcast" in weather_today:
        weather_mood = "soft diffused lighting, cloudy atmospheric mood"
    elif "rain" in weather_today or "shower" in weather_today:
        weather_mood = "cozy indoor lighting, rain-day atmosphere"
    else:
        weather_mood = "balanced natural lighting"
    
    # Day-specific elements for variety
    day_elements = {
        "Monday": "beginning-of-week energy, fresh start vibes",
        "Tuesday": "productive mid-week focus, determined mood",
        "Wednesday": "midweek balance, steady progress feeling",
        "Thursday": "anticipation building, forward momentum",
        "Friday": "end-of-week satisfaction, weekend anticipation",
        "Saturday": "relaxed weekend pace, leisure activities",
        "Sunday": "peaceful reflection, family time, preparation mood"
    }
    
    day_mood = day_elements.get(day_of_week, "daily life atmosphere")
    
    # Trending topic influences for contemporary feel
    contemporary_elements = []
    if daily_context.trending_topics:
        tech_topics = [t for t in daily_context.trending_topics if any(keyword in t.lower() for keyword in ['ai', 'tech', 'digital', 'cyber'])]
        if tech_topics:
            contemporary_elements.append("subtle modern tech elements")
    
    # Build enhanced prompt
    enhanced_prompt_parts = [
        base_context,
        f"Include {seasonal_hint}",
        f"Use {weather_mood}",
        f"Capture {day_mood}",
    ]
    
    if contemporary_elements:
        enhanced_prompt_parts.append(f"Add {', '.join(contemporary_elements)}")
    
    enhanced_prompt_parts.append(f"reflecting {date_obj.strftime('%A %B %d, %Y')} character")
    
    return ". ".join(enhanced_prompt_parts) + "."

# ═══════════════════════════════ STORAGE FUNCTIONS ═══════════════════════════

def s3_exists(key: str) -> bool:
    """Return True iff the given key already exists in the prompt bucket."""
    try:
        s3.head_object(Bucket=PROMPT_BUCKET, Key=key)
        return True
    except _BotoClientError as e:
        # botocore ClientError has .response; our dummy fallback may not
        error_code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
        if error_code in ("NoSuchKey", "404", "NotFound"):
            return False  # Not present ➜ can generate
        # For any other error, be conservative and assume it exists to avoid overwrite
        log.warning(f"⚠️ Unexpected error in s3_exists for {key}: {error_code}")
        return True

def store_prompt_if_missing(prompt_data: PromptData) -> tuple[str, bool]:
    """Write the prompt JSON only if it is not already present in S3.

    Returns (s3_key, generated) where generated is True if the file was
    created, False if it already existed and was therefore skipped.
    """
    y, m, d = prompt_data.date.split("-")
    key = f"{BASE_PROMPT_PREFIX}/{y}/{m}/{d}/{prompt_data.prompt_id}.json"

    # Short-circuit if the file already exists (idempotent behaviour)
    if s3_exists(key):
        log.info(f"⏩ Prompt already exists – skipping: {key}")
        return key, False

    # Re-use original implementation to build storage document
    storage_data = {
        "prompt_id": prompt_data.prompt_id,
        "prompt_type": prompt_data.prompt_type,
        "date": prompt_data.date,
        "prompt": prompt_data.final_prompt,
        "models": prompt_data.models,
        "context": {
            "base": prompt_data.base_context,
            "daily": {
                "weather": prompt_data.daily_context.weather,
                "news_headlines": prompt_data.daily_context.news_headlines,
                "trending_topics": prompt_data.daily_context.trending_topics,
                "local_events": prompt_data.daily_context.local_events,
                "date_context": {
                    "day_of_week": datetime.fromisoformat(prompt_data.date).strftime("%A"),
                    "formatted_date": datetime.fromisoformat(prompt_data.date).strftime("%B %d, %Y")
                }
            }
        }
    }

    if prompt_data.temperature is not None:
        storage_data["temperature"] = prompt_data.temperature
    if prompt_data.size is not None:
        storage_data["size"] = prompt_data.size

    s3.put_object(
        Bucket=PROMPT_BUCKET,
        Key=key,
        Body=json.dumps(storage_data, indent=2, ensure_ascii=False).encode(),
        ContentType="application/json"
    )

    log.info(f"✅ Prompt stored: {key}")
    return key, True

# ═══════════════════════════════ MAIN HANDLER ═══════════════════════════════

def lambda_handler(event, context):
    """
    Main handler supporting date range generation from environment variables
    
    Environment Variables:
    START_DATE: Start date for generation (YYYY-MM-DD)
    END_DATE: End date for generation (YYYY-MM-DD)
    
    Fallback to event parameters:
    Single date: {"date": "2025-01-15"}
    Date range:  {"start_date": "2025-01-10", "end_date": "2025-01-15"}
    Default:     Today's date
    """
    
    # Get date range from event payload first, fallback to environment variables, then default
    event_start = event.get("START_DATE")
    event_end = event.get("END_DATE")
    env_start = os.getenv("START_DATE")
    env_end = os.getenv("END_DATE")
    
    # Priority: event payload -> environment -> event legacy fields -> default
    if event_start and event_end:
        dates = generate_date_range(event_start, event_end)
        print(f"Using event payload dates: {event_start} to {event_end}")
    elif event_start:
        dates = [event_start]
        print(f"Using event payload single date: {event_start}")
    elif env_start and env_end:
        dates = generate_date_range(env_start, env_end)
        print(f"Using environment variable dates: {env_start} to {env_end}")
    elif env_start:
        dates = [env_start]
        print(f"Using environment variable single date: {env_start}")
    elif "start_date" in event and "end_date" in event:
        dates = generate_date_range(event["start_date"], event["end_date"])
        print(f"Using event legacy date range: {event['start_date']} to {event['end_date']}")
    elif "date" in event:
        dates = [event["date"]]
        print(f"Using event legacy single date: {event['date']}")
    else:
        dates = [datetime.now(ZoneInfo("Europe/London")).date().isoformat()]
        print(f"Using default date: {dates[0]}")
    
    print(f"Generating prompts for {len(dates)} dates: {dates[0]} to {dates[-1]}")
    
    # Define prompt configurations with clear delineation and HTML placement
    prompt_configs = [
        # ═══ LLM PROMPTS ═══
        {"id": "llm_01", "type": "llm", "content_type": "main_article", "temp": 0.9, 
         "description": "Main diary article - Graz's daily observations"},
        {"id": "llm_02", "type": "llm", "content_type": "comparison_article", "temp": 0.7,
         "description": "LLM comparison ranking - Technical analysis"}, 
        {"id": "llm_03", "type": "llm", "content_type": "llm_story", "temp": 0.9,
         "description": "LLM user story - Relatable everyday scenario"},
        {"id": "llm_04", "type": "llm", "content_type": "joke", "temp": 0.8,
         "description": "AI industry joke - Sam Altman one-liner"},
        {"id": "llm_05", "type": "llm", "content_type": "author_bio", "temp": 0.6,
         "description": "Author bio - Graham Land background"},
        
        # ═══ IMAGE PROMPTS ═══  
        {"id": "img_01", "type": "image", "content_type": "main_article", "size": "1024x1024",
         "description": "Main article illustration - Family scene"},
        {"id": "img_02", "type": "image", "content_type": "comparison_article", "size": "1024x1024",
         "description": "Comparison article graphic - Data visualization"},
        {"id": "img_03", "type": "image", "content_type": "advertisement1", "size": "1024x1024", 
         "description": "Advertisement 1 - Tech product spoof"},
        {"id": "img_04", "type": "image", "content_type": "advertisement2", "size": "1024x1024", 
         "description": "Advertisement 2 - AI cereal box"},
        {"id": "img_05", "type": "image", "content_type": "advertisement3", "size": "1024x1024", 
         "description": "Advertisement 3 - Vintage AI travel poster"},
        {"id": "img_06", "type": "image", "content_type": "advertisement4", "size": "1024x1024", 
         "description": "Advertisement 4 - Luxury tech product mockup"},
        {"id": "img_07", "type": "image", "content_type": "llm_story", "size": "1024x1024",
         "description": "LLM story illustration - Single panel comic"},
        {"id": "img_08", "type": "image", "content_type": "joke", "size": "1024x1024",
         "description": "Joke illustration - Editorial cartoon style"}
    ]
    
    generated_prompts = []
    skipped_prompts = []
    prompt_details = []
    
    # Generate prompts for each date
    for target_date in dates:
        print(f"\n{'='*60}")
        print(f"PROCESSING DATE: {target_date}")
        print(f"{'='*60}")
        
        # Build daily context for this date
        daily_context = build_daily_context(target_date)
        
        print(f"Daily Context Built:")
        print(f"  Weather: {daily_context.weather.get('today', 'N/A')} (source: {daily_context.weather.get('source', 'unknown')})")
        print(f"  News categories: {list(daily_context.news_headlines.keys())}")
        print(f"  Trending topics: {daily_context.trending_topics[:5]}")
        print(f"  Local events: {len(daily_context.local_events)}")
        
        # Generate each prompt with clear delineation
        for config in prompt_configs:
            try:
                content_type = config["content_type"]
                
                print(f"\n  ┌─ {config['description']}")
                print(f"  │  ID: {config['id']}")
                print(f"  │  Type: {config['type']}")
                print(f"  │  Content: {content_type}")
                
                if config["type"] == "llm":
                    base_context = BASE_CONTEXTS[content_type]
                    final_prompt = build_llm_prompt(content_type, base_context, daily_context)
                    models = LLM_MODELS
                    temperature = config.get("temp")
                    size = None
                    print(f"  │  Models: {len(models)} LLM models")
                    print(f"  │  Temperature: {temperature}")
                    
                else:  # image
                    if content_type.startswith("advertisement"):
                        ad_idx = int(content_type[-1]) - 1  # advertisement1->0, advertisement2->1, etc.
                        base_context = IMAGE_BASE_CONTEXTS["advertisements"][ad_idx]
                    else:
                        base_context = IMAGE_BASE_CONTEXTS[content_type]
                    
                    final_prompt = build_image_prompt(content_type, base_context, daily_context)
                    models = IMG_MODELS
                    temperature = None
                    size = config.get("size")
                    print(f"  │  Models: {len(models)} Image models")
                    print(f"  │  Size: {size}")
                
                # Create prompt data object
                prompt_data = PromptData(
                    prompt_id=config["id"],
                    prompt_type=config["type"],
                    date=target_date,
                    base_context=base_context if isinstance(base_context, dict) else {"description": base_context},
                    daily_context=daily_context,
                    final_prompt=final_prompt,
                    models=models,
                    temperature=temperature,
                    size=size
                )
                
                # Store prompt only if missing
                key, created = store_prompt_if_missing(prompt_data)

                if created:
                    generated_prompts.append(key)
                else:
                    skipped_prompts.append(key)

                # Add to detailed tracking
                prompt_details.append({
                    "id": config["id"],
                    "type": config["type"],
                    "date": target_date,
                    "description": config["description"],
                    "s3_key": key,
                    "prompt_length": len(final_prompt),
                    "models_count": len(models),
                    "status": "generated" if created else "skipped"
                })

                action_word = "Generated" if created else "Skipped (exists)"
                print(f"  │  Prompt length: {len(final_prompt)} characters")
                print(f"  │  {action_word}: {key}")
                print(f"  └─ ✓ {action_word}")
                
            except Exception as e:
                print(f"  └─ ✗ Error generating {config['id']}: {e}")
                continue
        
        print(f"\nCompleted {target_date}: {len([p for p in prompt_details if p['date'] == target_date])} prompts generated")
    
    # Summary statistics
    llm_prompts = [p for p in prompt_details if p['type'] == 'llm']
    image_prompts = [p for p in prompt_details if p['type'] == 'image']
    
    print(f"\n{'='*60}")
    print(f"GENERATION COMPLETE")
    print(f"{'='*60}")
    print(f"Total dates processed: {len(dates)}")
    print(f"Total new prompts generated: {len(generated_prompts)} (skipped {len(skipped_prompts)})")
    print(f"  - LLM prompts: {len(llm_prompts)}")
    print(f"  - Image prompts: {len(image_prompts)}")
    
    # Build response
    response_body = {
        "status": "SUCCESS",
        "dates_processed": dates,
        "prompts_generated": len(generated_prompts),
        "prompts_skipped": len(skipped_prompts),
        "prompt_breakdown": {
            "llm_prompts": len(llm_prompts),
            "image_prompts": len(image_prompts),
            "by_date": {date: len([p for p in prompt_details if p['date'] == date]) for date in dates}
        },
        "skipped_keys_sample": skipped_prompts[:10],
        "generated_keys_sample": generated_prompts[:10]
    }

    return response_body
