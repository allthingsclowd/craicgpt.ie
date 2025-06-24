# ╔══════════════════════════════════════════════════════════════════════╗
#  llm_runner.py – CraicGPT “newspaper” text-generation pipeline
# ╟──────────────────────────────────────────────────────────────────────╢
#  PURPOSE
#  ▸ For each requested **date × prompt × Bedrock text model**:
#      1. Pull the prompt JSON from S3 (`prompts/YYYY-MM-DD/<prompt_id>.json`)
#      2. Call the model (chat schema when supported)
#           – automatic **exponential back-off** on ThrottlingException
#           – automatic fallback to minimal single-prompt schema on
#             ValidationException
#      3. Save raw output ➜ `results/<date>/<prompt>/<model>.txt`
#      4. Merge output into    `static_assets/content/website/YYYY/MM/DD/paper_content.json`
#      5. **NEW:** Log total **output-tokens per rolling minute** so you
#         can compare with Bedrock token-per-minute quotas.
#
#  PROMPT-ID → NEWSPAPER SLOT MAP
#      llm_01 → mainArticle        {title, text}
#      llm_02 → comparisonArticle  {title, text}
#      llm_03 → llmStory           {content}
#      llm_04 → joke               {content}
#
#  MODEL SUPPORT
#      • Anthropic Claude (chat)           • Mistral / Mixtral (chat)
#      • Amazon Titan Text                 • Cohere Command-R
#      • AI-21 Jurassic-2                  • Generic fallback {"prompt": …}
#      • Any “*embed*” model is **skipped by default** (vectors, not prose).
#        Set env `ALLOW_EMBED_MODELS=true` to include them.
#
#  RESILIENCE
#      • safe_invoke() retries up to 6× with exponential back-off
#        (0.25 s → 0.5 s → 1 s → 2 s …) on *ThrottlingException*.
#      • On *ValidationException* the code logs the body and retries once
#        with a universal single-prompt schema, else skips the model.
#
#  PERMISSIONS
#      s3:GetObject, s3:PutObject  – PROMPT_BUCKET
#      bedrock:InvokeModel        – each model you call
#
#  RUNTIME
#      Python 3.12   •   AWS Region default: eu-west-1
# ╚══════════════════════════════════════════════════════════════════════╝
import os, json, re, time, random, logging
import boto3, botocore.exceptions
from datetime import datetime
from zoneinfo import ZoneInfo

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

slug = lambda m: re.sub(r'[:/]', '_', m)       # safe filename helper

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
    key = f"{PAPER_CONTENT_DIR}/{y}/{m}/{d}/paper_content.json" # Changed filename and variable
    try:
        return key, json.loads(s3_read(key))
    except s3.exceptions.NoSuchKey:
        paper = {
            "publicationDate": f"{y}-{m}-{d}",
            "metadata": { "bannerTitle": "The Artificially Intelligent Times",
                          "defaultLLM": "anthropic.claude-3-sonnet-20240229-v1",
                          "defaultImageGen": "amazon.titan-image-generator-v1" },
            "contentSlots": {
                "mainArticle":       { "llmOutputs": {}, "imageOutputs": {} },
                "authorBio":         { "text": "<p>Editor bio not generated yet.</p>" },
                "comparisonArticle": { "llmOutputs": {}, "imageOutputs": {} },
                "llmStory":          { "llmOutputs": {}, "imageOutputs": {} }, # Added imageOutputs
                "joke":              { "llmOutputs": {}, "imageOutputs": {} }, # Added imageOutputs
                "advertisements":    { "imageOutputs": {} }
            }
        }
        return key, paper

def save_paper_json(key, obj):
    s3_put(key, json.dumps(obj, indent=2), "application/json")

# ─── Prompt → slot mapping ──────────────────────────────────────────────
PROMPT_TO_SLOT = {
    "llm_01": ("mainArticle",        "title_text"),
    "llm_02": ("comparisonArticle",  "title_text"),
    "llm_03": ("llmStory",           "content"),
    "llm_04": ("joke",               "content")
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

# ─── Lambda entrypoint ──────────────────────────────────────────────────
def lambda_handler(event, _ctx):
    dates      = event.get("dates") or [event.get("date", today_iso())]
    prompt_ids = event.get("prompt_ids") or [f"llm_{i:02}" for i in range(1,5)]
    model_ids  = event.get("model_ids")  or DEFAULT_MODELS

    if not ALLOW_EMBED:
        embed_skip = [m for m in model_ids if "embed" in m.lower()]
        model_ids  = [m for m in model_ids if m not in embed_skip]
        if embed_skip:
            log.info("Skipping embedding models: %s", ", ".join(embed_skip))
    if not model_ids:
        raise ValueError("No generative models to run")

    result_map = {}

    # ── rolling token-budget globals ────────────────────────────────────
    global _tok_total, _tok_start
    _tok_total, _tok_start = 0, time.time()

    for day in dates:
        y, m, d = day.split("-")
        paper_key, paper = load_paper_json(y, m, d)
        result_map[day] = {}

        for pid in prompt_ids:
            slot, ftype = PROMPT_TO_SLOT.get(pid, (None, None))
            if slot is None:
                log.warning("Unknown prompt_id %s – skipped", pid)
                continue

            prompt_txt = json.loads(
                s3_read(f"{PROMPT_ROOT}/{y}/{m}/{d}/{pid}.json"))["prompt"]

            result_map[day][pid] = {}

            for model_id in model_ids:
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

                # ── NEW: rolling token-budget logging ───────────────────
                usage = payload.get("usage") or payload.get("usage_metadata") or {}
                out_tok = (usage.get("output_tokens") or
                           usage.get("generated_tokens") or 0)
                _tok_total += out_tok
                if time.time() - _tok_start >= 60:
                    log.info("📊  Output-tokens last 60 s: %d", _tok_total)
                    _tok_total, _tok_start = 0, time.time()
                # ────────────────────────────────────────────────────────

                raw_key = f"results/{day}/{pid}/{slug(model_id)}.txt"
                s3_put(raw_key, text)

                mdl_slug  = model_id.split(":")[0].split("/")[-1]
                slot_dict = paper["contentSlots"][slot]["llmOutputs"]
                if ftype == "title_text":
                    first, *rest = text.splitlines()
                    slot_dict[mdl_slug] = {
                        "title": first.strip(),
                        "text":  "<p>" + "\n".join(rest).strip() + "</p>"
                    }
                else:
                    slot_dict[mdl_slug] = { "content": f"<p>{text}</p>" }

                result_map[day][pid][model_id] = raw_key

        save_paper_json(paper_key, paper)

    return {
        "status": "OK",
        "dates_processed": dates,
        "prompt_ids": prompt_ids,
        "models_used": model_ids,
        "result_map": result_map
    }
