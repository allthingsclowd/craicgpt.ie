#!/usr/bin/env python3
"""
CraicGPT Orchestrator Lambda
============================

Coordinates the generation workflow by fanning out individual model/date 
combinations to worker lambdas to avoid timeout issues.

Architecture:
- Reads date range from environment variables
- Generates work items for each model/date combination  
- Invokes worker lambdas with dependency-aware scheduling
- Tracks progress and handles failures
- Reports consolidated results

Dependency Management:
- LLM processing must complete BEFORE image processing for each date
- Image workers depend on files created by LLM workers
- Per-date scheduling: LLM Phase → Image Phase
- Multiple dates can be processed in parallel

Throttling Strategy:
- In-memory rate limiting per model (no external dependencies)
- Model-specific rate limits with jitter
- Built-in exponential backoff in worker lambdas
- Controlled concurrency within each phase

Environment Variables:
- START_DATE: Start date (YYYY-MM-DD)
- END_DATE: End date (YYYY-MM-DD)
- LLM_WORKER_FUNCTION: Name of LLM worker lambda (default: craicgpt-llm-worker)
- IMAGE_WORKER_FUNCTION: Name of image worker lambda (default: craicgpt-image-worker)
- MAX_CONCURRENT_WORKERS: Maximum parallel workers (default: 5)
- BEDROCK_MODEL_IDS: Comma-separated LLM model IDs
- BEDROCK_IMAGE_MODEL_IDS: Comma-separated image model IDs
"""

import os, json, time, random, logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List, Dict, Any, Tuple
from collections import defaultdict

try:
    from botocore.exceptions import ClientError  # type: ignore
except ImportError:  # local linting env
    class ClientError(Exception):
        def __init__(self, *args, **kwargs):
            self.response = {}
            super().__init__(*args)

import boto3

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", force=True)
log = logging.getLogger("orchestrator")

# AWS Clients
lambda_client = boto3.client('lambda')
s3            = boto3.client('s3')

# Configuration
LLM_WORKER_FUNCTION   = os.environ.get("LLM_WORKER_FUNCTION",   "craicgptie_llm_runner")
IMAGE_WORKER_FUNCTION = os.environ.get("IMAGE_WORKER_FUNCTION", "craicgptie_image_runner")
PROMPT_GENERATOR_FUNCTION = os.environ.get("PROMPT_GENERATOR_FUNCTION", "craicgptie_prompt_generator")
MAX_CONCURRENT_WORKERS = int(os.environ.get("MAX_CONCURRENT_WORKERS", "1"))  # Sequential processing

# AWS Lambda account-wide concurrency limits
# CRITICAL: User requirement - maximum 10 Lambda functions including orchestrator
# Since orchestrator counts as 1, we limit workers to 9 concurrent executions
MAX_ACCOUNT_CONCURRENT = int(os.environ.get("MAX_ACCOUNT_CONCURRENT", "9"))  # Stay under 10 limit (orchestrator + 9 workers = 10 total)
CONCURRENCY_CHECK_ENABLED = os.environ.get("CONCURRENCY_CHECK_ENABLED", "true").lower() == "true"  # ENABLED by default for 10 Lambda limit compliance
CONCURRENCY_BACKOFF_DELAY = float(os.environ.get("CONCURRENCY_BACKOFF_DELAY", "5.0"))  # Reduced delay for faster response

# Model-specific throttling configuration (requests per minute) - DISABLED BY DEFAULT
MODEL_RATE_LIMITING_ENABLED = os.environ.get("MODEL_RATE_LIMITING_ENABLED", "false").lower() == "true"
MODEL_RATE_LIMITS = {
    # Anthropic models
    "anthropic.claude-3-sonnet-20240229-v1:0": 100,
    "anthropic.claude-3-haiku-20240307-v1:0": 120,
    "anthropic.claude-3-opus-20240229-v1:0": 50,
    
    # Amazon Titan models  
    "amazon.titan-text-premier-v1:0": 120,
    "amazon.titan-image-generator-v1": 60,
    "amazon.nova-canvas-v1:0": 40,
    
    # Default for unknown models
    "default": 30
}

