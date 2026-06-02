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
import os
import sys
from datetime import datetime, timezone
from typing import Optional


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

    p_syn = sub.add_parser("syndicate", help="Emit per-platform social posts for a published edition")
    p_syn.add_argument("--date", required=True)
    p_syn.add_argument("--from", dest="source",
                       help="Edition JSON URL or path (default: the live content URL)")

    # --- autonomous approval backbone (openclaw + hermes run these) ---------
    p_val = sub.add_parser("validate", help="Deterministic 'technically valid' check on a draft")
    p_val.add_argument("--date", required=True)
    p_val.add_argument("--from", dest="source", help="Draft JSON URL or path (default: preview URL)")
    p_val.add_argument("--check-links", action="store_true",
                       help="Also HEAD every source_url (network; default off)")

    p_ver = sub.add_parser("verdict", help="Write this agent's verdict to S3 for the peer to see")
    p_ver.add_argument("--date", required=True)
    p_ver.add_argument("--agent", required=True, help="e.g. openclaw / hermes")
    p_ver.add_argument("--decision", required=True, choices=["approve", "hold"])
    p_ver.add_argument("--reason", action="append", default=[], help="repeatable")

    p_con = sub.add_parser("consensus", help="Read both verdicts; publish live on two-agent APPROVE")
    p_con.add_argument("--date", required=True)
    p_con.add_argument("--require", default="openclaw,hermes",
                       help="comma-separated agents that must APPROVE (default: openclaw,hermes)")
    p_con.add_argument("--publish", action="store_true",
                       help="On APPROVE, publish live (idempotent — skips if already live)")

    p_ann = sub.add_parser("announce", help="Write the generation status flag (decoupling marker)")
    p_ann.add_argument("--date", required=True)
    p_ann.add_argument("--state", required=True, choices=["generating", "complete", "failed"])
    p_ann.add_argument("--require", default="openclaw,hermes",
                       help="agents to request review from when state=complete")

    p_gate = sub.add_parser("gate", help="Idempotent publisher poll: publish when ready + consensus")
    p_gate.add_argument("--date", required=True)
    p_gate.add_argument("--require", default="openclaw,hermes")
    p_gate.add_argument("--publish", action="store_true",
                        help="Actually publish on APPROVE (else just report the decision)")

    p_df = sub.add_parser("deploy-frontend",
                          help="Sync the static frontend to S3 (diff-only) + invalidate the CDN")
    p_df.add_argument("--dir", dest="frontend_dir", help="frontend dir (default: repo frontend/)")

    return parser


def _frontend_dir() -> str:
    # content_pipeline/agent/cli.py → repo root → frontend/
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(repo, "frontend")


def cmd_run(args) -> int:
    # Imported here so `build_parser` (and its test) don't pull the agent stack.
    from content_pipeline.agent.editor_in_chief import run_edition

    date_iso = args.date or _today()
    logging.info("[cli] running edition for %s", date_iso)

    # Decoupling marker: tell the (independent) publisher a run is in flight, so a
    # poll that races generation sees `generating` and simply retries later.
    if getattr(args, "publish_draft", False):
        _announce_safe(date_iso, "generating")

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
        # Mark complete + drop the review-request the agents poll for.
        _announce_safe(date_iso, "complete")
    return 0


def _announce_safe(date_iso: str, state: str) -> None:
    """Write the status flag (+ review-request on complete). Never let a status
    write break generation — the publisher just retries if the flag is missing."""
    from content_pipeline.agent import review

    try:
        if state == "complete":
            ymd = "/".join(date_iso.split("-"))
            review.write_review_request(
                date_iso, agents=review.DEFAULT_AGENTS,
                draft_url=f"https://craicgpt.ie/preview/{ymd}/paper_content.json",
                at=_now_iso())
            review.write_status(date_iso, "complete", at=_now_iso(),
                                extra={"draft_key": f"preview/{ymd}/paper_content.json"})
        else:
            review.write_status(date_iso, state, at=_now_iso())
    except Exception as exc:  # noqa: BLE001
        logging.warning("[cli] status announce (%s) failed: %s", state, exc)


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


