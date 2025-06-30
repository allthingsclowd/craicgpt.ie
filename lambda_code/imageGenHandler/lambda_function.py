# ╔══════════════════════════════════════════════════════════════════════════╗
#  image_runner.py – CraicGPT Enhanced Image Generation Pipeline
# ╟──────────────────────────────────────────────────────────────────────────╢
#  PURPOSE: Generate images for CraicGPT newspaper with date range support
#  
#  NEW FEATURES:
#    • Date range support (start_date to end_date)
#    • Improved error handling and resilience
#    • Enhanced request tracking
#    • Better logging and debugging
#    • Maintains backward compatibility
#
#  USAGE:
#    Single date: {"date": "2025-01-15"}
#    Date range:  {"start_date": "2025-01-10", "end_date": "2025-01-15"}
#    Custom prompts: {"dates": [...], "prompt_ids": [...], "model_ids": [...]}
#
#  IMAGE-PROMPT → NEWSPAPER SLOT MAP:
#      img_01 → mainArticle        (hero)
#      img_02 → comparisonArticle  (hero)
#      img_03 → advertisements     (ad-block 1)
#      img_04 → advertisements     (ad-block 2)
#      img_05 → advertisements     (ad-block 3)
#      img_06 → advertisements     (ad-block 4)
#      img_07 → llmStory           (spot)
#      img_08 → joke               (spot)
#
#  MODEL SUPPORT:
#      • amazon.titan-image-generator-v1   – text → image
#      • amazon.nova-canvas-v1:0           – text → image
#      • Both models use the same GA schema with textToImageParams
#
#  RESILIENCE:
#      • Exponential back-off on ThrottlingException (up to 6 retries)
#      • Content filter detection and graceful handling
#      • Comprehensive error logging
#      • Request count tracking per minute
#
#  PERMISSIONS:
#      s3:GetObject, s3:PutObject  – PROMPT_BUCKET
#      bedrock:InvokeModel        – each model
#
#  RUNTIME: Python 3.13   •   AWS Region default: eu-west-1
# ╚══════════════════════════════════════════════════════════════════════════╝
import os, json, re, time, random, logging, base64
import boto3, botocore.exceptions
from botocore.config import Config
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ─── Environment & AWS clients ──────────────────────────────────────────
PROMPT_BUCKET = os.environ["PROMPT_BUCKET"].strip()

PROMPT_ROOT       = "static_assets/content/prompts" # Reverted to match llmHandler's read path
PAPER_CONTENT_DIR = "static_assets/content/website" # Renamed from WEBSITE_ROOT

DEFAULT_MODELS = [
    m.strip() for m in os.getenv(
        "BEDROCK_IMAGE_MODEL_IDS",
        "amazon.titan-image-generator-v1,amazon.nova-canvas-v1:0"
    ).split(",") if m.strip()
]
AWS_REGION = os.getenv("AWS_REGION", "eu-west-1")

# ─── Alt-text helpers ───────────────────────────────────────────────
ALT_SLOT_TEXT = {
    "mainArticle":        "Main article illustration",
    "comparisonArticle":  "Comparison article illustration"
}

def ad_alt(idx: int) -> str:          # 0-based → "Ad 1…4"
    return f"Ad {idx + 1}"

# Longer network read timeout for 1024-px generations
bedrock_cfg = Config(read_timeout=90)
s3      = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime",
                       region_name=AWS_REGION,
                       config=bedrock_cfg)

slug = lambda m: re.sub(r'[:.\/]', '_', m)        # safe filename helper

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("image_runner")

# ─── Small helpers (dates, S3 I/O) ──────────────────────────────────────
today_iso = lambda: datetime.now(ZoneInfo("Europe/London")).date().isoformat()

