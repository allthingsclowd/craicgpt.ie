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

import os, re, json, html, urllib.request, random
from datetime import date, datetime, timedelta
import boto3
from typing import Union, Optional, Dict, List, Tuple
from dataclasses import dataclass

# ═══════════════════════════════ CONFIGURATION ════════════════════════════════

# AWS Configuration
PROMPT_BUCKET = os.environ["PROMPT_BUCKET"]
BASE_PROMPT_PREFIX = "static_assets/content/prompts"
s3 = boto3.client("s3")

# Date Configuration from Environment Variables
START_DATE = os.getenv("START_DATE")  # Format: YYYY-MM-DD
END_DATE = os.getenv("END_DATE")      # Format: YYYY-MM-DD

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
        "character": "Graz, 54 and a quarter, cybersecurity engineer",
        "style": "first-person diary form, dry wit of Adrian Mole",
        "location": "Pontesbury, Shropshire",
        "family": {
            "Lizzy": "brilliant wife who funds globe-trotting 'really important IT thingys'",
            "Noreen (19)": "'Steve Davis of kids', brilliant yet boring", 
            "Saoirse (17)": "grunge guitarist saving to visit a Parisian grave",
            "Terry (13)": "rugby-obsessed son you 'fake-coach'",
            "Eddie": "over-mortgaged black cockapoo",
            "Puddle": "impulsively-adopted white kitten"
        },
        "tone": "self-deprecating, observational and silly",
        "length": "approximately 650 words",
        "requirements": "Mention one plausible local Shropshire event"
    },
    
    "comparison_article": {
        "topic": "Top-10 LLMs ranking (mid-2025)",
        "format": "ordered Markdown list, 60 words per item", 
        "content": "Model name & vendor (bolded), genuine strength, cynical 'what it's really used for'",
        "tone": "informed yet cheekily sceptical"
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
    today = date.today()
    
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
    today = date.today()
    
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
    """Build main article prompt with embedded context data"""
    date_obj = datetime.fromisoformat(daily_context.date)
    date_formatted = date_obj.strftime("%A %d %B %Y")
    day_of_week = date_obj.strftime("%A")
    
    # Base context section with embedded family details
    base_section = f"""
WRITING STYLE: {base_context['length']} in {base_context['style']}
CHARACTER: {base_context['character']} in {base_context['location']}
TONE: {base_context['tone']}
REQUIREMENT: {base_context['requirements']}
DATE: {date_formatted}

FAMILY MEMBERS CONTEXT:"""
    
    for name, desc in base_context['family'].items():
        base_section += f"\n• {name} - {desc}"
    
    # Embedded weather context with actual data
    weather_section = f"""
WEATHER CONTEXT FOR {date_formatted}:
• Today's conditions: {daily_context.weather['today']}"""
    if daily_context.weather.get('tonight'):
        weather_section += f"\n• Tonight: {daily_context.weather['tonight']}"
    if daily_context.weather.get('tomorrow'):
        weather_section += f"\n• Tomorrow: {daily_context.weather['tomorrow']}"
    weather_section += f"\n• Weather data source: {daily_context.weather.get('source', 'seasonal pattern')}"
    
    # Embedded local events with specific details
    local_section = f"""
LOCAL SHROPSHIRE CONTEXT:"""
    if daily_context.local_events:
        for i, event in enumerate(daily_context.local_events, 1):
            local_section += f"\n• Event {i}: {event}"
    else:
        local_section += "\n• No specific local events for today"
    
    # Embedded news headlines with actual content
    news_section = f"""
CURRENT NEWS HEADLINES TO REFERENCE:"""
    for category, headlines in daily_context.news_headlines.items():
        if headlines:
            news_section += f"\n{category.upper()} NEWS:"
            for i, headline in enumerate(headlines[:3], 1):
                news_section += f"\n  {i}. {headline}"
    
    # Embedded trending topics
    trends_section = ""
    if daily_context.trending_topics:
        trends_section = f"""
TRENDING TOPICS TODAY: {', '.join(daily_context.trending_topics[:5])}"""
    
    # Day-specific guidance for variation
    day_guidance = {
        "Monday": "Reference the weekend just passed, work week beginning",
        "Tuesday": "Mid-week momentum building, tech announcements common",
        "Wednesday": "Hump day observations, family midweek routines",
        "Thursday": "Looking ahead to weekend, anticipation building",
        "Friday": "End of week reflection, weekend plans forming",
        "Saturday": "Weekend family time, more relaxed pace and activities",
        "Sunday": "Sunday reflections, preparing for the week ahead"
    }.get(day_of_week, "Daily observations and routine")
    
    return f"""{base_section}

{weather_section}

{local_section}

{news_section}

{trends_section}

{day_of_week.upper()} GUIDANCE: {day_guidance}

Write your diary entry for **{date_formatted}**. Embed specific weather observations, reference at least one actual news headline naturally, include authentic family interactions, and weave in current trends. Make it feel like this specific day with these specific conditions and events."""

def build_comparison_article_prompt(base_context: Dict, daily_context: DailyContext) -> str:
    """Build comparison article prompt"""
    
    base_section = f"""
TOPIC: {base_context['topic']}
FORMAT: {base_context['format']}
CONTENT: {base_context['content']}
TONE: {base_context['tone']}"""
    
    daily_section = ""
    if daily_context.news_headlines.get('tech'):
        daily_section += "\nCURRENT TECH CONTEXT:"
        for headline in daily_context.news_headlines['tech'][:4]:
            daily_section += f"\n• {headline}"
    
    if daily_context.trending_topics:
        tech_topics = [t for t in daily_context.trending_topics if 'ai' in t or 'tech' in t or 'cyber' in t]
        if tech_topics:
            daily_section += f"\n\nTECH TRENDS: {', '.join(tech_topics)}"
    
    return f"""{base_section}

{daily_section}

Create your ranking considering current industry developments and trends."""

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

def store_prompt(prompt_data: PromptData) -> str:
    """Store prompt data to S3 with HTML placement references and enhanced context summaries"""
    date_parts = prompt_data.date.split("-")
    y, m, d = date_parts[0], date_parts[1], date_parts[2]
    
    key = f"{BASE_PROMPT_PREFIX}/{y}/{m}/{d}/{prompt_data.prompt_id}.json"
    
    # Determine content type from prompt ID
    content_type = None
    if prompt_data.prompt_id.startswith("llm_01"):
        content_type = "main_article"
    elif prompt_data.prompt_id.startswith("llm_02"):
        content_type = "comparison_article"
    elif prompt_data.prompt_id.startswith("llm_03"):
        content_type = "llm_story"
    elif prompt_data.prompt_id.startswith("llm_04"):
        content_type = "joke"
    elif prompt_data.prompt_id.startswith("img_01"):
        content_type = "main_article"
    elif prompt_data.prompt_id.startswith("img_02"):
        content_type = "comparison_article"
    elif prompt_data.prompt_id.startswith("img_07"):
        content_type = "llm_story"
    elif prompt_data.prompt_id.startswith("img_08"):
        content_type = "joke"
    elif prompt_data.prompt_id.startswith("img_03"):
        content_type = "advertisement1"
    elif prompt_data.prompt_id.startswith("img_04"):
        content_type = "advertisement2"
    elif prompt_data.prompt_id.startswith("img_05"):
        content_type = "advertisement3"
    elif prompt_data.prompt_id.startswith("img_06"):
        content_type = "advertisement4"
    
    # Get HTML placement references
    html_placement = {}
    if content_type and content_type in HTML_PLACEMENTS:
        html_placement = HTML_PLACEMENTS[content_type]
    elif content_type and content_type.startswith("advertisement"):
        # Map individual advertisement content types to HTML placements
        ad_index = int(content_type[-1]) - 1  # advertisement1->0, advertisement2->1, etc.
        if 0 <= ad_index < len(HTML_PLACEMENTS["advertisements"]):
            html_placement = {"selector": HTML_PLACEMENTS["advertisements"][ad_index]}
    
    storage_data = {
        "type": prompt_data.prompt_type,
        "id": prompt_data.prompt_id,
        "date": prompt_data.date,
        "models": prompt_data.models,
        "prompt": prompt_data.final_prompt,
        "html_placement": html_placement,
        "context_summary": {
            "weather": {
                "source": prompt_data.daily_context.weather.get('source', 'unknown'),
                "conditions": prompt_data.daily_context.weather.get('today', 'N/A'),
                "has_forecast": bool(prompt_data.daily_context.weather.get('tomorrow'))
            },
            "news": {
                "categories": list(prompt_data.daily_context.news_headlines.keys()),
                "total_headlines": sum(len(headlines) for headlines in prompt_data.daily_context.news_headlines.values()),
                "sources_scraped": len([cat for cat, headlines in prompt_data.daily_context.news_headlines.items() if headlines])
            },
            "trending_topics": {
                "count": len(prompt_data.daily_context.trending_topics),
                "topics": prompt_data.daily_context.trending_topics[:5]
            },
            "local_events": {
                "count": len(prompt_data.daily_context.local_events),
                "events": prompt_data.daily_context.local_events[:3]
            },
            "date_context": {
                "day_of_week": datetime.fromisoformat(prompt_data.date).strftime("%A"),
                "formatted_date": datetime.fromisoformat(prompt_data.date).strftime("%B %d, %Y")
            }
        }
    }
    
    # Add optional parameters
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
    
    return key

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
    
    # Determine date range from environment variables first, then event, then default
    if START_DATE and END_DATE:
        dates = generate_date_range(START_DATE, END_DATE)
        print(f"Using environment variable dates: {START_DATE} to {END_DATE}")
    elif START_DATE:
        dates = [START_DATE]
        print(f"Using environment variable single date: {START_DATE}")
    elif "start_date" in event and "end_date" in event:
        dates = generate_date_range(event["start_date"], event["end_date"])
        print(f"Using event date range: {event['start_date']} to {event['end_date']}")
    elif "date" in event:
        dates = [event["date"]]
        print(f"Using event single date: {event['date']}")
    else:
        dates = [date.today().isoformat()]
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
                
                # Store prompt
                key = store_prompt(prompt_data)
                generated_prompts.append(key)
                
                # Add to detailed tracking
                prompt_details.append({
                    "id": config["id"],
                    "type": config["type"],  
                    "date": target_date,
                    "description": config["description"],
                    "s3_key": key,
                    "prompt_length": len(final_prompt),
                    "models_count": len(models)
                })
                
                print(f"  │  Prompt length: {len(final_prompt)} characters")
                print(f"  │  Stored: {key}")
                print(f"  └─ ✓ Generated successfully")
                
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
    print(f"Total prompts generated: {len(generated_prompts)}")
    print(f"  - LLM prompts: {len(llm_prompts)}")
    print(f"  - Image prompts: {len(image_prompts)}")
    
    return {
        "status": "SUCCESS",
        "dates_processed": dates,
        "prompts_generated": len(generated_prompts),
        "prompt_breakdown": {
            "llm_prompts": len(llm_prompts),
            "image_prompts": len(image_prompts),
            "by_date": {date: len([p for p in prompt_details if p['date'] == date]) for date in dates}
        },
        "configuration": {
            "date_source": "environment_variables" if (START_DATE or END_DATE) else "event_or_default",
            "fresh_context_enabled": ENABLE_FRESH_CONTEXT,
            "historical_weather_enabled": ENABLE_HISTORICAL_WEATHER,
            "base_contexts_loaded": len(BASE_CONTEXTS),
            "news_sources_configured": len(NEWS_SOURCES),
            "html_placements_defined": len(HTML_PLACEMENTS)
        },
        "sample_outputs": prompt_details[:3] if prompt_details else [],
        "storage_keys": generated_prompts[:10]  # First 10 keys for reference
    }
