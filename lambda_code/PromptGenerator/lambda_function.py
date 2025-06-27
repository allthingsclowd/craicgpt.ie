# ─────────────────────────────────────────────────────────────────────────
#  prompt_generator.py - VIBE EDITION ✨
#  -----------------------------------------------------------------------
#  DAILY PROMPT FACTORY - Now with extra vibes and context awareness
#
#  * Builds 12 prompts (4 LLM + 8 image) with optional context injection
#  * Optional fresh context from trending websites
#  * Optional 7-day historical content review for LLM prompts
#  * Maintains existing storage naming conventions
#  * Weather extraction with THREE layers (JSON → RSS → HTML)
#
#  ENVIRONMENT VARIABLES
#      PROMPT_BUCKET
#      BEDROCK_MODEL_IDS
#      BEDROCK_IMAGE_MODEL_IDS
#      ENABLE_FRESH_CONTEXT (optional, default: false)
#      ENABLE_HISTORICAL_CONTEXT (optional, default: false)
#
#  IAM NEEDED:  s3:PutObject, s3:GetObject (for historical context)
#  RUNTIME:     Python 3.12  (boto3 + std-lib only)
# ─────────────────────────────────────────────────────────────────────────
import os, re, json, html, urllib.request
from datetime import date, datetime, timedelta
import boto3
from typing import Union, Optional, Dict, List
from dataclasses import dataclass

# ──────────────────────────  VIBE CONSTANTS  ────────────────────────────
BASE_PROMPT_PREFIX = "static_assets/content/prompts"
TODAY_Y, TODAY_M, TODAY_D = date.today().strftime("%Y %m %d").split()

PROMPT_BUCKET = os.environ["PROMPT_BUCKET"]

# Model configurations with vibes ✨
LLM_MODELS = [m.strip() for m in os.getenv(
    "BEDROCK_MODEL_IDS",
    "anthropic.claude-3-sonnet-20240229-v1:0"
).split(",") if m.strip()]

IMG_MODELS = [m.strip() for m in os.getenv(
    "BEDROCK_IMAGE_MODEL_IDS",
    "stability.stable-diffusion-xl-v1"
).split(",") if m.strip()]

# Optional context features
ENABLE_FRESH_CONTEXT = os.getenv("ENABLE_FRESH_CONTEXT", "false").lower() == "true"
ENABLE_HISTORICAL_CONTEXT = os.getenv("ENABLE_HISTORICAL_CONTEXT", "false").lower() == "true"

# Vibe sources for fresh context 🌊
VIBE_SOURCES = {
    "tech_vibes": {
        "TheRegister": "https://www.theregister.com/",
        "BBCTech": "https://www.bbc.com/news/technology",
        "ArsTechnica": "https://arstechnica.com/",
        "TechCrunch": "https://techcrunch.com/"
    },
    "local_vibes": {
        "ShropshireStar": "https://www.shropshirestar.com/",
        "PontesburyParishCouncil": "https://www.pontesbury-pc.gov.uk/",
        "IrishTimes": "https://www.irishtimes.com/"
    },
    "security_vibes": {
        "AquaBlog": "https://blog.aquasec.com/",
        "SchneierOnSecurity": "https://www.schneier.com/",
        "KrebsOnSecurity": "https://krebsonsecurity.com/"
    }
}

# BBC Weather sources (Pontesbury / Shropshire → location-id 2640129)
LOC_ID   = "2640129"
WX_JSON  = f"https://weather-broker-cdn.api.bbci.co.uk/en/forecast/aggregated/{LOC_ID}"
WX_RSS   = f"https://weather-broker-cdn.api.bbci.co.uk/en/forecast/rss/3day/{LOC_ID}"
WX_HTML  = f"https://www.bbc.co.uk/weather/{LOC_ID}"

# Regex patterns for content extraction
HEAD_RE  = re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", re.S | re.I)
P_RE     = re.compile(r"<p[^>]*>(.*?)</p>", re.S | re.I)

s3 = boto3.client("s3")

# ──────────────────────────  VIBE DATA CLASSES  ──────────────────────────
@dataclass
class VibeContext:
    """Container for all the vibes we're feeling today"""
    weather: Dict[str, str]
    fresh_headlines: Dict[str, List[str]]
    historical_summary: Optional[str] = None
    trending_themes: Optional[List[str]] = None

    def __post_init__(self):
        if self.trending_themes is None:
            self.trending_themes = []

