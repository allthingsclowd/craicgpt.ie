# ╔══════════════════════════════════════════════════════════════════════════╗
#  llm_runner.py – CraicGPT Enhanced LLM Text Generation Pipeline
# ╟──────────────────────────────────────────────────────────────────────────╢
#  PURPOSE: Generate text content for CraicGPT newspaper with date range support
#  
#  NEW FEATURES:
#    • Date range support (start_date to end_date)
#    • Improved error handling and resilience
#    • Enhanced token budget tracking
#    • Better logging and debugging
#    • Maintains backward compatibility
#
#  USAGE:
#    Single date: {"date": "2025-01-15"}
#    Date range:  {"start_date": "2025-01-10", "end_date": "2025-01-15"}
#    Custom prompts: {"dates": [...], "prompt_ids": [...], "model_ids": [...]}
#
#  PROMPT-ID → NEWSPAPER SLOT MAP:
#      llm_01 → mainArticle        {title, text}
#      llm_02 → comparisonArticle  {title, text}
#      llm_03 → llmStory           {content}
#      llm_04 → joke               {content}
#
#  MODEL SUPPORT:
#      • Anthropic Claude (chat)           • Mistral / Mixtral (chat)
#      • Amazon Titan Text                 • Cohere Command-R
#      • AI-21 Jurassic-2                  • Generic fallback
#      • Embedding models skipped by default (set ALLOW_EMBED_MODELS=true)
#
#  RESILIENCE:
#      • Exponential back-off on ThrottlingException (up to 6 retries)
#      • Fallback schema on ValidationException
#      • Comprehensive error logging
#      • Token usage tracking per minute
#
#  PERMISSIONS:
#      s3:GetObject, s3:PutObject  – PROMPT_BUCKET
#      bedrock:InvokeModel        – each model
#
#  RUNTIME: Python 3.12   •   AWS Region default: eu-west-1
# ╚══════════════════════════════════════════════════════════════════════════╝
import os, json, re, time, random, logging
import boto3, botocore.exceptions
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from typing import List, Dict, Any, Optional, Union

# ─── Environment & AWS clients ──────────────────────────────────────────
PROMPT_BUCKET = os.environ["PROMPT_BUCKET"].strip()

PROMPT_ROOT         = "static_assets/content/prompts"
PAPER_CONTENT_DIR = "static_assets/content/website" # Renamed from WEBSITE_ROOT

DEFAULT_MODELS = [
    m.strip() for m in os.getenv(
        "BEDROCK_MODEL_IDS",
        "anthropic.claude-3-sonnet-20240229-v1:0"
    ).split(",") if m.strip()
]
AWS_REGION   = os.getenv("AWS_REGION", "eu-west-1")
ALLOW_EMBED  = os.getenv("ALLOW_EMBED_MODELS", "").lower() == "true"

s3       = boto3.client("s3")
bedrock  = boto3.client("bedrock-runtime", region_name=AWS_REGION)

slug = lambda m: re.sub(r'[:.\/]', '_', m)       # safe filename helper

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("llm_runner")

# ─── Small helpers (dates, S3 I/O) ──────────────────────────────────────
today_iso   = lambda: datetime.now(ZoneInfo("Europe/London")).date().isoformat()

def s3_read(key: str) -> str:
    return s3.get_object(Bucket=PROMPT_BUCKET, Key=key)["Body"].read().decode()

def s3_put(key: str, data, ct="text/plain; charset=utf-8"):
    s3.put_object(
        Bucket=PROMPT_BUCKET, Key=key,
        Body=data.encode() if isinstance(data, str) else data,
        ContentType=ct
    )

