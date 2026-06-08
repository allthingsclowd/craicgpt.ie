#!/usr/bin/env bash
# =============================================================================
# deploy-router.sh — Deploy the CraicGPT edge router (CloudFront Function) and
# attach it to the distribution, via the AWS CLI. IDEMPOTENT and re-runnable.
#
# WHY NOT TERRAFORM: terraform/frontend declares NO backend → local state, and
# that state is NOT in this checkout (the live stack was applied elsewhere). A
# `terraform apply` from here would try to RE-CREATE the live S3/CloudFront/ACM.
# So this change is enacted imperatively against the live distribution instead;
# terraform/frontend/modules/cloudfront/*.tf carries the equivalent change as
# clearly-labelled NOT-APPLIED documentation, to reconcile/import later.
#
# AUTH: needs CloudFront create-function / update-distribution — the put-only
# `craicgpt-publish` IAM CANNOT do this; use the admin account. Creds are pulled
# from 1Password inline (never printed), per skills/agentic-privileged-access:
#     export AWS_ACCESS_KEY_ID=$(op read "op://AgentCredentials/$AWS_ITEM/$AKID_FIELD")
#     export AWS_SECRET_ACCESS_KEY=$(op read "op://AgentCredentials/$AWS_ITEM/$SAK_FIELD")
# (Override AWS_ITEM/AKID_FIELD/SAK_FIELD to match the item's field labels.)
#
# USAGE:
#   ./deploy-router.sh                 # build + publish the function only (safe)
#   ./deploy-router.sh --attach        # ALSO attach it to the default behavior (writes prod)
#   DIST_ID=E... ./deploy-router.sh --attach
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FUNCTION_NAME="${FUNCTION_NAME:-craicgpt-router}"
DIST_ID="${DIST_ID:-${CLOUDFRONT_DISTRIBUTION_ID:-}}"
REGION="${AWS_REGION:-us-east-1}"   # CloudFront is a global (us-east-1) service
ATTACH=0; [ "${1:-}" = "--attach" ] && ATTACH=1

# 1Password item + field labels for the ADMIN creds (override to match your vault).
AWS_ITEM="${AWS_ITEM:-AWS Non Root Admin Account}"
AKID_FIELD="${AKID_FIELD:-access key id}"
SAK_FIELD="${SAK_FIELD:-secret access key}"

log() { echo "[router] $*"; }
die() { echo "[router] ERROR: $*" >&2; exit 1; }

# ── Auth (inline, never printed) ─────────────────────────────────────────────
if [ -z "${AWS_ACCESS_KEY_ID:-}" ]; then
  command -v op >/dev/null || die "1Password CLI 'op' not found and AWS_ACCESS_KEY_ID unset"
  log "fetching admin AWS creds from 1Password ($AWS_ITEM)…"
  AWS_ACCESS_KEY_ID="$(op read "op://AgentCredentials/${AWS_ITEM}/${AKID_FIELD}")" || die "op read access key failed"
  AWS_SECRET_ACCESS_KEY="$(op read "op://AgentCredentials/${AWS_ITEM}/${SAK_FIELD}")" || die "op read secret failed"
  export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
fi
aws sts get-caller-identity --query 'Arn' --output text >/dev/null || die "AWS auth failed"
log "authenticated: $(aws sts get-caller-identity --query 'Account' --output text)"

# ── 1) Create or update + publish the function ───────────────────────────────
CODE="$HERE/router.js"
[ -f "$CODE" ] || die "router.js not found at $CODE"

if aws cloudfront describe-function --name "$FUNCTION_NAME" >/dev/null 2>&1; then
  ETAG="$(aws cloudfront describe-function --name "$FUNCTION_NAME" --query 'ETag' --output text)"
  log "updating existing function $FUNCTION_NAME (ETag $ETAG)"
  ETAG="$(aws cloudfront update-function --name "$FUNCTION_NAME" --if-match "$ETAG" \
    --function-config Comment="CraicGPT language router",Runtime=cloudfront-js-2.0 \
    --function-code "fileb://$CODE" --query 'ETag' --output text)"
else
  log "creating function $FUNCTION_NAME"
  ETAG="$(aws cloudfront create-function --name "$FUNCTION_NAME" \
    --function-config Comment="CraicGPT language router",Runtime=cloudfront-js-2.0 \
    --function-code "fileb://$CODE" --query 'ETag' --output text)"
fi
aws cloudfront publish-function --name "$FUNCTION_NAME" --if-match "$ETAG" >/dev/null
FUNC_ARN="$(aws cloudfront describe-function --name "$FUNCTION_NAME" --query 'FunctionSummary.FunctionMetadata.FunctionARN' --output text)"
log "published. FunctionARN=$FUNC_ARN"

if [ "$ATTACH" -ne 1 ]; then
  log "function built + published. Re-run with --attach to wire it onto the distribution."
  log "NOTE: also ensure /static_assets/*, */content/*, /favicon.ico have their own cache"
  log "      behaviors WITHOUT this function (cost optimisation — router.js already"
  log "      passes those through, so it's safe either way)."
  exit 0
fi

# ── 2) Attach the function to the DEFAULT behavior (viewer-request) ──────────
[ -n "$DIST_ID" ] || die "--attach needs DIST_ID (or CLOUDFRONT_DISTRIBUTION_ID)"
log "reading distribution $DIST_ID config…"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
aws cloudfront get-distribution-config --id "$DIST_ID" > "$TMP/dist.json"
DETAG="$(jq -r '.ETag' "$TMP/dist.json")"

# Inject the viewer-request association on the DEFAULT behavior only (idempotent).
jq --arg arn "$FUNC_ARN" '
  .DistributionConfig
  | .DefaultCacheBehavior.FunctionAssociations =
      { "Quantity": 1, "Items": [ { "EventType": "viewer-request", "FunctionARN": $arn } ] }
' "$TMP/dist.json" > "$TMP/config.json"

log "DIFF (DefaultCacheBehavior.FunctionAssociations):"
jq -r '.FunctionAssociations' "$TMP/dist.json" 2>/dev/null | sed 's/^/  before: /' || true
jq -r '.DefaultCacheBehavior.FunctionAssociations' "$TMP/config.json" | sed 's/^/  after:  /'
read -r -p "[router] apply this update to LIVE distribution $DIST_ID? [y/N] " ok
[ "$ok" = "y" ] || { log "aborted — no change made"; exit 0; }

aws cloudfront update-distribution --id "$DIST_ID" --if-match "$DETAG" \
  --distribution-config "file://$TMP/config.json" --query 'Distribution.Status' --output text
log "attached. Allow a few minutes for the distribution to redeploy."