@dataclass
class PromptConfig:
    """Configuration for each prompt type"""
    prompt_id: str
    prompt_type: str  # "llm" or "image"
    content: str
    models: List[str]
    temperature: Optional[float] = None
    size: Optional[str] = None

# ──────────────────────────  VIBE HELPERS  ──────────────────────────────
def fetch(url: str, ua: str = "Mozilla/5.0 (VibeGenerator/2.0)") -> str:
    """Fetch content with good vibes"""
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode()

def scrape_vibes(sites: dict, limit: int = 15) -> List[tuple]:
    """Scrape the vibes from various sources"""
    out = []
    for src, url in sites.items():
        try:
            doc = fetch(url)
            for raw in HEAD_RE.findall(doc)[:30]:  # More headlines for better vibes
                txt = html.unescape(re.sub("<[^>]*>", " ", raw)).strip()
                if len(txt) >= 25:  # Shorter minimum for more variety
                    out.append((src, txt))
                if len(out) == limit:
                    return out
        except Exception:
            continue
    return out

def extract_trending_themes(headlines: List[tuple]) -> List[str]:
    """Extract trending themes from headlines using basic NLP vibes"""
    all_text = " ".join([h[1] for h in headlines]).lower()
    
    # Simple keyword extraction for vibes
    vibe_keywords = [
        "ai", "artificial intelligence", "machine learning", "cybersecurity", "cloud",
        "blockchain", "quantum", "startup", "funding", "acquisition", "ipo",
        "breach", "hack", "vulnerability", "patch", "update", "release",
        "conference", "summit", "meetup", "workshop", "training"
    ]
    
    themes = []
    for keyword in vibe_keywords:
        if keyword in all_text and keyword not in themes:
            themes.append(keyword)
    
    return themes[:5]  # Top 5 vibes

# ──────────────────────────  WEATHER VIBES  ──────────────────────────────
def parse_bbc_json(text: str) -> Union[tuple, None]:
    """Parse BBC weather JSON with good vibes"""
    js = json.loads(text)
    fc = js.get("forecast", {})
    
    # BBC keeps reshuffling; try several likely paths
    for path in [
        ("daily", 0, "summary"),
        ("daily", 0, "generalSummary"),
        ("daily", 0, "narrative"),
        ("text",  0, "summary"),
    ]:
        node = fc
        try:
            for p in path:
                node = node[p]
            today = str(node)
            tonight = (fc.get("daily", [{}])[0]
                         .get("detailed", [{}])[0]
                         .get("summary", "")) or today
            return today, tonight
        except Exception:
            continue
    return None

def parse_rss(text: str) -> Union[tuple, None]:
    """Parse RSS with good vibes"""
    descs = re.findall(r"<description>(.*?)</description>", text, re.S)
    if len(descs) >= 2:
        today   = html.unescape(re.sub(r"^Today:\s*",   "", descs[0]).strip())
        tonight = html.unescape(re.sub(r"^Tonight:\s*", "", descs[1]).strip())
        return today, tonight
    return None

def parse_html(text: str) -> Union[tuple, None]:
    """Parse HTML with good vibes"""
    t_block = re.search(r"<h2[^>]*>\s*Today\s*</h2>(.*?)<h2", text, re.S | re.I)
    n_block = re.search(r"<h2[^>]*>\s*Tonight\s*</h2>(.*?)<h2", text, re.S | re.I)
    if t_block and n_block:
        today_p   = P_RE.search(t_block.group(1))
        tonight_p = P_RE.search(n_block.group(1))
        if today_p and tonight_p:
            today   = html.unescape(re.sub("<[^>]*>", " ", today_p.group(1))).strip()
            tonight = html.unescape(re.sub("<[^>]*>", " ", tonight_p.group(1))).strip()
            return today, tonight
    return None

