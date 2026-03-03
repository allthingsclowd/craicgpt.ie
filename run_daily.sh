#!/usr/bin/env bash
# =============================================================================
# run_daily.sh — CraicGPT daily newspaper generation script
#
# Usage:
#   ./run_daily.sh                      # generate today's edition
#   ./run_daily.sh --dry-run            # test run, writes to /tmp not S3
#   ./run_daily.sh --skip-local         # skip LM Studio (if not running)
#   ./run_daily.sh --date 2026-03-03    # generate a specific date
#   ./run_daily.sh --dry-run --verbose  # full debug output, no upload
#
# All arguments are passed straight through to content_pipeline/main.py.
#
# Schedule with macOS cron (runs at 08:00 every morning):
#   crontab -e
#   0 8 * * * /Users/graz/repos/craicgpt.ie/run_daily.sh >> /tmp/craicgpt.log 2>&1
# =============================================================================

set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
ENV_FILE="$SCRIPT_DIR/.env"
REQUIREMENTS="$SCRIPT_DIR/content_pipeline/requirements.txt"

# ── Colour output (safe — disabled if not a terminal) ────────────────────────

if [ -t 1 ]; then
  GREEN="\033[0;32m"; YELLOW="\033[0;33m"; RED="\033[0;31m"; RESET="\033[0m"
else
  GREEN=""; YELLOW=""; RED=""; RESET=""
fi

info()    { echo -e "${GREEN}[craicgpt]${RESET} $*"; }
warning() { echo -e "${YELLOW}[craicgpt]${RESET} $*"; }
error()   { echo -e "${RED}[craicgpt]${RESET} $*" >&2; }

# ── Load environment variables from .env ─────────────────────────────────────

if [ ! -f "$ENV_FILE" ]; then
  error ".env file not found at $ENV_FILE"
  error "Copy .env.example to .env and fill in your credentials."
  exit 1
fi

info "Loading environment from $ENV_FILE"
# Export each non-comment, non-empty line from .env
set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

# ── Sanity-check required variables ──────────────────────────────────────────

MISSING=()
[ -z "${ANTHROPIC_API_KEY:-}" ] && MISSING+=("ANTHROPIC_API_KEY")
[ -z "${GOOGLE_API_KEY:-}"    ] && MISSING+=("GOOGLE_API_KEY")
[ -z "${AWS_ACCESS_KEY_ID:-}" ] && MISSING+=("AWS_ACCESS_KEY_ID")
[ -z "${S3_BUCKET:-}"         ] && MISSING+=("S3_BUCKET")

if [ ${#MISSING[@]} -gt 0 ]; then
  error "Missing required variables in .env: ${MISSING[*]}"
  exit 1
fi

# ── Python virtual environment ───────────────────────────────────────────────

if [ ! -d "$VENV_DIR" ]; then
  info "Creating Python virtual environment at $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

info "Activating virtual environment"
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

# ── Install / upgrade dependencies ───────────────────────────────────────────

info "Checking dependencies (pip install -q -r requirements.txt)"
pip install -q --upgrade pip
pip install -q -r "$REQUIREMENTS"

# ── Run the pipeline ─────────────────────────────────────────────────────────

info "Starting pipeline (args: ${*:-none})"
echo ""

cd "$SCRIPT_DIR"
PYTHONPATH="$SCRIPT_DIR" python content_pipeline/main.py "$@"

EXIT_CODE=$?
echo ""

if [ $EXIT_CODE -eq 0 ]; then
  info "Pipeline finished successfully."
else
  error "Pipeline exited with code $EXIT_CODE."
fi

exit $EXIT_CODE
