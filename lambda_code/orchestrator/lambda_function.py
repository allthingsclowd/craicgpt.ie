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

import os
import json
import boto3
import time
import random
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
# Removed concurrent.futures - using sequential processing to avoid Lambda limits
from typing import List, Dict, Any, Tuple
import logging
from collections import defaultdict

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("orchestrator")

# AWS Clients
lambda_client = boto3.client('lambda')

# Configuration
LLM_WORKER_FUNCTION = os.environ.get("LLM_WORKER_FUNCTION", "craicgptie_llm_runner")
IMAGE_WORKER_FUNCTION = os.environ.get("IMAGE_WORKER_FUNCTION", "craicgptie_image_runner") 
MAX_CONCURRENT_WORKERS = int(os.environ.get("MAX_CONCURRENT_WORKERS", "1"))  # Sequential processing

# AWS Lambda account-wide concurrency limits
MAX_ACCOUNT_CONCURRENT = int(os.environ.get("MAX_ACCOUNT_CONCURRENT", "9"))  # Stay under 10 limit
CONCURRENCY_CHECK_ENABLED = os.environ.get("CONCURRENCY_CHECK_ENABLED", "false").lower() == "true"  # Disabled by default for speed
CONCURRENCY_BACKOFF_DELAY = float(os.environ.get("CONCURRENCY_BACKOFF_DELAY", "10.0"))  # Reduced from 30s to 10s

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

def generate_date_range(start_date: str, end_date: str) -> List[str]:
    """Generate list of dates between start and end (inclusive)"""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    
    dates = []
    current = start
    while current <= end:
        dates.append(current.isoformat())
        current += timedelta(days=1)
    
    return dates

def create_work_items(dates: List[str]) -> List[Dict[str, Any]]:
    """Create work items for each model/date combination"""
    work_items = []
    
    # LLM work items
    for date_str in dates:
        for model in LLM_MODELS:
            work_items.append({
                "type": "llm",
                "date": date_str,
                "model": model,
                "function_name": LLM_WORKER_FUNCTION,
                "worker_type": "llm"
            })
    
    # Image work items  
    for date_str in dates:
        for model in IMAGE_MODELS:
            work_items.append({
                "type": "image", 
                "date": date_str,
                "model": model,
                "function_name": IMAGE_WORKER_FUNCTION,
                "worker_type": "image"
            })
    
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
        "model_id": model,  # Fixed: workers expect "model_id"
        "worker_mode": True  # Tell worker to process only this model
    }
    
    # Retry logic with exponential backoff for Lambda throttling (only when actually throttled)
    max_retries = 3
    base_delay = 2.0  # Reduced from 10s to 2s for faster recovery
    
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
            
            result = {
                "work_item": work_item,
                "status": "success",
                "response": response_payload,
                "status_code": response['StatusCode']
            }
            
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
                return {
                    "work_item": work_item,
                    "status": "error", 
                    "error": error_msg,
                    "status_code": 500
                }
    
    # This should never be reached, but handle it for completeness
    return {
        "work_item": work_item,
        "status": "error", 
        "error": "Unexpected error: retry loop exited without result",
        "status_code": 500
    }