def get_weather_vibes() -> dict:
    """Get weather vibes with fallback layers"""
    # 1️⃣ JSON vibes
    try:
        res = parse_bbc_json(fetch(WX_JSON))
        if res:
            t, n = res
            return {"today": t, "tonight": n}
    except Exception:
        pass
    
    # 2️⃣ RSS vibes
    try:
        res = parse_rss(fetch(WX_RSS))
        if res:
            t, n = res
            return {"today": t, "tonight": n}
    except Exception:
        pass
    
    # 3️⃣ HTML vibes
    try:
        res = parse_html(fetch(WX_HTML))
        if res:
            t, n = res
            return {"today": t, "tonight": n}
    except Exception:
        pass
    
    # Final fallback vibes
    return {"today": "Weather vibes unavailable", "tonight": "Weather vibes unavailable"}

# ──────────────────────────  HISTORICAL VIBES  ────────────────────────────
def get_historical_context(prompt_type: str, days_back: int = 7) -> Optional[str]:
    """Get historical context from the last 7 days of content"""
    if not ENABLE_HISTORICAL_CONTEXT:
        return None
    
    try:
        # Get content from the last 7 days
        historical_content = []
        for i in range(1, days_back + 1):
            past_date = date.today() - timedelta(days=i)
            y, m, d = past_date.strftime("%Y %m %d").split()
            
            # Try to get the paper content from that date
            try:
                key = f"static_assets/content/website/{y}/{m}/{d}/paper_content.json"
                response = s3.get_object(Bucket=PROMPT_BUCKET, Key=key)
                paper_data = json.loads(response["Body"].read().decode())
                
                # Extract relevant content based on prompt type
                if prompt_type == "main-article-text":
                    slot_data = paper_data.get("contentSlots", {}).get("mainArticle", {})
                    for model_data in slot_data.get("llmOutputs", {}).values():
                        if "text" in model_data:
                            historical_content.append(model_data["text"])
                
                elif prompt_type == "comparison-article-text":
                    slot_data = paper_data.get("contentSlots", {}).get("comparisonArticle", {})
                    for model_data in slot_data.get("llmOutputs", {}).values():
                        if "text" in model_data:
                            historical_content.append(model_data["text"])
                
                elif prompt_type == "llm-story-content":
                    slot_data = paper_data.get("contentSlots", {}).get("llmStory", {})
                    for model_data in slot_data.get("llmOutputs", {}).values():
                        if "content" in model_data:
                            historical_content.append(model_data["content"])
                
                elif prompt_type == "joke-content":
                    slot_data = paper_data.get("contentSlots", {}).get("joke", {})
                    for model_data in slot_data.get("llmOutputs", {}).values():
                        if "content" in model_data:
                            historical_content.append(model_data["content"])
                
            except Exception:
                continue  # Skip dates with no content
        
        if not historical_content:
            return None
        
        # Create a summary of historical content
        combined_content = " ".join(historical_content)
        # Simple summary: take first 500 characters and add context
        summary = combined_content[:500] + "..." if len(combined_content) > 500 else combined_content
        
        return f"Historical context from the last {days_back} days:\n{summary}\n\nUse this context to maintain story continuity and avoid repetition."
    
    except Exception:
        return None

# ──────────────────────────  VIBE CONTEXT BUILDER  ────────────────────────
def build_vibe_context() -> VibeContext:
    """Build the ultimate vibe context for today"""
    weather = get_weather_vibes()
    
    fresh_headlines = {}
    if ENABLE_FRESH_CONTEXT:
        for vibe_category, sites in VIBE_SOURCES.items():
            fresh_headlines[vibe_category] = [h[1] for h in scrape_vibes(sites, limit=10)]
    
    # Extract trending themes from all headlines
    all_headlines = []
    for headlines in fresh_headlines.values():
        all_headlines.extend(headlines)
    
    trending_themes = extract_trending_themes([("", h) for h in all_headlines])
    
    return VibeContext(
        weather=weather,
        fresh_headlines=fresh_headlines,
        trending_themes=trending_themes
    )