def s3_read(key: str) -> str:
    try:
        response = s3.get_object(Bucket=PROMPT_BUCKET, Key=key)
        log.info(f"S3_READ_SUCCESS: Successfully read S3 key: '{key}' from bucket: '{PROMPT_BUCKET}'")
        return response["Body"].read().decode()
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            log.error(f"S3_READ_FAIL (NoSuchKey): Key: '{key}' not found in bucket: '{PROMPT_BUCKET}'")
        else:
            log.error(f"S3_READ_FAIL (ClientError): Error reading key '{key}' from bucket '{PROMPT_BUCKET}': {e}")
        raise # Re-raise the exception to be handled by the caller

def s3_put(key: str, data: bytes, ct="image/png"):
    s3.put_object(Bucket=PROMPT_BUCKET, Key=key, Body=data, ContentType=ct)

def s3_exists(key: str) -> bool:
    """Check if an S3 object exists"""
    try:
        s3.head_object(Bucket=PROMPT_BUCKET, Key=key)
        return True
    except s3.exceptions.NoSuchKey:
        return False
    except Exception as e:
        log.warning(f"Error checking S3 existence for {key}: {e}")
        return False

# ─── Newspaper JSON skeleton & helpers ──────────────────────────────────
def load_paper_json(y, m, d):
    key = f"{PAPER_CONTENT_DIR}/{y}/{m}/{d}/paper_content.json"
    try:
        existing_paper = json.loads(s3_read(key))
        log.info(f"📄 Found existing paper_content.json for {y}-{m}-{d}")
        return key, existing_paper, True  # True = file existed
    except s3.exceptions.NoSuchKey:
        log.info(f"📄 Creating minimal paper_content.json structure for {y}-{m}-{d}")
        # Create minimal shell for image-only processing
        paper = {
            "publicationDate": f"{y}-{m}-{d}",
            "metadata": { "bannerTitle": "The Artificially Intelligent Times",
                          "defaultLLM": "anthropic.claude-3-sonnet-20240229-v1:0",
                          "defaultImageGen": "amazon.titan-image-generator-v1" },
            "contentSlots": {
                "mainArticle": {"imageOutputs": {}}, 
                "comparisonArticle": {"imageOutputs": {}}, 
                "llmStory": {"imageOutputs": {}}, 
                "joke": {"imageOutputs": {}}, 
                "advertisement1": {"imageOutputs": {}},
                "advertisement2": {"imageOutputs": {}},
                "advertisement3": {"imageOutputs": {}},
                "advertisement4": {"imageOutputs": {}}
            }
        }
        return key, paper, False  # False = file was created new

def save_paper_json(key, obj):
    s3_put(key, json.dumps(obj, indent=2).encode(), "application/json")

# ─── Prompt → slot mapping ──────────────────────────────────────────────
PROMPT_TO_SLOT = {
    "img_01": "mainArticle",
    "img_02": "comparisonArticle",
    "img_03": "advertisement1",  # Changed from "advertisements" to individual slots
    "img_04": "advertisement2",
    "img_05": "advertisement3", 
    "img_06": "advertisement4",
    "img_07": "llmStory",
    "img_08": "joke"
}
ALT_SLOT_TEXT.update({ # Add alt text for new slots
    "llmStory": "LLM story illustration",
    "joke": "Joke illustration",
    "advertisement1": "Advertisement 1",
    "advertisement2": "Advertisement 2", 
    "advertisement3": "Advertisement 3",
    "advertisement4": "Advertisement 4"
})