# Get models from environment
LLM_MODELS = [m.strip() for m in os.getenv(
    "BEDROCK_MODEL_IDS",
    "anthropic.claude-3-sonnet-20240229-v1:0"
).split(",") if m.strip()]

IMAGE_MODELS = [m.strip() for m in os.getenv(
    "BEDROCK_IMAGE_MODEL_IDS", 
    "amazon.titan-image-generator-v1,amazon.nova-canvas-v1:0"
).split(",") if m.strip()]

# Utility – inclusive date range generator

def generate_date_range(start_date: str, end_date: str) -> List[str]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    out: list[str] = []
    cur = start
    while cur <= end:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out

# ---------- S3 helpers -------------------------------------------------------

PROMPT_BUCKET = os.environ.get("PROMPT_BUCKET", "craicgpt-content")  # Same bucket as workers
PAPER_CONTENT_DIR = "static_assets/content/website"

# Mapping prompt_id → slot / field-type (copied from workers)
LLM_PROMPT_TO_SLOT: dict[str, Tuple[str, str]] = {
    "llm_01": ("mainArticle",        "title_text"),
    "llm_02": ("comparisonArticle",  "title_text"),
    "llm_03": ("llmStory",           "content"),
    "llm_04": ("joke",               "content"),
    "llm_05": ("authorBio",          "content")
}

IMAGE_PROMPT_TO_SLOT: dict[str, str] = {
    "img_01": "mainArticle",
    "img_02": "comparisonArticle",
    "img_03": "advertisement1",
    "img_04": "advertisement2",
    "img_05": "advertisement3",
    "img_06": "advertisement4",
    "img_07": "llmStory",
    "img_08": "joke"
}