def execute_work_items(work_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Execute work items with dependency-aware scheduling (LLM before Image per date)"""
    results = []
    
    # Group work items by date and type for dependency management
    work_by_date = defaultdict(lambda: {"llm": [], "image": []})
    for item in work_items:
        work_by_date[item["date"]][item["type"]].append(item)
    
    dates = sorted(work_by_date.keys())
    log.info(f"Executing {len(work_items)} work items across {len(dates)} dates")
    log.info(f"Dependency constraint: LLM must complete before Image for each date")
    
    # Process each date with proper dependency ordering
    for date_str in dates:
        date_work = work_by_date[date_str]
        llm_items = date_work["llm"]
        image_items = date_work["image"]
        
        log.info(f"🗓️  Processing {date_str}: {len(llm_items)} LLM + {len(image_items)} Image work items")
        log.info(f"📋 LLM models to process: {[item['model'] for item in llm_items]}")
        log.info(f"🖼️  Image models to process: {[item['model'] for item in image_items]}")
        
        # Phase 1: Execute ALL LLM work items for this date
        if llm_items:
            log.info(f"🔸 Phase 1 - LLM processing for {date_str}: {len(llm_items)} items")
            llm_results = execute_work_phase(llm_items, f"LLM-{date_str}")
            results.extend(llm_results)
            
            # Check if LLM processing succeeded
            llm_success_count = len([r for r in llm_results if r["status"] == "success"])
            if llm_success_count == len(llm_items):
                log.info(f"✅ LLM phase completed for {date_str}: {llm_success_count}/{len(llm_items)} successful")
            else:
                log.warning(f"⚠️  LLM phase completed for {date_str}: {llm_success_count}/{len(llm_items)} successful")
        
        # Phase 2: Execute ALL Image work items for this date (only after LLM completes)
        if image_items:
            log.info(f"🔹 Phase 2 - Image processing for {date_str}: {len(image_items)} items")
            image_results = execute_work_phase(image_items, f"Image-{date_str}")
            results.extend(image_results)
            
            # Check if Image processing succeeded  
            image_success_count = len([r for r in image_results if r["status"] == "success"])
            if image_success_count == len(image_items):
                log.info(f"✅ Image phase completed for {date_str}: {image_success_count}/{len(image_items)} successful")
            else:
                log.warning(f"⚠️  Image phase completed for {date_str}: {image_success_count}/{len(image_items)} successful")
        
        # Log overall progress
        completed = len(results)
        total = len(work_items)
        success_rate = len([r for r in results if r["status"] == "success"]) / completed * 100 if completed > 0 else 0
        log.info(f"Date {date_str} completed. Overall progress: {completed}/{total} ({completed/total*100:.1f}%) - Success: {success_rate:.1f}%")
    
    return results

def execute_work_phase(work_items: List[Dict[str, Any]], phase_name: str) -> List[Dict[str, Any]]:
    """Execute a phase of work items (either all LLM or all Image for a date)"""
    results = []
    
    if not work_items:
        return results
    
    log.info(f"Starting {phase_name} with {len(work_items)} items")
    
    # Process work items sequentially to avoid Lambda concurrency limits
    for i, item in enumerate(work_items, 1):
        log.info(f"🚀 {phase_name} progress: {i}/{len(work_items)} - Starting {item['model']}")
        
        start_time = time.time()
        result = invoke_worker(item)
        duration = time.time() - start_time
        results.append(result)
        
        # Log individual result with timing
        status_emoji = "✅" if result["status"] == "success" else "❌"
        log.info(f"{status_emoji} {item['model']} completed in {duration:.1f}s")
        
        # Log overall progress
        completed = len(results)
        total = len(work_items)
        success_rate = len([r for r in results if r["status"] == "success"]) / completed * 100 if completed > 0 else 0
        log.info(f"📊 {phase_name} progress: {completed}/{total} ({completed/total*100:.1f}%) - Success: {success_rate:.1f}%")
    
    log.info(f"{phase_name} completed: {len([r for r in results if r['status'] == 'success'])}/{len(work_items)} successful")
    return results

def analyze_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze execution results and create summary"""
    successful = [r for r in results if r["status"] == "success"]
    failed = [r for r in results if r["status"] == "error"]
    
    # Group by type
    llm_results = [r for r in results if r["work_item"]["type"] == "llm"]
    image_results = [r for r in results if r["work_item"]["type"] == "image"]
    
    # Group by date
    dates_processed = set(r["work_item"]["date"] for r in successful)
    
    # Error analysis
    error_summary = {}
    for failed_item in failed:
        error = failed_item.get("error", "Unknown error")
        error_summary[error] = error_summary.get(error, 0) + 1
    
    return {
        "total_work_items": len(results),
        "successful": len(successful),
        "failed": len(failed), 
        "success_rate": len(successful) / len(results) * 100 if results else 0,
        "llm_processing": {
            "total": len(llm_results),
            "successful": len([r for r in llm_results if r["status"] == "success"]),
            "failed": len([r for r in llm_results if r["status"] == "error"])
        },
        "image_processing": {
            "total": len(image_results),
            "successful": len([r for r in image_results if r["status"] == "success"]), 
            "failed": len([r for r in image_results if r["status"] == "error"])
        },
        "dates_processed": sorted(list(dates_processed)),
        "error_summary": error_summary,
        "failed_items": [
            {
                "type": r["work_item"]["type"],
                "date": r["work_item"]["date"], 
                "model": r["work_item"]["model"],
                "error": r.get("error", "Unknown")
            } for r in failed
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
        
        # Create work items
        work_items = create_work_items(dates)
        log.info(f"📋 Generated {len(work_items)} work items:")
        log.info(f"   📝 LLM models ({len(LLM_MODELS)}): {LLM_MODELS}")
        log.info(f"   🖼️  Image models ({len(IMAGE_MODELS)}): {IMAGE_MODELS}")
        log.info(f"   🔢 Total combinations: {len(dates)} dates × {len(LLM_MODELS + IMAGE_MODELS)} models")
        
        # Log concurrency configuration
        log.info(f"🚦 Performance configuration:")
        log.info(f"   Max account concurrent: {MAX_ACCOUNT_CONCURRENT}")
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
        log.info(f"📊 Final results: {analysis['successful']}/{len(work_items)} successful, {analysis['failed']} failed")
        
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