# ──────────────────────────  VIBE PROMPT BUILDERS  ────────────────────────
def build_main_article_prompt(context: VibeContext, historical_context: Optional[str] = None) -> str:
    """Build the main article prompt with maximum vibes"""
    d = date.today().strftime("%A %d %B %Y")
    
    # Build context section
    context_sections = []
    
    # Weather vibes
    context_sections.append(f"Weather Vibes:\n  • Today: {context.weather['today']}\n  • Tonight: {context.weather['tonight']}")
    
    # Fresh context vibes
    if context.fresh_headlines:
        for category, headlines in context.fresh_headlines.items():
            if headlines:
                context_sections.append(f"{category.replace('_', ' ').title()} Vibes:\n" + "\n".join(f"  • {h}" for h in headlines[:3]))
    
    # Trending themes
    if context.trending_themes:
        context_sections.append(f"Trending Vibes: {', '.join(context.trending_themes)}")
    
    # Historical context
    if historical_context:
        context_sections.append(f"{historical_context}")
    
    context_block = "\n\n".join(context_sections)
    
    return f"""Write approximately 650 words in first-person diary form. You are Graz, 54 and a quarter, a cybersecurity engineer in Pontesbury, Shropshire, channelling the dry wit of Adrian Mole. Mention one plausible local Shropshire event.

Include family antics and clearly tag relationships:
• Lizzy - brilliant wife who funds your globe-trotting "really important IT thingys"
• Noreen (19) - "Steve Davis of kids", brilliant yet boring
• Saoirse (17) - grunge guitarist saving to visit a Parisian grave
• Terry (13) - rugby-obsessed son you "fake-coach"
• Eddie the over-mortgaged black cockapoo & Puddle the impulsively-adopted white kitten

Keep it self-deprecating, observational and silly. Reference current events and trends naturally.

{context_block}

Date: **{d}**"""

def build_comparison_article_prompt(context: VibeContext, historical_context: Optional[str] = None) -> str:
    """Build the comparison article prompt with tech vibes"""
    context_sections = []
    
    # Tech headlines context
    if context.fresh_headlines.get("tech_vibes"):
        context_sections.append("Recent Tech Vibes:\n" + "\n".join(f"  • {h}" for h in context.fresh_headlines["tech_vibes"][:5]))
    
    # Security headlines context
    if context.fresh_headlines.get("security_vibes"):
        context_sections.append("Security Vibes:\n" + "\n".join(f"  • {h}" for h in context.fresh_headlines["security_vibes"][:3]))
    
    # Historical context
    if historical_context:
        context_sections.append(f"{historical_context}")
    
    context_block = "\n\n".join(context_sections) if context_sections else ""
    
    return f"""Produce a Top-10 LLMs (mid-2025) ranked list. For each entry give: Model name & vendor (bolded), one-sentence genuine strength, one-sentence cynical "what it's really used for." 

Tone: informed yet cheekily sceptical. Present as an ordered Markdown list; about 60 words per item.

{context_block}"""

def build_llm_story_prompt(context: VibeContext, historical_context: Optional[str] = None) -> str:
    """Build the LLM story prompt with everyday vibes"""
    context_sections = []
    
    # Local headlines context
    if context.fresh_headlines.get("local_vibes"):
        context_sections.append("Local Vibes:\n" + "\n".join(f"  • {h}" for h in context.fresh_headlines["local_vibes"][:3]))
    
    # Historical context
    if historical_context:
        context_sections.append(f"{historical_context}")
    
    context_block = "\n\n".join(context_sections) if context_sections else ""
    
    return f"""Tell a light-hearted, jargon-free 400-word story about an everyday non-techie (e.g., retired postman) who uses an LLM to fix a small life problem, with an unexpectedly funny twist. 

Explain the request, the LLM's reply, and the humorous outcome. Relatable and chuckle-worthy.

{context_block}"""

def build_joke_prompt(context: VibeContext, historical_context: Optional[str] = None) -> str:
    """Build the joke prompt with AI vibes"""
    context_sections = []
    
    # Tech headlines context for AI-related jokes
    if context.fresh_headlines.get("tech_vibes"):
        ai_headlines = [h for h in context.fresh_headlines["tech_vibes"] if any(word in h.lower() for word in ["ai", "artificial intelligence", "chatgpt", "openai"])]
        if ai_headlines:
            context_sections.append("AI Vibes:\n" + "\n".join(f"  • {h}" for h in ai_headlines[:2]))
    
    # Historical context
    if historical_context:
        context_sections.append(f"{historical_context}")
    
    context_block = "\n\n".join(context_sections) if context_sections else ""
    
    return f"""Write a one-liner (40 words or less) poking fun at AI hype. Include Sam Altman by name. Clever, family-friendly, self-aware.

{context_block}"""