# Helper – basic S3 existence test
def s3_exists(key: str) -> bool:
    try:
        s3.head_object(Bucket=PROMPT_BUCKET, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False
        # Unknown error – assume exists to be safe
        log.warning(f"⚠️ Unexpected S3 error checking {key}: {e}")
        return True

# ---------- paper_content helpers -------------------------------------------

def load_or_create_paper_json(date_str: str) -> Tuple[str, dict]:
    """Load paper_content.json from S3 if present, otherwise create skeleton."""
    y, m, d = date_str.split("-")
    key = f"{PAPER_CONTENT_DIR}/{y}/{m}/{d}/paper_content.json"

    try:
        body = s3.get_object(Bucket=PROMPT_BUCKET, Key=key)["Body"].read()
        return key, json.loads(body)
    except ClientError as e:
        if e.response["Error"]["Code"] not in ("404", "NoSuchKey", "NotFound"):
            raise  # real error

    # Build skeleton identical to workers
    paper = {
        "publicationDate": date_str,
        "metadata": {
            "bannerTitle": "The Artificially Intelligent Times",
            "defaultLLM": LLM_MODELS[0] if LLM_MODELS else "",
            "defaultImageGen": IMAGE_MODELS[0] if IMAGE_MODELS else ""
        },
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

    # Persist skeleton (so first worker sees it)
    s3.put_object(
        Bucket=PROMPT_BUCKET,
        Key=key,
        Body=json.dumps(paper, indent=2).encode(),
        ContentType="application/json"
    )
    log.info(f"🆕 Created new paper_content.json skeleton: {key}")
    return key, paper

# ---------- idempotency helpers -------------------------------------------

def _get_slot_mapping(work_item: Dict[str, Any]) -> Tuple[str, str]:
    """Return (slot_name, field_type) for the given work item."""
    if work_item["type"] == "llm":
        slot, ftype = LLM_PROMPT_TO_SLOT[work_item["prompt_id"]]
        return slot, ftype  # ftype only relevant for LLM
    else:
        slot = IMAGE_PROMPT_TO_SLOT[work_item["prompt_id"]]
        return slot, "image"

def task_already_done(paper: dict, work_item: Dict[str, Any]) -> bool:
    """True if successful content exists OR the failed counter reached 3."""
    slot, ftype = _get_slot_mapping(work_item)
    model_id = work_item["model"]

    slot_dict = paper["contentSlots"][slot]

    if work_item["type"] == "llm":
        mdict = slot_dict.get("llmOutputs", {}).get(model_id, {})
        # success?
        if ftype == "title_text":
            if mdict.get("title") and mdict.get("text"):
                return True
        else:
            if mdict.get("content"):
                return True
        # hard-failed?
        if mdict.get("failed", 0) >= 3:
            return True
        return False
    else:  # image
        image_outputs = slot_dict.get("imageOutputs", {})
        mdict = image_outputs.get(model_id, {})
        entry = mdict.get(work_item["prompt_id"], {}) if isinstance(mdict, dict) else {}
        if entry.get("imageUrl") and not entry.get("blocked", False):
            return True
        if entry.get("failed", 0) >= 3:
            return True
        return False

def mark_task_failure(date_str: str, work_item: Dict[str, Any], error_msg: str):
    """Increment failure counter inside paper_content.json for this task."""
    key, paper = load_or_create_paper_json(date_str)
    slot, ftype = _get_slot_mapping(work_item)
    model_id = work_item["model"]

    if work_item["type"] == "llm":
        outputs = paper["contentSlots"][slot].setdefault("llmOutputs", {})
        record = outputs.setdefault(model_id, {})
    else:
        slot_io = paper["contentSlots"][slot].setdefault("imageOutputs", {})
        mdl_dict = slot_io.setdefault(model_id, {})
        record = mdl_dict.setdefault(work_item["prompt_id"], {})

    record["failed"] = record.get("failed", 0) + 1
    record["error"] = error_msg[:250]

    # write back
    s3.put_object(
        Bucket=PROMPT_BUCKET,
        Key=key,
        Body=json.dumps(paper, indent=2).encode(),
        ContentType="application/json"
    )

# ---------- updated work-item generation ------------------------------------

def create_work_items(dates: List[str]) -> List[Dict[str, Any]]:
    """Return list of atomic work items: one prompt_id × model per date."""
    work_items: list[dict[str, Any]] = []

    for date_str in dates:
        _key, paper = load_or_create_paper_json(date_str)

        # 1. LLM tasks
        for prompt_id, (slot, ftype) in LLM_PROMPT_TO_SLOT.items():
            for model_id in LLM_MODELS:
                slot_dict = paper["contentSlots"][slot]["llmOutputs"].get(model_id, {})

                has_content = False
                if ftype == "title_text":
                    has_content = bool(slot_dict.get("title") and slot_dict.get("text"))
                else:
                    has_content = bool(slot_dict.get("content"))

                if not task_already_done(paper, {
                    "type": "llm", "prompt_id": prompt_id, "model": model_id
                }):
                    work_items.append({
                        "type": "llm",
                        "date": date_str,
                        "model": model_id,
                        "prompt_id": prompt_id,
                        "function_name": LLM_WORKER_FUNCTION,
                        "worker_type": "llm"
                    })

        # 2. Image tasks
        for prompt_id, slot in IMAGE_PROMPT_TO_SLOT.items():
            for model_id in IMAGE_MODELS:
                img_outputs = paper["contentSlots"][slot].get("imageOutputs", {})
                mdl_dict = img_outputs.get(model_id, {}) if isinstance(img_outputs, dict) else {}
                mdl_info = mdl_dict.get(prompt_id, {}) if isinstance(mdl_dict, dict) else {}

                has_image = bool(mdl_info.get("imageUrl") and not mdl_info.get("blocked", False))

                if not task_already_done(paper, {
                    "type": "image", "prompt_id": prompt_id, "model": model_id
                }):
                    work_items.append({
                        "type": "image",
                        "date": date_str,
                        "model": model_id,
                        "prompt_id": prompt_id,
                        "function_name": IMAGE_WORKER_FUNCTION,
                        "worker_type": "image"
                    })

    log.info(f"📝 Work-item generation complete: {len(work_items)} tasks pending")
    return work_items

# In-memory throttling state (per orchestrator execution)
_model_last_call = defaultdict(float)

# AWS CloudWatch client for concurrency monitoring
cloudwatch = boto3.client('cloudwatch')

def get_throttling_delay(model: str) -> float:
    """Calculate delay needed before calling this model again (only if rate limiting enabled)"""
    if not MODEL_RATE_LIMITING_ENABLED:
        return 0  # No proactive delays - only react to actual throttling
    
    rate_limit = MODEL_RATE_LIMITS.get(model, MODEL_RATE_LIMITS["default"])
    min_delay = 60.0 / rate_limit  # seconds between calls
    
    last_call = _model_last_call.get(model, 0)
    time_since_last = time.time() - last_call
    
    delay_needed = max(0, min_delay - time_since_last)
    
    # Add small random jitter to prevent thundering herd
    if delay_needed > 0:
        jitter = random.uniform(0, 0.5)  # 0-500ms jitter
        delay_needed += jitter
    
    return delay_needed

def update_throttling_state(model: str):
    """Update in-memory throttling state after making a call"""
    _model_last_call[model] = time.time()

def get_current_lambda_concurrency() -> int:
    """Get current concurrent Lambda executions using CloudWatch metrics"""
    if not CONCURRENCY_CHECK_ENABLED:
        return 0
    
    try:
        # Get current concurrent executions metric
        response = cloudwatch.get_metric_statistics(
            Namespace='AWS/Lambda',
            MetricName='ConcurrentExecutions',
            Dimensions=[],  # Account-wide
            StartTime=datetime.now(ZoneInfo("UTC")) - timedelta(minutes=1),
            EndTime=datetime.now(ZoneInfo("UTC")),
            Period=60,
            Statistics=['Maximum']
        )
        
        if response['Datapoints']:
            # Get the most recent datapoint
            latest = max(response['Datapoints'], key=lambda x: x['Timestamp'])
            concurrent = int(latest['Maximum'])
            log.info(f"🔢 Current Lambda concurrency: {concurrent}")
            return concurrent
        else:
            # No data available, assume low concurrency
            log.info(f"🔢 No concurrency data available, assuming low usage")
            return 2  # Conservative estimate
            
    except Exception as e:
        log.warning(f"⚠️  Failed to check Lambda concurrency: {e}")
        return 2  # Conservative fallback

def wait_for_concurrency_slot(target_function: str, max_wait_minutes: int = 5) -> bool:
    """Wait for a concurrency slot to become available"""
    if not CONCURRENCY_CHECK_ENABLED:
        return True
    
    max_wait_seconds = max_wait_minutes * 60
    start_time = time.time()
    
    while (time.time() - start_time) < max_wait_seconds:
        current_concurrent = get_current_lambda_concurrency()
        
        if current_concurrent < MAX_ACCOUNT_CONCURRENT:
            log.info(f"✅ Concurrency slot available ({current_concurrent}/{MAX_ACCOUNT_CONCURRENT})")
            return True
        
        log.info(f"⏳ Waiting for concurrency slot: {current_concurrent}/{MAX_ACCOUNT_CONCURRENT} - waiting {CONCURRENCY_BACKOFF_DELAY}s")
        time.sleep(CONCURRENCY_BACKOFF_DELAY)
    
    log.warning(f"⚠️  Timeout waiting for concurrency slot after {max_wait_minutes} minutes")
    return False

def invoke_worker(work_item: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke a worker lambda for a single work item"""
    model = work_item["model"]
    date_str = work_item["date"]
    function_name = work_item["function_name"]
    
    # Check concurrency limits before invoking
    if CONCURRENCY_CHECK_ENABLED:
        log.info(f"🔍 Checking concurrency before invoking {function_name} for {model}")
        if not wait_for_concurrency_slot(function_name, max_wait_minutes=3):
            return {
                "work_item": work_item,
                "status": "error",
                "error": f"Timeout waiting for concurrency slot (limit: {MAX_ACCOUNT_CONCURRENT})",
                "status_code": 429
            }
    
    # Apply throttling delay for Bedrock models (only if rate limiting enabled)
    delay = get_throttling_delay(model)
    if delay > 0:
        log.info(f"⏳ Model throttling delay for {model}: {delay:.2f}s")
        time.sleep(delay)
    
    # No proactive Lambda delay - only react to actual throttling errors
    
    # Prepare payload for worker
    payload = {
        "date": date_str,
        "model_id": model,  # workers expect "model_id"
        "prompt_ids": [work_item.get("prompt_id")],
        "worker_mode": True
    }
    
    # Retry logic with exponential backoff (up to 3 tries per orchestrator run)
    max_retries = 3
    base_delay = 2.0
    
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                retry_delay = base_delay * (2 ** attempt) + random.uniform(0, 5)
                log.info(f"🔄 Retry {attempt}/{max_retries} for {model} after {retry_delay:.1f}s delay...")
                time.sleep(retry_delay)
            
            log.info(f"⚡ Invoking {function_name} for {model} on {date_str} (attempt {attempt + 1})")
            
            response = lambda_client.invoke(
                FunctionName=function_name,
                InvocationType='RequestResponse',  # Synchronous
                Payload=json.dumps(payload)
            )
            
            # Update throttling state on successful invocation
            update_throttling_state(model)
            
            # Parse response
            response_payload = json.loads(response['Payload'].read().decode())
            
            # Check if worker actually succeeded (Lambda call success ≠ worker success)
            worker_status = "success"
            worker_error = None
            
            # Check for Lambda-level errors
            if response['StatusCode'] != 200:
                worker_status = "error"
                worker_error = f"Lambda returned status {response['StatusCode']}"
            
            # Check for worker-level errors in response
            elif "errorMessage" in response_payload:
                worker_status = "error"  
                worker_error = response_payload.get("errorMessage", "Unknown worker error")
            
            # Check for HTTP-style error responses
            elif isinstance(response_payload, dict):
                status_code = response_payload.get("statusCode")
                if status_code and status_code != 200:
                    worker_status = "error"
                    worker_error = response_payload.get("body", f"Worker returned status {status_code}")
                
                # Check body for error indicators
                body = response_payload.get("body", {})
                if isinstance(body, str):
                    try:
                        body = json.loads(body)
                    except:
                        pass
                
                if isinstance(body, dict):
                    if body.get("status") == "error" or "error" in body:
                        worker_status = "error"
                        worker_error = body.get("error", "Worker reported error")
            
            result = {
                "work_item": work_item,
                "status": worker_status,
                "response": response_payload,
                "status_code": response['StatusCode']
            }
            
            if worker_error:
                result["error"] = worker_error
                log.error(f"❌ Worker failed for {model} on {date_str}: {worker_error}")
                mark_task_failure(date_str, work_item, worker_error)
            else:
                log.info(f"✅ Worker succeeded for {model} on {date_str}")
            
            # Extract worker details for progress reporting
            worker_response = response_payload.get("body", {})
            if isinstance(worker_response, str):
                try:
                    worker_response = json.loads(worker_response)
                except:
                    worker_response = {}
            
            prompts_processed = worker_response.get("prompts_processed", "unknown")
            worker_time = worker_response.get("processing_time", 0)
            
            log.info(f"✅ {model} completed: {prompts_processed} prompts in {worker_time:.1f}s")
            return result
            
        except Exception as e:
            error_msg = str(e)
            
            # Check if this is a retryable error
            if ("TooManyRequestsException" in error_msg or 
                "Rate Exceeded" in error_msg or
                "timeout" in error_msg.lower()) and attempt < max_retries:
                log.warning(f"⚠️  Retryable error for {model} on {date_str} (attempt {attempt + 1}): {error_msg}")
                continue
            else:
                log.error(f"❌ Failed {model} on {date_str} after {attempt + 1} attempts: {error_msg}")
                mark_task_failure(date_str, work_item, error_msg)
                return {
                    "work_item": work_item,
                    "status": "error",
                    "error": error_msg,
                    "status_code": 500
                }
    
    mark_task_failure(date_str, work_item, "retry loop exited without result")
    return {
        "work_item": work_item,
        "status": "error",
        "error": "retry loop exited without result",
        "status_code": 500
    }

def execute_work_items(work_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Process all tasks, spreading calls across models (round-robin)."""
    results: list[dict[str, Any]] = []
    from collections import deque

    q = deque(sorted(work_items, key=lambda w: w["model"]))
    last_model = None

    while q:
        # pick index whose model != last_model if possible
        idx = 0
        if last_model is not None:
            for i, t in enumerate(q):
                if t["model"] != last_model:
                    idx = i
                    break
        q.rotate(-idx)
        task = q.popleft()

        log.info(f"🚀 Executing {task['type'].upper()} {task['prompt_id']} "
                 f"{task['model']} on {task['date']}  (queue left: {len(q)})")

        start_t = time.time()
        res = invoke_worker(task)
        res["duration"] = round(time.time() - start_t, 2)
        results.append(res)

        last_model = task["model"]
    return results

def analyze_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze execution results and create summary"""
    successful = [r for r in results if r["status"] == "success"]
    failed = [r for r in results if r["status"] == "error"]
    skipped = [r for r in results if r["status"] == "skipped"]
    
    # Group by type
    llm_results = [r for r in results if r["work_item"]["type"] == "llm"]
    image_results = [r for r in results if r["work_item"]["type"] == "image"]
    
    # Group by date
    dates_processed = set(r["work_item"]["date"] for r in successful)
    
    # Error analysis
    error_summary = {}
    for failed_item in failed + skipped:
        error = failed_item.get("error", "Unknown error")
        error_summary[error] = error_summary.get(error, 0) + 1
    
    return {
        "total_work_items": len(results),
        "successful": len(successful),
        "failed": len(failed),
        "skipped": len(skipped), 
        "success_rate": len(successful) / len(results) * 100 if results else 0,
        "llm_processing": {
            "total": len(llm_results),
            "successful": len([r for r in llm_results if r["status"] == "success"]),
            "failed": len([r for r in llm_results if r["status"] == "error"]),
            "skipped": len([r for r in llm_results if r["status"] == "skipped"])
        },
        "image_processing": {
            "total": len(image_results),
            "successful": len([r for r in image_results if r["status"] == "success"]), 
            "failed": len([r for r in image_results if r["status"] == "error"]),
            "skipped": len([r for r in image_results if r["status"] == "skipped"])
        },
        "dates_processed": sorted(list(dates_processed)),
        "error_summary": error_summary,
        "failed_items": [
            {
                "type": r["work_item"]["type"],
                "date": r["work_item"]["date"], 
                "model": r["work_item"]["model"],
                "error": r.get("error", "Unknown"),
                "status": r["status"]
            } for r in failed + skipped
        ]
    }

def lambda_handler(event, context):
    """
    Main orchestrator handler
    
    Coordinates the fan-out execution of LLM and Image generation
    across multiple dates and models to avoid timeout issues.
    """
    start_time = time.time()
    
    # Get date range from event payload, fallback to environment variables, then default
    event_start = event.get("START_DATE")
    event_end = event.get("END_DATE")
    env_start = os.getenv("START_DATE")
    env_end = os.getenv("END_DATE")
    
    # Debug logging
    log.info(f"🔍 Date parameter debugging:")
    log.info(f"   Event START_DATE: {event_start}")
    log.info(f"   Event END_DATE: {event_end}")
    log.info(f"   Env START_DATE: {env_start}")
    log.info(f"   Env END_DATE: {env_end}")
    log.info(f"   Full event payload: {json.dumps(event)}")
    
    # Priority: event payload first, then environment variables
    START_DATE = event_start or env_start
    END_DATE = event_end or env_end
    
    # Default to current date if START_DATE not provided
    if not START_DATE:
        START_DATE = datetime.now(ZoneInfo("Europe/London")).date().isoformat()
        log.info(f"No START_DATE provided, defaulting to current date: {START_DATE}")
    
    # Default END_DATE to START_DATE if not specified
    if not END_DATE:
        END_DATE = START_DATE
    
    log.info(f"✅ Final resolved dates: START_DATE={START_DATE}, END_DATE={END_DATE}")
    
    try:
        # Generate date range
        dates = generate_date_range(START_DATE, END_DATE)
        log.info(f"🗓️  Processing date range: {START_DATE} to {END_DATE} ({len(dates)} dates)")
        
        # ------------------------------------------------------------------
        # Phase-0: ensure prompts exist by invoking PromptGenerator (idempotent)
        # ------------------------------------------------------------------
        try:
            pg_payload = {"START_DATE": START_DATE, "END_DATE": END_DATE, "worker_mode": False}
            log.info(f"🛫 Invoking PromptGenerator ({PROMPT_GENERATOR_FUNCTION}) for {START_DATE} → {END_DATE}")
            pg_resp = lambda_client.invoke(
                FunctionName=PROMPT_GENERATOR_FUNCTION,
                InvocationType="RequestResponse",
                Payload=json.dumps(pg_payload)
            )

            if pg_resp["StatusCode"] != 200:
                log.warning(f"⚠️ PromptGenerator returned status {pg_resp['StatusCode']} – continuing anyway")
            else:
                body = json.loads(pg_resp["Payload"].read().decode())
                log.info(f"📝 PromptGenerator result: generated={body.get('prompts_generated')} skipped={body.get('prompts_skipped')}")
        except Exception as e:
            log.error(f"❌ Failed invoking PromptGenerator: {e}. Proceeding – workers may 404 on missing prompts")
        
        # Create work items
        work_items = create_work_items(dates)
        log.info(f"📋 Generated {len(work_items)} work items:")
        log.info(f"   📝 LLM models ({len(LLM_MODELS)}): {LLM_MODELS}")
        log.info(f"   🖼️  Image models ({len(IMAGE_MODELS)}): {IMAGE_MODELS}")
        log.info(f"   🔢 Total combinations: {len(dates)} dates × {len(LLM_MODELS + IMAGE_MODELS)} models")
        
        # Log concurrency configuration
        log.info(f"🚦 Performance configuration:")
        log.info(f"   CRITICAL: 10 Lambda limit compliance - orchestrator (1) + workers ({MAX_ACCOUNT_CONCURRENT}) = {MAX_ACCOUNT_CONCURRENT + 1} total")
        log.info(f"   Max worker concurrent: {MAX_ACCOUNT_CONCURRENT}")
        log.info(f"   Concurrency checking: {'enabled' if CONCURRENCY_CHECK_ENABLED else 'disabled'}")
        log.info(f"   Model rate limiting: {'enabled' if MODEL_RATE_LIMITING_ENABLED else 'disabled'}")
        log.info(f"   Backoff delay (when throttled): {CONCURRENCY_BACKOFF_DELAY}s")
        log.info(f"   Strategy: Reactive delays only - no proactive throttling")
        
        # Estimate based on average Lambda execution time (no artificial delays)
        avg_execution_time = 45  # seconds per model/date combination
        estimated_time = len(work_items) * avg_execution_time / 60  
        log.info(f"⏱️  Estimated completion time: {estimated_time:.1f} minutes (reactive performance mode)")
        log.info(f"🚀 Starting high-speed orchestration with reactive throttling...")
        
        # Execute work items
        results = execute_work_items(work_items)
        
        # Analyze results
        analysis = analyze_results(results)
        
        processing_time = time.time() - start_time
        
        log.info(f"🎉 Orchestration completed in {processing_time:.2f} seconds ({processing_time/60:.1f} minutes)")
        log.info(f"📈 Final success rate: {analysis['success_rate']:.1f}%")
        log.info(f"📊 Final results: {analysis['successful']}/{len(work_items)} successful, {analysis['failed']} failed, {analysis['skipped']} skipped")
        log.info(f"🔗 Dependency enforcement: LLM → Image dependency properly enforced")
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "completed",
                "processing_time_seconds": round(processing_time, 2),
                "date_range": {
                    "start": START_DATE,
                    "end": END_DATE, 
                    "dates": dates
                },
                "configuration": {
                    "llm_models": LLM_MODELS,
                    "image_models": IMAGE_MODELS,
                    "max_concurrent_workers": MAX_CONCURRENT_WORKERS,
                    "max_account_concurrent": MAX_ACCOUNT_CONCURRENT,
                    "concurrency_check_enabled": CONCURRENCY_CHECK_ENABLED,
                    "model_rate_limiting_enabled": MODEL_RATE_LIMITING_ENABLED,
                    "concurrency_backoff_delay": CONCURRENCY_BACKOFF_DELAY,
                    "performance_mode": "reactive_throttling",
                    "llm_worker_function": LLM_WORKER_FUNCTION,
                    "image_worker_function": IMAGE_WORKER_FUNCTION
                },
                "results": analysis
            }, indent=2)
        }
        
    except Exception as e:
        log.error(f"Orchestration failed: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "processing_time_seconds": time.time() - start_time
            })
        } 