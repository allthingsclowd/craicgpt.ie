"""
content_pipeline/main.py
=========================
CLI entry point for the CraicGPT newspaper generation pipeline.

TUTORIAL: Command-Line Interface Design
-----------------------------------------
This file is intentionally thin — it handles argument parsing and logging setup,
then delegates everything to the orchestrator. The pipeline logic lives in agents/,
chains/, and publishers/ so it's testable independently of the CLI.

Usage:
    # Generate today's newspaper
    python content_pipeline/main.py

    # Generate for a specific date
    python content_pipeline/main.py --date 2026-03-03

    # Dry run — generate but don't upload to S3 (writes to /tmp instead)
    python content_pipeline/main.py --dry-run

    # Skip local LLM (if LM Studio isn't running)
    python content_pipeline/main.py --skip-local

    # Show the LangGraph pipeline structure as a Mermaid diagram
    python content_pipeline/main.py --show-graph

From GitHub Actions, the workflow calls:
    python content_pipeline/main.py ${{ inputs.date }}

The optional positional argument allows the workflow_dispatch input to be
passed directly without needing --date syntax.
"""

import argparse
import logging
import os
import sys
from datetime import date, datetime


def _setup_logging(verbose: bool = False) -> None:
    """Configure logging with a clear format for CI output."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    # Quieten noisy third-party loggers.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CraicGPT — AI newspaper generation pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python content_pipeline/main.py                    # today
  python content_pipeline/main.py 2026-03-03         # specific date
  python content_pipeline/main.py --dry-run          # no S3 upload
  python content_pipeline/main.py --show-graph       # print pipeline diagram
        """,
    )
    parser.add_argument(
        "date",
        nargs="?",
        help="Date to generate (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--date",
        dest="date_flag",
        help="Alternative --date flag (same as positional).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate content but write to /tmp instead of uploading to S3.",
    )
    parser.add_argument(
        "--skip-local",
        action="store_true",
        help="Skip the local LM Studio provider (use if LM Studio isn't running).",
    )
    parser.add_argument(
        "--show-graph",
        action="store_true",
        help="Print the LangGraph pipeline structure as a Mermaid diagram and exit.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG level logging.",
    )
    return parser.parse_args()


def _resolve_date(args: argparse.Namespace) -> date:
    """Parse the target date from CLI args, defaulting to today."""
    raw = args.date or args.date_flag
    if not raw:
        return date.today()
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        print(f"ERROR: Invalid date format '{raw}'. Expected YYYY-MM-DD.", file=sys.stderr)
        sys.exit(1)


def _show_pipeline_graph() -> None:
    """Print the LangGraph pipeline as a Mermaid diagram."""
    from content_pipeline.agents.orchestrator import build_pipeline
    graph = build_pipeline()
    print("\n=== CraicGPT Pipeline (Mermaid) ===\n")
    print(graph.get_graph().draw_mermaid())
    print("\nPaste the above into https://mermaid.live to visualise it.\n")


def main() -> int:
    args = _parse_args()
    _setup_logging(verbose=args.verbose)
    log = logging.getLogger("main")

    # --show-graph is a standalone informational command.
    if args.show_graph:
        _show_pipeline_graph()
        return 0

    # Apply CLI flags to environment (config.py reads from env vars).
    if args.dry_run:
        os.environ["DRY_RUN"] = "true"
    if args.skip_local:
        os.environ["SKIP_LOCAL_LLM"] = "true"

    target_date = _resolve_date(args)
    log.info(f"CraicGPT pipeline starting for {target_date.isoformat()}")

    # Import here (after env vars are set) so config.py picks up CLI flags.
    from content_pipeline.agents.orchestrator import run_pipeline

    final_state = run_pipeline(target_date=target_date)

    if final_state.get("published") or (args.dry_run and final_state.get("paper_content")):
        log.info("Pipeline completed successfully.")
        if args.dry_run:
            log.info(f"Dry run output: {final_state.get('s3_key', '/tmp/paper_content.json')}")
        return 0
    else:
        errors = final_state.get("errors", [])
        log.error(f"Pipeline failed. Errors: {errors}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