def build_author_bio_prompt(context: VibeContext) -> str:
    """Build the author bio prompt with professional vibes"""
    context_sections = []
    
    # Security headlines context
    if context.fresh_headlines.get("security_vibes"):
        context_sections.append("Industry Vibes:\n" + "\n".join(f"  • {h}" for h in context.fresh_headlines["security_vibes"][:2]))
    
    context_block = "\n\n".join(context_sections) if context_sections else ""
    
    return f"""In 120-150 words, craft a cheeky third-person bio for Graham Land. Omit phone, email or addresses. 

Use: Irish-born, UK-based technologist; Technical Customer Success Manager at Aqua Security (2024-), ex-Manager CSM EMEA at HashiCorp (2018-23, grew portfolio 3M to 60M); OpenStack evangelist at Fujitsu & HP; Vault-certified, AWS SA cert, ITIL; conference speaker; motorbike & paddle-board addict. 

Finish with a playful line about making DevOps "slightly less terrifying."

{context_block}"""

# ──────────────────────────  IMAGE PROMPT BUILDERS  ────────────────────────
def build_main_article_image_prompt(context: VibeContext) -> str:
    """Build the main article image prompt with visual vibes"""
    return """Comic-realistic illustration: middle-aged man labelled "Graz" at a messy desk, laptop aglow. Around him: Lizzy balancing a globe, Noreen polishing a trophy, Saoirse thrashing a guitar with Eiffel-Tower sticker, Terry tackling a rugby dummy, Eddie sprinting with a squeaky toy, Puddle dangling from curtains. Shropshire hills and a village fete banner in the window. Bright colours, playful energy."""

def build_comparison_article_image_prompt(context: VibeContext) -> str:
    """Build the comparison article image prompt with data vibes"""
    return """Vibrant d3js-style combo chart titled "LLM Capability vs. Marketing Hype (2025)". X-axis = Marketing Hype, Y-axis = Actual Capability. Ten uniquely coloured bars/points, legend with model names, dashed line for "Hype-Reality Parity". Playful infographics flavour; no numeric data needed."""

def build_llm_story_image_prompt(context: VibeContext) -> str:
    """Build the LLM story image prompt with cozy vibes"""
    return """Single-panel comic: cosy cottage lounge; cheerful elderly postman in slippers holding a tablet showing a chat bubble, while hundreds of perfectly folded origami swans overflow the room - his LLM's over-enthusiastic answer. Warm lighting, gentle humour."""

def build_joke_image_prompt(context: VibeContext) -> str:
    """Build the joke image prompt with satirical vibes"""
    return """Satirical editorial cartoon: Sam Altman riding a giant, talking paperclip shaped like Clippy, waving a banner reading "Now with 10x more tokens!" Bemused office workers watch. Clean lines, bold colours, respectful caricature."""

def build_ad_image_prompts(context: VibeContext) -> List[str]:
    """Build the advertisement image prompts with marketing vibes"""
    return [
        """Spoof billboard: "Graz's Quantum-Powered Password Post-It Notes - Because Even Hackers Deserve A Challenge." Neon 80s styling; sticky notes orbiting a glowing quantum computer; small-print disclaimer: "Side effects include remembering none of your passwords." """,
        
        """Fake cereal box: "LLM-Os - Crunchy Clusters of Context!" Cartoon tokens pouring from a GPU-shaped spoon; starburst "Free 8K sample prompt inside!" Nutrition panel lists "100% Daily Iron-y".""",
        
        """Vintage travel poster: "Visit Promptesbury-on-AI - Where Every Pub Has Its Own Model!" Soft pastel colours; villagers ordering pints from robot barmaids; sign reads "Population 1, Tokens 1B".""",
        
        """Mock perfume advert: black-and-white close-up of a sleek USB stick labelled "TOKEN No.5". Elegant model whispers "Smell the parameters." Gold serif caption: "For those who prefer their GPUs in eau de toilette." """
    ]

# ──────────────────────────  VIBE STORAGE  ────────────────────────────────
def put_json(key: str, obj: dict):
    """Store JSON with good vibes"""
    s3.put_object(
        Bucket=PROMPT_BUCKET,
        Key=key,
        Body=json.dumps(obj, indent=2, ensure_ascii=False).encode(),
        ContentType="application/json",
    )

