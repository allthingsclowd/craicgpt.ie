# ╔══════════════════════════════════════════════════════════════════════╗
#  image_runner.py – CraicGPT “newspaper” image-generation pipeline
# ╟──────────────────────────────────────────────────────────────────────╢
#  PURPOSE
#  ▸ For each requested **date × img-prompt × Bedrock image model**:
#      1. Pull the prompt JSON from S3 (`prompts/YYYY-MM-DD/<img_id>.json`)
#      2. Call the model twice (512² & 1024²)
#         – automatic **exponential back-off** on *ThrottlingException*
#         – skip on *ValidationException* (blocked by model content filters)
#      3. Save raw bytes ➜ `static_assets/content/website/YYYY/MM/DD/<file>.png`
#      4. Merge results into `paper_content.json › contentSlots[*].imageOutputs`
#      5. Log rolling request count per minute  (debug capacity tracking)
#
#  IMAGE-PROMPT → NEWSPAPER SLOT MAP
#      img_01 → mainArticle        (hero)
#      img_02 → comparisonArticle  (hero)
#      img_03 → advertisements     (ad-block 1) # Corrected mapping based on code
#      img_04 → advertisements     (ad-block 2) # Corrected mapping based on code
#      img_05 → advertisements     (ad-block 3)
#      img_06 → advertisements     (ad-block 4)
#      img_07 → llmStory           (spot) # Added for new functionality
#      img_08 → joke               (spot) # Added for new functionality
#
#  MODEL SUPPORT  (GA 2025-06)
#      • amazon.titan-image-generator-v1   – text → image
#      • amazon.nova-canvas-v1:0           – text → image
#
#      ⮕ **Both** models now accept the *same* GA schema:
#         {
#           "taskType": "TEXT_IMAGE",
#           "textToImageParams": { "text": "<prompt>" },
#           "imageGenerationConfig": {
#               "numberOfImages": 1,
#               "quality":        "standard",
#               "width":           <px>,
#               "height":          <px>
#               # optional: "seed": 123
#           }
#         }
#
#  NEW (2025-06-22)
#      • safe_invoke() returns *(resp, blocked, reason)* and caps back-off at 8 s.
#      • Blocked requests are recorded in JSON as
#          { "blocked": true, "reason": "…" } (front-end can show placeholder).
#      • “payload lacks image” warning now fires **only** for genuine model bugs.
#
#  RESILIENCE
#      • safe_invoke() retries up to 6× on *ThrottlingException*.
#      • On *ValidationException* we log the server message & mark slot blocked.
#
#  RUNTIME
#      Python 3.13          • AWS Region default: eu-west-1
# ╚══════════════════════════════════════════════════════════════════════╝
import os, json, re, time, random, logging, base64
import boto3, botocore.exceptions
from botocore.config import Config
from datetime import datetime
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

def ad_alt(idx: int) -> str:          # 0-based → “Ad 1…4”
    return f"Ad {idx + 1}"

# Longer network read timeout for 1024-px generations
bedrock_cfg = Config(read_timeout=90)
s3      = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime",
                       region_name=AWS_REGION,
                       config=bedrock_cfg)

slug = lambda m: re.sub(r'[:/]', '_', m)        # safe filename helper

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

# ─── Newspaper JSON skeleton & helpers ──────────────────────────────────
def load_paper_json(y, m, d):
    key = f"{PAPER_CONTENT_DIR}/{y}/{m}/{d}/paper_content.json" # Changed filename and variable
    try:
        return key, json.loads(s3_read(key))
    except s3.exceptions.NoSuchKey:
        # If llmHandler hasn't created it yet, this is an issue.
        # However, for robustness, we could create a minimal shell, though it might hide upstream errors.
        # For now, maintaining original behavior of raising error.
        raise RuntimeError("paper_content.json must exist before image pass. Run llmHandler first.")

def save_paper_json(key, obj):
    s3_put(key, json.dumps(obj, indent=2).encode(), "application/json")

# ─── Prompt → slot mapping ──────────────────────────────────────────────
PROMPT_TO_SLOT = {
    "img_01": "mainArticle",
    "img_02": "comparisonArticle",
    "img_03": "advertisements", # Keeps ad_idx logic simple: img_03 -> ad 0
    "img_04": "advertisements", # img_04 -> ad 1
    "img_05": "advertisements", # img_05 -> ad 2
    "img_06": "advertisements", # img_06 -> ad 3
    "img_07": "llmStory",
    "img_08": "joke"
}
ALT_SLOT_TEXT.update({ # Add alt text for new slots
    "llmStory": "LLM story illustration",
    "joke": "Joke illustration"
})