def _load_edition(date_iso: str, source: Optional[str], prefix: str = "content") -> dict:
    """Load an edition JSON from an explicit URL/path, or the default CDN URL."""
    y, m, d = date_iso.split("-")
    source = source or f"https://craicgpt.ie/{prefix}/{y}/{m}/{d}/paper_content.json"
    if source.startswith("http"):
        import httpx

        return httpx.get(source, timeout=20, follow_redirects=True).json()
    with open(source, encoding="utf-8") as fh:
        return json.load(fh)


def cmd_syndicate(args) -> int:
    from content_pipeline.social.syndicate import build_posts

    paper = _load_edition(args.date, args.source, prefix="content")
    print(json.dumps(build_posts(paper), indent=2, ensure_ascii=False))
    return 0


def cmd_validate(args) -> int:
    from content_pipeline.agent import review

    paper = _load_edition(args.date, args.source, prefix="preview")
    res = review.validate_paper(paper)
    if args.check_links:
        res["link_check"] = _check_links(paper)
        if not res["link_check"]["all_ok"]:
            res["valid"] = False
            res["reasons"].append(
                f"{len(res['link_check']['failed'])} source link(s) unreachable")
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0 if res["valid"] else 1


def _check_links(paper: dict) -> dict:
    """HEAD every source_url; return {all_ok, checked, failed:[url]}."""
    import httpx

    urls = []
    ai = paper.get("ai") or {}
    for it in [ai.get("headliner")] + (ai.get("subarticles") or []) + \
              (ai.get("shorts") or []) + (paper.get("fun") or []):
        u = (it or {}).get("source_url")
        if u:
            urls.append(u)
    failed = []
    with httpx.Client(timeout=15, follow_redirects=True) as c:
        for u in urls:
            try:
                r = c.head(u)
                if r.status_code >= 400:
                    r = c.get(u)  # some hosts reject HEAD
                if r.status_code >= 400:
                    failed.append(u)
            except Exception:  # noqa: BLE001
                failed.append(u)
    return {"all_ok": not failed, "checked": len(urls), "failed": failed}


def cmd_verdict(args) -> int:
    from content_pipeline.agent import review

    key = review.write_verdict(args.date, args.agent, args.decision,
                               args.reason or [], at=_now_iso())
    print(f"verdict written: {args.agent}={args.decision.upper()} → {key}")
    return 0


def _already_live(date_iso: str) -> bool:
    """True if content/<date>/paper_content.json already exists (idempotency)."""
    from content_pipeline.agent.publish import _default_s3, s3_key
    from content_pipeline.content_config import content_cfg

    try:
        _default_s3().head_object(Bucket=content_cfg.s3_bucket,
                                  Key=s3_key(date_iso, content_cfg.content_prefix))
        return True
    except Exception:  # noqa: BLE001 — NoSuchKey / 404 → not live yet
        return False


def cmd_consensus(args) -> int:
    from content_pipeline.agent import review

    required = tuple(a.strip() for a in args.require.split(",") if a.strip())
    verdicts = review.read_verdicts(args.date)
    result = review.compute_consensus(verdicts, required=required)
    result["voted"] = {a: review.verdict_of(verdicts[a]) or None for a in verdicts}

    if args.publish and result["decision"] == "APPROVE":
        if _already_live(args.date):
            result["published"] = "already-live"
        else:
            draft = f"/tmp/paper_content_{args.date}.json"
            rc = _publish_live(args.date, draft)
            result["published"] = rc == 0
    print(json.dumps(result, indent=2, ensure_ascii=False))
    # exit non-zero unless we have a clean APPROVE, so callers can branch on it
    return 0 if result["decision"] == "APPROVE" else 2