# ─── Titan-specific prompt simplification ──────────────────────────────────
def simplify_prompt_for_titan(original_prompt: str, slot: str) -> str:
    """
    Create a simplified version of the prompt optimized for Titan Image Generator.
    Titan works better with shorter, more focused prompts.
    """
    
    # Base simplified prompts for each content type
    titan_base_prompts = {
        "mainArticle": "Family scene with father and children, cozy home setting",  # Restored original
        "comparisonArticle": "Simple data chart, clean infographic style", 
        "llmStory": "Cozy indoor scene, single person",
        "joke": "Simple cartoon style, editorial illustration",
        "advertisement1": "Product advertisement, clean design",
        "advertisement2": "Product advertisement, clean design", 
        "advertisement3": "Product advertisement, clean design",
        "advertisement4": "Product advertisement, clean design"
    }
    
    # Get the base prompt for this slot
    base = titan_base_prompts.get(slot, "Simple illustration")
    
    # Extract key elements from original prompt that Titan handles well
    simple_elements = []
    
    # Look for style keywords that Titan understands
    style_keywords = {
        "comic": "comic style",
        "cartoon": "cartoon style", 
        "realistic": "realistic style",
        "illustration": "illustration",
        "infographic": "infographic",
        "chart": "chart",
        "billboard": "advertisement",
        "poster": "poster"
    }
    
    for keyword, simple_style in style_keywords.items():
        if keyword in original_prompt.lower():
            simple_elements.append(simple_style)
            break  # Only take first match
    
    # Look for simple lighting/mood
    if "bright" in original_prompt.lower() or "sun" in original_prompt.lower():
        simple_elements.append("bright lighting")
    elif "cozy" in original_prompt.lower() or "warm" in original_prompt.lower():
        simple_elements.append("warm lighting")
    
    # Combine base with simple elements
    if simple_elements:
        return f"{base}, {', '.join(simple_elements[:2])}"  # Max 2 additional elements
    else:
        return base

def safe_invoke_with_fallback(model_id: str, original_prompt: str, slot: str, size: int, tag: str, 
                             max_retries: int = 6, base_delay: float = 0.25):
    """
    Enhanced safe_invoke that tries simplified prompts for Titan when original fails.
    """
    
    # First, try with original prompt using existing safe_invoke
    body = build_body(model_id, original_prompt, size=size)
    
    # Debug logging for Titan
    if model_id.startswith("amazon.titan-image"):
        log.info(f"🔍 TITAN DEBUG - Original prompt: {original_prompt}")
        log.info(f"🔍 TITAN DEBUG - Request body: {body}")
    
    resp, blocked, reason = safe_invoke(model_id, body, tag, max_retries, base_delay)
    
    # If successful, return as-is
    if resp is not None:
        return resp, blocked, reason, False  # False = didn't use fallback
    
    # For Titan models, try simplified prompt for both failures and content blocks
    if model_id.startswith("amazon.titan-image"):
        if blocked:
            log.info(f"🔄 Titan blocked by content filter, trying simplified version for {tag}")
        else:
            log.info(f"🔄 Titan failed with error, trying simplified version for {tag}")
        
        simplified_prompt = simplify_prompt_for_titan(original_prompt, slot)
        log.info(f"   Original: {original_prompt[:100]}...")
        log.info(f"   Simplified: {simplified_prompt}")
        
        # Try with simplified prompt
        simple_body = build_body(model_id, simplified_prompt, size=size)
        log.info(f"🔍 TITAN DEBUG - Simplified request body: {simple_body}")
        
        resp, blocked, reason = safe_invoke(model_id, simple_body, f"{tag}-simplified", max_retries//2, base_delay)
        
        if resp is not None:
            log.info(f"✅ Titan succeeded with simplified prompt for {tag}")
            return resp, blocked, reason, True  # True = used fallback
        else:
            log.warning(f"❌ Titan failed even with simplified prompt for {tag}: {reason}")
            return resp, blocked, reason, False
    
    # For non-Titan models or if original succeeded, return original result
    return resp, blocked, reason, False

# ─── REQUEST BODY builder (Titan & Nova share schema) ───────────────────
def build_body(model_id: str, prompt: str, *, size: int) -> str:
    """
    Return a JSON string for GA Bedrock image models.
    """
    # Enhanced negative prompts for better quality
    enhanced_negative = "low quality, blurry, ugly, distorted, watermark, text overlay, deformed"
    
    # Titan-specific optimizations
    if model_id.startswith("amazon.titan-image"):
        # Correct Titan request format to avoid false positives
        return json.dumps({
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {
                "text": prompt
            },
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "height": size,
                "width": size
            }
        })
    else:
        # Nova and other models can handle more complex configs
        return json.dumps({
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {
                 "text": prompt,
                 "negativeText": enhanced_negative
            },
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "quality": "premium",  # Nova can handle premium quality
                "width": size,
                "height": size,
                "cfgScale": 8.0
            }
        })