# ─── REQUEST BODY builder (Titan & Nova share schema) ───────────────────
def build_body(model_id: str, prompt: str, *, size: int) -> str:
    """
    Return a JSON string for GA Bedrock image models.
    """
    return json.dumps({
        "taskType": "TEXT_IMAGE",
        "textToImageParams": {
             "text": prompt,
             "negativeText": "low quality, blurry, ugly"  # <-- ADD THIS LINE
        },
        "imageGenerationConfig": {
            "numberOfImages": 1,
            "quality":        "standard",
            "width":           size,
            "height":          size
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


# ─── Lambda entry-point ─────────────────────────────────────────────────
def lambda_handler(event, _ctx):
    """
    • For every requested date → read prompts img_01 … img_08 (now includes llmStory & joke)
    • Call each Bedrock image model at 512 px & 1024 px  
    • Persist the PNGs under static_assets/…  
    • Merge their filenames (or block flags) into paper_content.json
    """
    dates      = event.get("dates")      or [event.get("date", today_iso())]
    # Updated to include img_07 and img_08 for llmStory and joke images
    prompt_ids = event.get("prompt_ids") or [f"img_{i:02}" for i in range(1, 9)]
    model_ids  = event.get("model_ids")  or DEFAULT_MODELS

    for day in dates:
        y, m, d = day.split("-")
        paper_key, paper = load_paper_json(y, m, d)

        for pid in prompt_ids:
            slot = PROMPT_TO_SLOT.get(pid)
            if not slot:
                log.warning("Unknown img_id %s – skipped", pid)
                continue

            s3_key_for_prompt = f"{PROMPT_ROOT}/{y}/{m}/{d}/{pid}.json"
            log.info(f"Attempting to read prompt from S3 Bucket: {PROMPT_BUCKET}")
            log.info(f"Constructed S3 Key: {s3_key_for_prompt}")
            log.info(f"Key components: PROMPT_ROOT='{PROMPT_ROOT}', y='{y}', m='{m}', d='{d}', pid='{pid}'")

            prompt_json = s3_read(s3_key_for_prompt)
            prompt_txt  = json.loads(prompt_json)["prompt"]

            for model_id in model_ids:
                mdl_slug  = model_id.split(":")[0].split("/")[-1]
                px = 512 # Only generating 512px for now, can be parameterized later if needed
                tag  = f"{pid}-{px}"
                body = build_body(model_id, prompt_txt, size=px)

                resp, blocked, reason = safe_invoke(model_id, body, tag)

                # Ensure the imageOutputs dictionary exists for the slot and model slug
                slot_image_outputs = paper["contentSlots"][slot].setdefault("imageOutputs", {})

                is_ad = (slot == "advertisements")

                if is_ad:
                    # Ensure the list for ad images for this model_slug exists and has 4 slots
                    model_ad_images = slot_image_outputs.setdefault(mdl_slug, [None] * 4)
                    ad_idx = int(pid.split("_")[1]) - 3  # img_03 -> 0, ..., img_06 -> 3

                    if blocked or resp is None:
                        entry = {"blocked": True, "reason": reason[:120] if reason else ""}
                        model_ad_images[ad_idx] = entry
                        continue # Skip to next model or prompt_id

                else: # For non-ad slots like mainArticle, llmStory, joke
                    # model_specific_outputs will be the dictionary under the model_slug
                    # e.g., paper.contentSlots.mainArticle.imageOutputs["amazon-titan-image-generator-v1"]
                    model_specific_outputs = slot_image_outputs.setdefault(mdl_slug, {})

                    if blocked or resp is None:
                        model_specific_outputs[pid] = { # Store under the specific prompt_id (img_01, img_07, etc.)
                            "blocked": True,
                            "reason":  reason[:120] if reason else ""
                        }
                        continue # Skip to next model or prompt_id

                # Redundant block removed as this condition (blocked or resp is None)
                # is already handled by the logic from lines 262-279 which includes a `continue`.
                # The original syntax error was caused by the `if blocked:` within this
                # (now removed) block not having an indented executable statement after
                # its own contents were commented out.

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
                    if is_ad:
                        container[ad_idx] = entry
                    else:
                        container.update(entry)
                    continue

                b64_img = extract_base64(payload, model_id)
                if not b64_img: # 200 OK but no image
                    log.warning("❔ %s returned 200 OK with no image for %s. Full payload: %s", model_id, pid, payload)
                    # Create a "blocked" entry to signify missing image data
                    entry = {"blocked": True, "reason": "No image data in response"}
                    if is_ad:
                        model_ad_images[ad_idx] = entry
                    else:
                        model_slot_output.update(entry)
                    continue

                # ─── successful image ────────────────────────────────────
                img_bytes = base64.b64decode(b64_img)
                fname = f"{pid}_{mdl_slug}_{px}.png"
                key   = f"{PAPER_CONTENT_DIR}/{y}/{m}/{d}/{fname}" # Use new variable name
                s3_put(key, img_bytes)

                entry = (
                    {"imageUrl": fname, "imageAlt": ad_alt(ad_idx)}
                    if is_ad else
                    {"imageUrl": fname, "imageAlt": ALT_SLOT_TEXT.get(slot, "Illustration")} # Use .get for safety
                )

                if is_ad:
                    model_ad_images[ad_idx] = entry
                else:
                        # For non-ad slots, entry is stored under the specific prompt_id (pid)
                        # model_specific_outputs was already retrieved/created earlier
                        model_specific_outputs[pid] = entry


        save_paper_json(paper_key, paper)

    return {"status": "OK", "dates_processed": dates}