def _require(args) -> tuple:
    return tuple(a.strip() for a in args.require.split(",") if a.strip())


def cmd_announce(args) -> int:
    from content_pipeline.agent import review

    ymd = "/".join(args.date.split("-"))
    extra = None
    if args.state == "complete":
        draft_url = f"https://craicgpt.ie/preview/{ymd}/paper_content.json"
        review.write_review_request(args.date, agents=_require(args),
                                    draft_url=draft_url, at=_now_iso())
        extra = {"draft_key": f"preview/{ymd}/paper_content.json"}
    key = review.write_status(args.date, args.state, at=_now_iso(), extra=extra)
    print(f"status={args.state} → {key}")
    return 0


def cmd_gate(args) -> int:
    """The decoupled, idempotent publisher poll. Exit 0 published/already-live,
    2 hold, 3 retry-later (no content yet / awaiting a verdict)."""
    from content_pipeline.agent import review

    required = _require(args)
    status = review.read_status(args.date)
    verdicts = review.read_verdicts(args.date)

    # Host-side deterministic re-check before any publish (only worth fetching the
    # draft once content is marked complete). The agents own "harmless"; we own
    # "technically valid" — belt and braces against a bad draft slipping through.
    valid, invalid_reasons = True, []
    if status and status.get("state") == "complete" and not _already_live(args.date):
        try:
            vres = review.validate_paper(_load_edition(args.date, None, prefix="preview"))
            valid, invalid_reasons = vres["valid"], vres["reasons"]
        except Exception as exc:  # noqa: BLE001 — can't fetch draft → treat as not-yet-valid, retry
            valid, invalid_reasons = False, [f"could not fetch/validate draft: {exc}"]

    g = review.gate(args.date, verdicts=verdicts, status=status,
                    already_live=_already_live(args.date), valid=valid,
                    invalid_reasons=invalid_reasons, required=required)
    g["voted"] = {a: review.verdict_of(verdicts[a]) or None for a in verdicts}

    if args.publish and g["action"] == "publish":
        rc = _publish_live(args.date, f"/tmp/paper_content_{args.date}.json")
        g["published"] = rc == 0
        # Keep the deployed frontend in lockstep with the repo so the site can
        # never render a stale shell against fresh content. Diff-only; failure
        # here must not fail the content publish.
        if rc == 0:
            try:
                from content_pipeline.agent.frontend import sync_frontend

                g["frontend"] = sync_frontend(_frontend_dir())["uploaded"]
            except Exception as exc:  # noqa: BLE001
                logging.warning("[cli] frontend sync after publish failed: %s", exc)
                g["frontend_error"] = str(exc)
    print(json.dumps(g, indent=2, ensure_ascii=False))
    return {"already-live": 0, "publish": 0, "hold": 2, "retry": 3}.get(g["action"], 3)


def cmd_deploy_frontend(args) -> int:
    from content_pipeline.agent.frontend import sync_frontend

    d = args.frontend_dir or _frontend_dir()
    res = sync_frontend(d)
    n = len(res["uploaded"])
    print(f"frontend: {n} file(s) deployed{' + CDN invalidated' if n else ' (already current)'}")
    for k in res["uploaded"]:
        print(f"  ↑ {k}")
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "approve":
        return cmd_approve(args)
    if args.command == "publish":
        return cmd_publish(args)
    if args.command == "syndicate":
        return cmd_syndicate(args)
    if args.command == "validate":
        return cmd_validate(args)
    if args.command == "verdict":
        return cmd_verdict(args)
    if args.command == "consensus":
        return cmd_consensus(args)
    if args.command == "announce":
        return cmd_announce(args)
    if args.command == "gate":
        return cmd_gate(args)
    if args.command == "deploy-frontend":
        return cmd_deploy_frontend(args)
    print(f"unknown command {args.command!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