# ─── Bedrock invoke with exponential back-off ───────────────────────────
def safe_invoke(model_id: str, body_json: str, tag: str,
                max_retries: int = 6, base_delay: float = 0.25):
    """
    Invoke the Bedrock model with retries.

    Returns
    -------
    (resp, blocked, reason)
      resp    : botocore response object | None
      blocked : bool  – True if ValidationException (content filter)
      reason  : str | None  – server message from ValidationException
    """
    blocked_msg = None
    for attempt in range(max_retries):
        try:
            resp = bedrock.invoke_model(
                modelId=model_id,
                body=body_json,
                contentType="application/json",
                accept="application/json"
            )
            return resp, False, None
        except botocore.exceptions.ClientError as err:
            code = err.response["Error"]["Code"]
            if code == "ThrottlingException":
                wait = min(base_delay * (2 ** attempt), 8) + random.random() * 0.1
                log.warning("⏳  %s throttled (%s attempt %d) – %.2fs",
                            model_id, tag, attempt + 1, wait)
                time.sleep(wait)
                continue
            if code == "ValidationException":
                blocked_msg = err.response["Error"].get("Message", "?")
                log.warning("⚠️  %s ValidationException – %s → %s",
                            model_id, tag, blocked_msg)
                return None, True, blocked_msg
            raise
    log.error("🚫  %s throttled >%d× – skipped", model_id, max_retries)
    return None, False, None

# ─── Helper: extract base-64 PNG from Bedrock payload ───────────────────
def extract_base64(payload, model_id):
    """
    Robust extraction of base64 PNG from payload.
    Handles dict, list, or string payloads from Bedrock.
    """
    if isinstance(payload, str):
        return payload

    if isinstance(payload, list):
        # Handles direct list-of-strings response
        return payload[0] if payload else None

    if isinstance(payload, dict):
        # Handle known dict structures from Bedrock
        if "base64" in payload:
            return payload["base64"]
        for key in ["images", "artifacts"]:
            if key in payload and isinstance(payload[key], list):
                for item in payload[key]:
                    if "base64" in item:
                        return item["base64"]
                    elif isinstance(item, str):
                        return item
        # Special case: directly a list under an unknown key
        for value in payload.values():
            if isinstance(value, list) and value:
                if isinstance(value[0], str):
                    return value[0]

    # If nothing matches, return None explicitly
    log.warning(f"⚠️ Unhandled payload structure for {model_id}: {payload}")
    return None


# ═══════════════════════════════════════════════════════════════════════════
# DATE RANGE UTILITY
# ═══════════════════════════════════════════════════════════════════════════

def generate_date_range(start_date: str, end_date: str) -> list[str]:
    """Generate list of dates between start and end (inclusive)"""
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()
    
    dates = []
    current = start
    while current <= end:
        dates.append(current.isoformat())
        current += timedelta(days=1)
    
    return dates

