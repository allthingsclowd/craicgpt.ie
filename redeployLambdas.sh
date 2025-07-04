#!/usr/bin/env zsh
set -euo pipefail

REGION="eu-west-1"

# list of "local_directory:function_name"
LAMBDA_PAIRS=(
  "lambda_code/imageGenHandler:craicgptie_image_runner"
  "lambda_code/llmHandler:craicgptie_llm_runner"
  "lambda_code/orchestrator:craicgptie-orchestrator"
  "lambda_code/PromptGenerator:craicgptie_prompt_generator"
)

echo "🔄 Packaging & deploying ${#LAMBDA_PAIRS[@]} functions …"

for pair in $LAMBDA_PAIRS; do
  DIR="${pair%%:*}"
  FUNC="${pair##*:}"
  ZIP="/tmp/${FUNC}.zip"

  echo "• $FUNC  ←  $DIR"
  ( cd "$DIR" && /usr/bin/zip -qr "$ZIP" . -x '*__pycache__/*' '*.DS_Store' )

  aws lambda update-function-code \
    --region "$REGION" \
    --function-name "$FUNC" \
    --zip-file "fileb://$ZIP" \
    --publish \
    | jq '{FunctionName, LastModified, Version}'
done

echo "✅  All functions updated and published."