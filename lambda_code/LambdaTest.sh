###############################################################################
# CraicGPT.ie backend run – edition 2025-07-01
###############################################################################

# ── 0 · environment ──────────────────────────────────────────────────────────
export AWS_DEFAULT_REGION=eu-west-1
export REAL_BUCKET=craicgpt-ie-production   # ← your real bucket

# function names / arns
export ORCH_FN=craicgptie-orchestrator
export ORCH_ARN=arn:aws:lambda:eu-west-1:217369101910:function:craicgptie-orchestrator

# ── 1 · one-time env-var fix for all three backend functions
###############################################################################
for FN in craicgptie-orchestrator craicgptie_llm_runner craicgptie_image_runner
do
  echo "Updating $FN to use bucket $REAL_BUCKET …"
  aws lambda update-function-configuration \
    --function-name "$FN" \
    --environment "Variables={PROMPT_BUCKET=${REAL_BUCKET}}" | cat
done

# ── 2 · re-run the edition workflow (exact same as before)
###############################################################################
export EDITION_DATE=2025-07-01

# ── 1 · run PromptGenerator (idempotent phase-0) ─────────────────────────────
aws lambda invoke \
  --function-name craicgptie_prompt_generator \
  --cli-binary-format raw-in-base64-out \
  --payload "{\"START_DATE\":\"${EDITION_DATE}\",\"END_DATE\":\"${EDITION_DATE}\"}" \
  prompt_generator_response.json | cat

cat prompt_generator_response.json | jq '. | {prompts_generated, prompts_skipped}'

# ── 2 · run the orchestrator (phases 1 & 2) ─────────────────────────────────
aws lambda invoke \
  --function-name "${ORCH_FN}" \
  --cli-binary-format raw-in-base64-out \
  --payload "{\"START_DATE\":\"${EDITION_DATE}\",\"END_DATE\":\"${EDITION_DATE}\"}" \
  orchestrator_response.json | cat

cat orchestrator_response.json | jq '.body | fromjson | {status, processing_time_seconds, results}'

# ── 3 · check the generated paper JSON in S3 ────────────────────────────────
S3_PATH="s3://${REAL_BUCKET}/static_assets/content/website/2025/07/01/paper_content.json"

aws s3 cp "${S3_PATH}" - | head -40
echo "…"
echo "Full file at: ${S3_PATH}"

# ── 4 · tail orchestrator logs (Ctrl-C to stop) ─────────────────────────────
aws logs tail "/aws/lambda/${ORCH_FN}" --since 10m --follow