# ─── Lambda entry-point ─────────────────────────────────────────────────
def lambda_handler(event, _ctx):
    """
    Enhanced worker handler - processes single model/date combinations
    
    Worker Mode (NEW - called by orchestrator):
    {"date": "2025-01-15", "model": "amazon.titan-image-generator-v1", "worker_mode": true}
    
    Legacy Mode (fallback for backwards compatibility):
    Single date: {"date": "2025-01-15"}
    Date range:  {"start_date": "2025-01-10", "end_date": "2025-01-15"}
    Environment variables: START_DATE, END_DATE
    """
    
    try:
        # Check for special debugging mode
        if event.get("debug"):
            import logging
            logging.getLogger().setLevel(logging.DEBUG)
            log.setLevel(logging.DEBUG)
            
        # Check for force regeneration mode
        force_regenerate = event.get("force_regenerate", False)
        
        # Environment variable fallback for dates (for production scheduling)
        if event.get("worker_mode"):
            # Worker mode - process single model/date combination for ALL image prompts
            dates = [event.get("date", today_iso())]
            model_ids = [event.get("model_id", DEFAULT_MODELS[0])]
            prompt_ids = [f"img_{i:02}" for i in range(1, 9)]  # Process ALL image prompts
            
            log.info("Worker mode: Processing ALL image prompts with %s for %s", 
                     model_ids[0], dates[0])
        else:
            # Legacy mode - handle multiple dates/models/prompts
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
            
        # Updated to include img_07 and img_08 for llmStory and joke images
        prompt_ids = event.get("prompt_ids") or [f"img_{i:02}" for i in range(1, 9)]

        start_time = time.time()
        results_summary = {"successful_dates": 0, "failed_dates": 0, "total_images": 0}

        for day in dates:
            log.info("Processing date: %s (force_regenerate=%s)", day, force_regenerate)
            y, m, d = day.split("-")
            
            try:
                paper_key, paper, file_existed = load_paper_json(y, m, d)
                
                if file_existed:
                    log.info(f"🔍 Checking existing images for incremental processing on {day}")
                else:
                    log.info(f"🆕 Full image generation required for {day}")

                for pid in prompt_ids:
                    slot = PROMPT_TO_SLOT.get(pid)
                    if not slot:
                        log.warning("Unknown img_id %s – skipped", pid)
                        continue

                    try:
                        s3_key_for_prompt = f"{PROMPT_ROOT}/{y}/{m}/{d}/{pid}.json"
                        log.debug(f"Reading prompt from S3: {s3_key_for_prompt}")

                        prompt_json = s3_read(s3_key_for_prompt)
                        prompt_txt  = json.loads(prompt_json)["prompt"]
                    except Exception as e:
                        log.error(f"Failed to load prompt {pid} for {day}: {e}")
                        continue

                    for model_id in model_ids:
                        # Use the full model ID as the key (same as LLM handler)
                        mdl_key = model_id
                        # Create a safe filename version of the model ID
                        mdl_slug = slug(model_id)  # Use the slug helper for consistent filename sanitization
                        px = 512 # Only generating 512px for now, can be parameterized later if needed
                        
                        # Ensure the imageOutputs dictionary exists for the slot and model
                        slot_image_outputs = paper["contentSlots"][slot].setdefault("imageOutputs", {})
                        model_specific_outputs = slot_image_outputs.setdefault(mdl_key, {})
                        
                        # Check if image already exists (both JSON metadata AND actual file)
                        should_skip = False
                        existing_image = model_specific_outputs.get(pid) if file_existed else None
                        
                        if file_existed and not force_regenerate:  # Skip only if not forcing regeneration
                            if (existing_image and
                                isinstance(existing_image, dict) and
                                existing_image.get("imageUrl") and
                                isinstance(existing_image.get("imageUrl"), str) and
                                len(str(existing_image.get("imageUrl", "")).strip()) > 10 and
                                not existing_image.get("blocked", False)):
                                
                                # Also check if the actual image file exists in S3
                                image_filename = existing_image["imageUrl"]
                                image_s3_key = f"{PAPER_CONTENT_DIR}/{y}/{m}/{d}/{image_filename}"
                                
                                if s3_exists(image_s3_key):
                                    log.info(f"✅ Image already exists for {model_id} {pid} on {day} ({image_filename}) - skipping")
                                    should_skip = True
                                else:
                                    log.info(f"🔄 JSON has imageUrl but file missing from S3 for {model_id} {pid} on {day} - regenerating")
                            else:
                                log.info(f"🔄 Generating missing/invalid image for {model_id} {pid} on {day}")
                        elif force_regenerate:
                            log.info(f"🔥 Force regeneration enabled - regenerating {model_id} {pid} on {day}")
                        else:
                            log.info(f"🆕 New file - generating all images for {model_id} {pid} on {day}")
                        
                        if should_skip:
                            continue
                        
                        # Clean up any existing blocked data when force regenerating
                        if force_regenerate and existing_image:
                            if existing_image.get("blocked"):
                                log.info(f"🧹 Cleaning up old blocked data for {model_id} {pid} on {day}: {existing_image.get('reason', 'No reason')}")
                                del model_specific_outputs[pid]  # Remove old blocked entry
                            else:
                                log.info(f"🧹 Cleaning up existing image data for {model_id} {pid} on {day}: {existing_image.get('imageUrl', 'No URL')}")
                                del model_specific_outputs[pid]  # Remove old successful entry for fresh generation
                        
                        tag  = f"{pid}-{px}"
                        
                        # Use enhanced fallback system for better Titan compatibility
                        resp, blocked, reason, used_fallback = safe_invoke_with_fallback(
                            model_id, prompt_txt, slot, px, tag
                        )
                        
                        # Track if we used a fallback prompt
                        if used_fallback:
                            log.info(f"📝 Used simplified fallback prompt for {model_id} on {pid}")

                        # Handle blocked/failed images uniformly for all slots
                        if blocked or resp is None:
                            model_specific_outputs[pid] = { # Store under the specific prompt_id (img_01, img_07, etc.)
                                "blocked": True,
                                "reason":  reason[:120] if reason else ""
                            }
                            continue # Skip to next model or prompt_id

                        # ─── parse Bedrock response ───────────────────────────────
                        # This part is now only reached if `resp` is not None and `blocked` is False.
                        raw = resp["body"].read()
                        try:
                            payload = json.loads(raw)
                        except json.JSONDecodeError:
                            payload = raw.decode()

                        # content-filtered after 200 OK
                        if isinstance(payload, dict) and payload.get("contentFiltered"):
                            reason = payload.get("filteredReason", "Image blocked by AWS filters")
                            entry = {"blocked": True, "reason": reason}
                            model_specific_outputs[pid] = entry
                            continue

                        b64_img = extract_base64(payload, model_id)
                        if not b64_img: # 200 OK but no image
                            log.warning("❔ %s returned 200 OK with no image for %s. Full payload: %s", model_id, pid, payload)
                            # Create a "blocked" entry to signify missing image data
                            entry = {"blocked": True, "reason": "No image data in response"}
                            model_specific_outputs[pid] = entry
                            continue

                        # ─── successful image ────────────────────────────────────
                        img_bytes = base64.b64decode(b64_img)
                        fname = f"{pid}_{mdl_slug}_{px}.png"
                        key   = f"{PAPER_CONTENT_DIR}/{y}/{m}/{d}/{fname}"
                        s3_put(key, img_bytes)

                        entry = {
                            "imageUrl": fname, 
                            "imageAlt": ALT_SLOT_TEXT.get(slot, "Illustration")
                        }

                        # All slots now use the same structure: store under specific prompt_id (pid)
                        model_specific_outputs[pid] = entry
                        results_summary["total_images"] += 1
                        log.info(f"✅ Generated image {pid} for {model_id} → {fname}")

                save_paper_json(paper_key, paper)
                results_summary["successful_dates"] += 1
                log.info("✅ Completed processing for %s", day)
                
            except Exception as e:
                log.error("❌ Failed to process date %s: %s", day, e)
                results_summary["failed_dates"] += 1
                continue

        processing_time = time.time() - start_time
        
        # Worker mode returns simple success response
        if event.get("worker_mode"):
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "status": "success",
                    "prompts_processed": results_summary["total_images"],
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
                "dates_processed": results_summary["successful_dates"],
                "dates_failed": results_summary["failed_dates"],
                "total_dates": len(dates),
                "total_images_generated": results_summary["total_images"],
                "prompt_ids": prompt_ids,
                "model_ids": model_ids,
                "configuration": {
                    "aws_region": AWS_REGION,
                    "prompt_bucket": PROMPT_BUCKET
                }
            })
        }
        
    except Exception as e:
        log.error("❌ Fatal error in image generation: %s", e)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
