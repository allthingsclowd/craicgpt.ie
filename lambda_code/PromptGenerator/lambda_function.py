# ─────────────────────────────────────────────────────────────────────────
#  prompt_generator.py
#  -----------------------------------------------------------------------
#  DAILY PROMPT FACTORY  (multi-model -- latest weather hot-fix)
#
#  * Builds 4 LLM prompts + 6 image prompts every day.
#  * Each prompt JSON contains an **array of model IDs** (for downstream
#    batch execution by llm_runner.py / image_runner.py).
#  * Weather extraction now has THREE layers (JSON → RSS → HTML).
#  * All other behaviour (distinct headline sources, Simpsons/Warhol/Batman/
#    Leprechaun image styles, etc.) is unchanged.
#
#  ENVIRONMENT VARIABLES  (comma-separated lists allowed)
#      PROMPT_BUCKET
#      BEDROCK_MODEL_IDS
#      BEDROCK_IMAGE_MODEL_IDS
#
#  IAM NEEDED:  s3:PutObject
#  RUNTIME:     Python 3.12  (boto3 + std-lib only)
# ─────────────────────────────────────────────────────────────────────────
import os, re, json, html, urllib.request
from datetime import date
import boto3

# ──────────────────────────  ENV & CONSTANTS  ────────────────────────────
BASE_PROMPT_PREFIX = "static_assets/content/prompts"
TODAY_Y, TODAY_M, TODAY_D = date.today().strftime("%Y %m %d").split()

PROMPT_BUCKET = os.environ["PROMPT_BUCKET"]

LLM_MODELS = [m.strip() for m in os.getenv(
    "BEDROCK_MODEL_IDS",
    "anthropic.claude-3-sonnet-20240229-v1:0"
).split(",") if m.strip()]

IMG_MODELS = [m.strip() for m in os.getenv(
    "BEDROCK_IMAGE_MODEL_IDS",
    "stability.stable-diffusion-xl-v1"
).split(",") if m.strip()]

# per-prompt headline sources
DIARY_SITES   = {"PontesburyParishCouncil": "https://www.pontesbury-pc.gov.uk/",
                 "IrishTimes":              "https://www.irishtimes.com/"}
DIGEST_SITES  = {"TheRegister": "https://www.theregister.com/",
                 "BBCTech":     "https://www.bbc.com/news/technology"}
LOCAL_SITES   = {"ShropshireStar": "https://www.shropshirestar.com/"}
TECHTIP_SITES = {"AquaBlog": "https://blog.aquasec.com/"}

# BBC Weather sources (Pontesbury / Shropshire → location-id 2640129)
LOC_ID   = "2640129"
WX_JSON  = f"https://weather-broker-cdn.api.bbci.co.uk/en/forecast/aggregated/{LOC_ID}"
WX_RSS   = f"https://weather-broker-cdn.api.bbci.co.uk/en/forecast/rss/3day/{LOC_ID}"
WX_HTML  = f"https://www.bbc.co.uk/weather/{LOC_ID}"

HEAD_RE  = re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", re.S | re.I)
P_RE     = re.compile(r"<p[^>]*>(.*?)</p>", re.S | re.I)
s3       = boto3.client("s3")

# ─────────────────────────────  HELPERS  ────────────────────────────────
def fetch(url: str, ua: str = "Mozilla/5.0 (PromptGen/1.1)") -> str:
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode()

def scrape(sites: dict, limit: int = 10):
    out = []
    for src, url in sites.items():
        try:
            doc = fetch(url)
            for raw in HEAD_RE.findall(doc)[:25]:
                txt = html.unescape(re.sub("<[^>]*>", " ", raw)).strip()
                if len(txt) >= 30:
                    out.append((src, txt))
                if len(out) == limit:
                    return out
        except Exception:
            continue
    return out

# –– WEATHER (JSON → RSS → HTML) ––––––––––––––––––––––––––––––––––––––––
def parse_bbc_json(text: str) -> tuple | None:
    js = json.loads(text)
    fc = js.get("forecast", {})
    # BBC keep reshuffling; try several likely paths
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

def parse_rss(text: str) -> tuple | None:
    descs = re.findall(r"<description>(.*?)</description>", text, re.S)
    if len(descs) >= 2:
        today   = html.unescape(re.sub(r"^Today:\s*",   "", descs[0]).strip())
        tonight = html.unescape(re.sub(r"^Tonight:\s*", "", descs[1]).strip())
        return today, tonight
    return None

def parse_html(text: str) -> tuple | None:
    # Find the “Today” section
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

def get_weather() -> dict:
    # 1️⃣ JSON
    try:
        res = parse_bbc_json(fetch(WX_JSON))
        if res:
            t, n = res
            return {"today": t, "tonight": n}
    except Exception:
        pass
    # 2️⃣ RSS
    try:
        res = parse_rss(fetch(WX_RSS))
        if res:
            t, n = res
            return {"today": t, "tonight": n}
    except Exception:
        pass
    # 3️⃣ HTML scrape
    try:
        res = parse_html(fetch(WX_HTML))
        if res:
            t, n = res
            return {"today": t, "tonight": n}
    except Exception:
        pass
    # final fallback
    return {"today": "Weather unavailable", "tonight": "Weather unavailable"}