# ─── Newspaper JSON skeleton & helpers ──────────────────────────────────
def load_paper_json(y, m, d):
    key = f"{PAPER_CONTENT_DIR}/{y}/{m}/{d}/paper_content.json"
    try:
        existing_paper = json.loads(s3_read(key))
        log.info(f"📄 Found existing paper_content.json for {y}-{m}-{d}")
        return key, existing_paper, True  # True = file existed
    except s3.exceptions.NoSuchKey:
        log.info(f"📄 Creating new paper_content.json for {y}-{m}-{d}")
        paper = {
            "publicationDate": f"{y}-{m}-{d}",
            "metadata": { "bannerTitle": "The Artificially Intelligent Times",
                          "defaultLLM": "anthropic.claude-3-sonnet-20240229-v1:0",
                          "defaultImageGen": "amazon.titan-image-generator-v1" },
            "contentSlots": {
                "mainArticle":       { "llmOutputs": {}, "imageOutputs": {} },
                "authorBio":         { "llmOutputs": {}, "imageOutputs": {} },
                "comparisonArticle": { "llmOutputs": {}, "imageOutputs": {} },
                "llmStory":          { "llmOutputs": {}, "imageOutputs": {} },
                "joke":              { "llmOutputs": {}, "imageOutputs": {} },
                "advertisement1":    { "imageOutputs": {} },
                "advertisement2":    { "imageOutputs": {} },
                "advertisement3":    { "imageOutputs": {} },
                "advertisement4":    { "imageOutputs": {} }
            }
        }
        return key, paper, False  # False = file was created new

def save_paper_json(key, obj):
    s3_put(key, json.dumps(obj, indent=2), "application/json")

# ─── Prompt → slot mapping ──────────────────────────────────────────────
PROMPT_TO_SLOT = {
    "llm_01": ("mainArticle",        "title_text"),
    "llm_02": ("comparisonArticle",  "title_text"),
    "llm_03": ("llmStory",           "content"),
    "llm_04": ("joke",               "content"),
    "llm_05": ("authorBio",          "content")
}

# ─── Request body builder – family-aware schemas ────────────────────────
def build_body(model_id: str, prompt: str, *, chat: bool) -> str:
    if chat:
        if model_id.startswith("anthropic."):
            return json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "system": prompt,
                "messages": [{ "role": "user", "content": "Generate." }],
                "max_tokens": 800, "temperature": 0.7, "top_p": 0.9
            })
        if model_id.startswith("mistral."):
            return json.dumps({
                "messages": [
                    { "role": "system", "content": prompt },
                    { "role": "user",   "content": "Generate." }
                ],
                "max_tokens": 800, "temperature": 0.7, "top_p": 0.9
            })
    if model_id.startswith("amazon.titan-text"):
        return json.dumps({
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": 512,
                "temperature": 0.7,
                "topP": 0.9,
                "stopSequences": []
            }
        })
    if model_id.startswith("cohere."):
        return json.dumps({ "prompt": prompt, "max_tokens": 800 })
    if model_id.startswith("ai21."):
        return json.dumps({ "prompt": prompt, "maxTokens": 800 })
    return json.dumps({ "prompt": prompt })  # generic fallback

# ─── Extract generated text from diverse payloads ───────────────────────
def extract_text(model_id: str, payload: dict) -> str:
    if "content"  in payload: return payload["content"][0]["text"].strip()
    if "message"  in payload: return payload["message"]["content"].strip()
    if "messages" in payload: return payload["messages"][0]["content"].strip()

    if "results" in payload:                 # Cohere / misc OSS wrappers
        r0 = payload["results"][0]
        return (r0.get("text") or r0.get("generation") or
                r0.get("outputText") or r0.get("output") or
                json.dumps(r0)).strip()

    if "outputs"      in payload: return payload["outputs"][0]["text"].strip()
    if "generations"  in payload: return payload["generations"][0]["text"].strip()
    raise RuntimeError(f"Unknown response schema for {model_id}")

# ─── Bedrock invoke with exponential back-off ───────────────────────────
def safe_invoke(model_id: str, body_json: str, tag: str,
                max_retries: int = 6, base_delay: float = 0.25):
    for attempt in range(max_retries):
        try:
            return bedrock.invoke_model(
                modelId=model_id,
                body=body_json,
                contentType="application/json",
                accept="application/json"
            )
        except botocore.exceptions.ClientError as err:
            if err.response["Error"]["Code"] == "ThrottlingException":
                wait = base_delay * (2 ** attempt) + random.random() * 0.1
                log.warning("⏳  %s throttled (%s attempt %d) – sleep %.2fs",
                            model_id, tag, attempt+1, wait)
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"Throttled >{max_retries}× for model {model_id}")

# ═══════════════════════════════════════════════════════════════════════════
# DATE RANGE UTILITY
# ═══════════════════════════════════════════════════════════════════════════

