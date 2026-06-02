"""
content_pipeline/agent/cli.py
=============================
CLI for the deep-agent content engine.

    python -m content_pipeline.agent.cli run [--date YYYY-MM-DD] [--dry-run] [--out PATH]
    python -m content_pipeline.agent.cli approve --date YYYY-MM-DD [--reject]
    python -m content_pipeline.agent.cli publish --date YYYY-MM-DD --draft PATH

`run` executes the Editor-in-Chief deep agent and writes a draft edition. The
draft is held for human approval (LangGraph interrupt gate) before `publish`
pushes it live. This is what the thin Conductor trigger on host .75 invokes.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser (separated out so it's unit-testable)."""
    parser = argparse.ArgumentParser(prog="craicgpt-content",
                                     description="CraicGPT deep-agent content engine")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run the deep agent and write a draft edition")
    p_run.add_argument("--date", help="Edition date YYYY-MM-DD (default: today UTC)")
    p_run.add_argument("--dry-run", action="store_true",
                       help="Write the draft to /tmp instead of the configured location")
    p_run.add_argument("--out", help="Explicit output path for the draft JSON")
    p_run.add_argument("--publish-draft", action="store_true",
                       help="Also upload the draft (+ images) to the S3 preview/ prefix "
                            "for review (this is what the daily Conductor run does)")

    p_app = sub.add_parser("approve", help="Approve (or reject) a held draft edition")
    p_app.add_argument("--date", required=True)
    p_app.add_argument("--reject", action="store_true", help="Reject instead of approve")

    p_pub = sub.add_parser("publish", help="Publish an approved edition live")
    p_pub.add_argument("--date", required=True)
    p_pub.add_argument("--draft", required=True, help="Path to the approved draft JSON")

    return parser


def cmd_run(args) -> int:
    # Imported here so `build_parser` (and its test) don't pull the agent stack.
    from content_pipeline.agent.editor_in_chief import run_edition

    date_iso = args.date or _today()
    logging.info("[cli] running edition for %s", date_iso)
    paper = run_edition(date_iso, generated_at=_now_iso())

    # The local copy keeps LOCAL image paths so a later `approve` can re-publish
    # the images to the live content/ prefix.
    out = args.out or f"/tmp/paper_content_{date_iso}.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(paper, fh, indent=2, ensure_ascii=False)
    print(f"draft written: {out}")
    print(f"  AI: 1 headliner + {len(paper['ai']['subarticles'])} subs + "
          f"{len(paper['ai']['shorts'])} shorts | fun: {len(paper['fun'])}")

    if getattr(args, "publish_draft", False):
        import copy

        from content_pipeline.agent.publish import publish_paper

        preview = copy.deepcopy(paper)  # don't mutate the local copy's image paths
        key = publish_paper(preview, date_iso, live=False)
        print(f"draft published to preview: {key}")
    return 0


def _publish_live(date_iso: str, draft_path: str) -> int:
    from content_pipeline.agent.publish import publish_paper
    from content_pipeline.compile import mark_approved

    with open(draft_path, encoding="utf-8") as fh:
        paper = json.load(fh)
    paper = mark_approved(paper, approver="cli", at=_now_iso())
    key = publish_paper(paper, date_iso, live=True)
    print(f"published live: s3://{paper.get('_bucket', '')} {key}")
    return 0


def cmd_approve(args) -> int:
    if args.reject:
        print(f"edition {args.date} rejected — nothing published")
        return 0
    # The draft staged in preview/ IS the durable pause; approval republishes live.
    draft = f"/tmp/paper_content_{args.date}.json"
    print(f"approving {args.date} from {draft}")
    return _publish_live(args.date, draft)


def cmd_publish(args) -> int:
    return _publish_live(args.date, args.draft)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "approve":
        return cmd_approve(args)
    if args.command == "publish":
        return cmd_publish(args)
    print(f"unknown command {args.command!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