def put_json(key: str, obj: dict):
    s3.put_object(
        Bucket=PROMPT_BUCKET,
        Key=key,
        Body=json.dumps(obj, indent=2, ensure_ascii=False).encode(),
        ContentType="application/json",
    )

# ─────────────────── PROMPT BUILDERS (unchanged) ────────────────────────
def diary_prompt(hl, wx):
    d = date.today().strftime("%A %d %B %Y")
    block = "\n".join(f"- {s}: {h}" for s, h in hl)
    return (
        f"You are Graz, a 54¼-year-old cybersecurity engineer near Pontesbury.\n\n"
        f"Date: **{d}**\n"
        f"Weather:\n  • Today: {wx['today']}\n  • Tonight: {wx['tonight']}\n\n"
        "Write a single ~1,000-word Adrian-Mole-style diary entry. Rules:\n"
        " 1. Start with the date line only.\n"
        " 2. Reference yesterday in ≤2 lines.\n"
        " 3. Use ONE upbeat headline below to frame today’s story.\n"
        " 4. Quote/paraphrase both weather lines exactly once.\n"
        " 5. Mention a local Shropshire event if plausible.\n"
        " 6. Include antics from Lizzy, Noreen, Saoirse, Terry, Eddie & Puddle.\n"
        " 7. Include a ridiculous tech snafu.\n"
        " 8. Keep it funny; no politics/violence/death.\n"
        " 9. End with: _“Right. That’s enough public disclosure for one day.”_\n\n"
        "HEADLINES:\n" + block + "\n--- END RULES ---"
    )

def digest_prompt(hl):
    block = "\n".join(f"- {s}: {h}" for s, h in hl)
    return (
        "Provide a ≤150-word bulleted digest of today’s tech headlines, grouped by "
        "source, highlighting any cybersecurity angles.\n\nHEADLINES:\n" + block
    )

def local_story_prompt(hl, wx):
    block = "\n".join(f"- {s}: {h}" for s, h in hl)
    return (
        "Write a 300-word feel-good local article blending:\n"
        " • The most uplifting headline below (or invent one)\n"
        " • Today’s weather summary\n"
        " • Tonight’s farmers’ market at The Square\n\n"
        f"WEATHER:\n  • Today: {wx['today']}\n  • Tonight: {wx['tonight']}\n\n"
        "HEADLINES:\n" + block
    )

def tech_tip_prompt(hl):
    block = "\n".join(f"- {s}: {h}" for s, h in hl)
    return (
        "Draft a 250-word ‘Tech Tip of the Day’ covering:\n"
        " • Why a CNAPP beats siloed tools\n"
        " • Detecting secrets in container images\n"
        " • A Terraform least-privilege IAM guardrail snippet\n"
        "Reference a headline below if relevant.\n\nHEADLINES:\n" + block
    )


def _prompt(hl):
    block = "\n".join(f"- {s}: {h}" for s, h in hl)
    return (
        "Provide a ≤150-word bulleted digest of today’s tech headlines, grouped by "
        "source, highlighting any cybersecurity angles.\n\nHEADLINES:\n" + block
    )

def img_prompts(wx):
    return [
        "Main Article - in the vibrant, multi-panel pop-art style of the 1960s, featuring a poodle-spaniel mix dog",
        "Second Article - in the geometric 1980s pop style of an iconic female singer, featuring a curly-haired poodle mix dog",
        "Ad1 - A high-quality food advertisement for a premium grocery store, featuring a poodle-spaniel mix dog",
        "Ad2 - A colourful advertisement for a family supermarket, featuring a happy poodle-spaniel mix dog",
        "Ad3 - In the neon and pastel style of a 1980s new wave music video, featuring a poodle-spaniel mix dog",
        "Ad4 - In the style of a DIY and home improvement store ad, featuring a dog in a beautifully decorated garden",
    ]

# ─────────────────────────  MAIN HANDLER  ────────────────────────────────
def lambda_handler(event, _):
    today_iso = date.today().isoformat()
    prefix = f"{BASE_PROMPT_PREFIX}/{TODAY_Y}/{TODAY_M}/{TODAY_D}/"


    wx = get_weather()

    diary_h   = scrape(DIARY_SITES)
    digest_h  = scrape(DIGEST_SITES)
    local_h   = scrape(LOCAL_SITES)
    techtip_h = scrape(TECHTIP_SITES)

    # 4 × LLM prompts
    for pid, text, heads in [
        ("llm_01", diary_prompt(diary_h, wx), diary_h),
        ("llm_02", digest_prompt(digest_h),    digest_h),
        ("llm_03", local_story_prompt(local_h, wx), local_h),
        ("llm_04", tech_tip_prompt(techtip_h), techtip_h),
    ]:
        put_json(prefix + f"{pid}.json", {
            "type":   "llm",
            "id":     pid,
            "date":   today_iso,
            "models": LLM_MODELS,
            "prompt": text,
        })

    # 6 × image prompts
    for i, ptxt in enumerate(img_prompts(wx), 1):
        pid = f"img_{i:02}"
        put_json(prefix + f"{pid}.json", {
            "type":   "image",
            "id":     pid,
            "date":   today_iso,
            "models": IMG_MODELS,
            "prompt": ptxt,
        })

    return {
        "status": "OK",
        "saved_prompts": 10,
        "date": today_iso,
        "prefix": prefix
    }