def generate_date_range(start_date: str, end_date: str) -> list[str]:
    """Generate list of dates between start and end (inclusive)"""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    
    dates = []
    current = start
    while current <= end:
        dates.append(current.isoformat())
        current += timedelta(days=1)
    
    return dates

# ─── Lambda entrypoint ──────────────────────────────────────────────────
def lambda_handler(event, _ctx):
    """
    Enhanced worker handler - processes single model/date combinations
    
    Worker Mode (NEW - called by orchestrator):
    {"date": "2025-01-15", "model": "claude-3-sonnet", "worker_mode": true}
    
    Legacy Mode (fallback for backwards compatibility):
    Single date: {"date": "2025-01-15"}
    Date range:  {"start_date": "2025-01-10", "end_date": "2025-01-15"}
    Environment variables: START_DATE, END_DATE
    """
    
    try:
        # Check if this is single model worker mode (called by orchestrator)
        if event.get("worker_mode") and "model" in event and "date" in event:
            log.info("Running in WORKER MODE for single model/date combination")
            dates = [event["date"]]
            model_ids = [event["model"]]
            log.info("Processing: %s on %s", event["model"], event["date"])
        else:
            log.info("Running in LEGACY MODE with date range processing")
            
            # Get environment variables for date range
            START_DATE = os.getenv("START_DATE")
            END_DATE = os.getenv("END_DATE")
            
            # Determine date range from environment variables first, then event, then default
            if START_DATE and END_DATE:
                dates = generate_date_range(START_DATE, END_DATE)
                log.info("Using environment variable dates: %s to %s (%d dates)", 
                         START_DATE, END_DATE, len(dates))
            elif START_DATE:
                dates = [START_DATE]
                log.info("Using environment variable single date: %s", START_DATE)
            elif "start_date" in event and "end_date" in event:
                dates = generate_date_range(event["start_date"], event["end_date"])
                log.info("Processing event date range: %s to %s (%d dates)", 
                         event["start_date"], event["end_date"], len(dates))
            elif "dates" in event:
                dates = event["dates"]
                log.info("Processing custom event date list: %d dates", len(dates))
            elif "date" in event:
                dates = [event["date"]]
                log.info("Processing single event date: %s", event["date"])
            else:
                dates = [today_iso()]
                log.info("Processing default date (today): %s", dates[0])
            
            model_ids = event.get("model_ids") or DEFAULT_MODELS
        
        prompt_ids = event.get("prompt_ids") or [f"llm_{i:02}" for i in range(1,6)]

        if not ALLOW_EMBED:
            embed_skip = [m for m in model_ids if "embed" in m.lower()]
            model_ids  = [m for m in model_ids if m not in embed_skip]
            if embed_skip:
                log.info("Skipping embedding models: %s", ", ".join(embed_skip))
        if not model_ids:
            raise ValueError("No generative models to run")

        result_map = {}
        start_time = time.time()

        # ── rolling token-budget globals ────────────────────────────────────
        global _tok_total, _tok_start
        _tok_total, _tok_start = 0, time.time()

        # Process each date
        for day in dates:
            log.info("Processing date: %s", day)
            y, m, d = day.split("-")
            
            try:
                paper_key, paper, file_existed = load_paper_json(y, m, d)
                result_map[day] = {}
                
                if file_existed:
                    log.info(f"🔍 Checking existing content for incremental processing on {day}")
                else:
                    log.info(f"🆕 Full content generation required for {day}")

                for pid in prompt_ids:
                    slot, ftype = PROMPT_TO_SLOT.get(pid, (None, None))
                    if slot is None:
                        log.warning("Unknown prompt_id %s – skipped", pid)
                        continue

                    try:
                        prompt_txt = json.loads(
                            s3_read(f"{PROMPT_ROOT}/{y}/{m}/{d}/{pid}.json"))["prompt"]
                    except Exception as e:
                        log.error("Failed to load prompt %s for %s: %s", pid, day, e)
                        continue

                    result_map[day][pid] = {}

                    for model_id in model_ids:
                        try:
                            # Check if content already exists for this model (only if file existed)
                            if file_existed:
                                mdl_key = model_id
                                slot_dict = paper["contentSlots"][slot].get("llmOutputs", {})
                                existing_content = slot_dict.get(mdl_key, {})
                                
                                # Check if meaningful content exists
                                has_content = False
                                if ftype == "title_text":
                                    has_content = (existing_content.get("title") and 
                                                 existing_content.get("text") and
                                                 len(existing_content.get("title", "").strip()) > 5 and
                                                 len(existing_content.get("text", "").strip()) > 20)
                                else:  # content type
                                    has_content = (existing_content.get("content") and
                                                 len(existing_content.get("content", "").strip()) > 20)
                                
                                if has_content:
                                    log.info(f"✅ Content already exists for {model_id} on {pid} for {day} - skipping")
                                    result_map[day][pid][model_id] = "SKIPPED: Content already exists"
                                    continue
                                else:
                                    log.info(f"🔄 Generating missing content for {model_id} on {pid} for {day}")
                            else:
                                log.info(f"🆕 New file - generating all content for {model_id} on {pid} for {day}")
                            
                            chat_cap  = model_id.startswith(("anthropic.", "mistral."))
                            body_prim = build_body(model_id, prompt_txt, chat=chat_cap)
                            body_fbk  = build_body(model_id, prompt_txt, chat=False)

                            try:
                                resp = safe_invoke(model_id, body_prim,  f"{pid}-primary")
                            except botocore.exceptions.ClientError as ve:
                                if ve.response["Error"]["Code"] != "ValidationException":
                                    raise
                                log.warning("⚠️  %s ValidationException – retry fallback", model_id)
                                resp = safe_invoke(model_id, body_fbk, f"{pid}-fallback")

                            payload = json.loads(resp["body"].read())
                            text    = extract_text(model_id, payload)

                            # ── rolling token-budget logging ───────────────────
                            usage = payload.get("usage") or payload.get("usage_metadata") or {}
                            out_tok = (usage.get("output_tokens") or
                                       usage.get("generated_tokens") or 0)
                            _tok_total += out_tok
                            if time.time() - _tok_start >= 60:
                                log.info("📊  Output-tokens last 60 s: %d", _tok_total)
                                _tok_total, _tok_start = 0, time.time()

                            raw_key = f"results/{day}/{pid}/{slug(model_id)}.txt"
                            s3_put(raw_key, text)

                            # Use the full model ID as the key (same as image handler)
                            mdl_key = model_id
                            
                            # Store content in model-specific llmOutputs (all slots treated equally)
                            slot_dict = paper["contentSlots"][slot]["llmOutputs"]
                            if ftype == "title_text":
                                first, *rest = text.splitlines()
                                slot_dict[mdl_key] = {
                                    "title": first.strip(),
                                    "text":  "<p>" + "\n".join(rest).strip() + "</p>"
                                }
                            else:
                                slot_dict[mdl_key] = { "content": f"<p>{text}</p>" }

                            result_map[day][pid][model_id] = raw_key
                            log.info(f"✅ Generated {ftype} content for {model_id} on {pid}")
                            
                        except Exception as e:
                            log.error("❌ Failed to process %s for %s on %s: %s", 
                                      model_id, pid, day, e)
                            result_map[day][pid][model_id] = f"ERROR: {str(e)}"
                            continue

                save_paper_json(paper_key, paper)
                log.info("✅ Completed processing for %s", day)
                
            except Exception as e:
                log.error("❌ Failed to process date %s: %s", day, e)
                result_map[day] = {"error": str(e)}
                continue

        processing_time = time.time() - start_time
        successful_dates = [d for d in result_map.keys() if "error" not in result_map[d]]
        
        # Worker mode returns simple success response
        if event.get("worker_mode"):
            prompts_processed = sum(
                len([1 for pid_results in day_results.values() 
                     for model_result in pid_results.values() 
                     if not str(model_result).startswith("ERROR")])
                for day_results in result_map.values()
                if "error" not in day_results
            )
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "status": "success",
                    "prompts_processed": prompts_processed,
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
                "dates_processed": len(successful_dates),
                "dates_failed": len(dates) - len(successful_dates),
                "total_dates": len(dates),
                "prompt_ids": prompt_ids,
                "models_used": model_ids,
                "result_map": result_map
            })
        }
        
    except Exception as e:
        log.error("LLM generation failed: %s", str(e))
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "error",
                "error": str(e),
                "model": event.get("model", "unknown"),
                "date": event.get("date", "unknown")
            })
        }