# ──────────────────────────  MAIN VIBE HANDLER  ────────────────────────────
def lambda_handler(event, _):
    """Main vibe handler - generate all the prompts with maximum vibes"""
    today_iso = date.today().isoformat()
    prefix = f"{BASE_PROMPT_PREFIX}/{TODAY_Y}/{TODAY_M}/{TODAY_D}/"
    
    # Build the ultimate vibe context
    vibe_context = build_vibe_context()
    
    # Get historical context for LLM prompts
    historical_contexts = {}
    if ENABLE_HISTORICAL_CONTEXT:
        for prompt_type in ["main-article-text", "comparison-article-text", "llm-story-content", "joke-content"]:
            historical_contexts[prompt_type] = get_historical_context(prompt_type)
    
    # Define all the prompts with their configurations
    prompt_configs = [
        # LLM Prompts
        PromptConfig(
            prompt_id="llm_01",
            prompt_type="llm",
            content=build_main_article_prompt(vibe_context, historical_contexts.get("main-article-text")),
            models=LLM_MODELS,
            temperature=0.9
        ),
        PromptConfig(
            prompt_id="llm_02", 
            prompt_type="llm",
            content=build_comparison_article_prompt(vibe_context, historical_contexts.get("comparison-article-text")),
            models=LLM_MODELS,
            temperature=0.7
        ),
        PromptConfig(
            prompt_id="llm_03",
            prompt_type="llm", 
            content=build_llm_story_prompt(vibe_context, historical_contexts.get("llm-story-content")),
            models=LLM_MODELS,
            temperature=0.9
        ),
        PromptConfig(
            prompt_id="llm_04",
            prompt_type="llm",
            content=build_joke_prompt(vibe_context, historical_contexts.get("joke-content")),
            models=LLM_MODELS,
            temperature=0.8
        ),
        
        # Image Prompts
        PromptConfig(
            prompt_id="img_01",
            prompt_type="image",
            content=build_main_article_image_prompt(vibe_context),
            models=IMG_MODELS,
            size="1024x1024"
        ),
        PromptConfig(
            prompt_id="img_02",
            prompt_type="image", 
            content=build_comparison_article_image_prompt(vibe_context),
            models=IMG_MODELS,
            size="1024x1024"
        ),
        PromptConfig(
            prompt_id="img_07",
            prompt_type="image",
            content=build_llm_story_image_prompt(vibe_context),
            models=IMG_MODELS,
            size="1024x1024"
        ),
        PromptConfig(
            prompt_id="img_08",
            prompt_type="image",
            content=build_joke_image_prompt(vibe_context),
            models=IMG_MODELS,
            size="1024x1024"
        )
    ]
    
    # Add advertisement image prompts
    ad_prompts = build_ad_image_prompts(vibe_context)
    for i, ad_prompt in enumerate(ad_prompts, 3):
        prompt_configs.append(PromptConfig(
            prompt_id=f"img_{i:02}",
            prompt_type="image",
            content=ad_prompt,
            models=IMG_MODELS,
            size="1024x1024"
        ))
    
    # Generate and store all prompts
    for config in prompt_configs:
        prompt_data = {
            "type": config.prompt_type,
            "id": config.prompt_id,
            "date": today_iso,
            "models": config.models,
            "prompt": config.content
        }
        
        # Add optional parameters for LLM prompts
        if config.prompt_type == "llm" and config.temperature is not None:
            prompt_data["temperature"] = config.temperature
        
        # Add optional parameters for image prompts
        if config.prompt_type == "image" and config.size is not None:
            prompt_data["size"] = config.size
        
        put_json(prefix + f"{config.prompt_id}.json", prompt_data)
    
    return {
        "status": "VIBES_OK ✨",
        "saved_prompts": len(prompt_configs),
        "date": today_iso,
        "prefix": prefix,
        "vibe_features": {
            "fresh_context_enabled": ENABLE_FRESH_CONTEXT,
            "historical_context_enabled": ENABLE_HISTORICAL_CONTEXT,
            "trending_themes": vibe_context.trending_themes,
            "weather_vibes": vibe_context.weather
        }
    }
