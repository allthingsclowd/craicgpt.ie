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

from content_pipeline.content_config import content_cfg


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
    p_run.add_argument("--no-recency", action="store_true",
                       help="Operator override: regenerate IGNORING the recency de-dup "
                            "(do NOT exclude the last few editions' stories). Use to force "
                            "a fresh same-day version when the day's news pool is too thin "
                            "for the recency filter to leave enough sources.")

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
    p_ver.add_argument("--vid", help="edition version id (per-version verdict; optional)")

    p_con = sub.add_parser("consensus", help="Read both verdicts; publish live on two-agent APPROVE")
    p_con.add_argument("--date", required=True)
    p_con.add_argument("--require", default="rubric",
                       help="comma-separated agents that must APPROVE (default: openclaw,hermes)")
    p_con.add_argument("--publish", action="store_true",
                       help="On APPROVE, publish live (idempotent — skips if already live)")

    p_ann = sub.add_parser("announce", help="Write the generation status flag (decoupling marker)")
    p_ann.add_argument("--date", required=True)
    p_ann.add_argument("--state", required=True, choices=["generating", "complete", "failed"])
    p_ann.add_argument("--require", default="rubric",
                       help="agents to request review from when state=complete")

    p_gate = sub.add_parser("gate", help="Idempotent publisher poll: publish when ready + consensus")
    p_gate.add_argument("--date", required=True)
    p_gate.add_argument("--require", default="rubric")
    p_gate.add_argument("--publish", action="store_true",
                        help="Actually publish on APPROVE (else just report the decision)")

    # --- human-in-the-loop override / remediate (Graham via CLI or an agent) ---
    p_ovr = sub.add_parser("override",
                           help="Human override: publish the edition over the agents' HOLD")
    p_ovr.add_argument("--date", required=True)
    p_ovr.add_argument("--require", default="rubric")
    p_ovr.add_argument("--publish", action="store_true",
                       help="Enact now (else just write the directive for the gate to honour)")
    p_ovr.add_argument("--by", help="who issued the override, e.g. 'graham via openclaw'")
    p_ovr.add_argument("--reason", help="why the override")

    p_rem = sub.add_parser("remediate",
                           help="Human remediation: drop flagged article(s) by title, then publish")
    p_rem.add_argument("--date", required=True)
    p_rem.add_argument("--drop", action="append", default=[], required=True,
                       help="article title (case-insensitive substring) to drop; repeatable")
    p_rem.add_argument("--require", default="rubric")
    p_rem.add_argument("--publish", action="store_true", help="Enact now (else just write the directive)")
    p_rem.add_argument("--by", help="who issued the remediation")
    p_rem.add_argument("--reason", help="why the remediation")

    p_hold = sub.add_parser("hold",
                            help="Human HOLD: keep the edition held + SUPPRESS the passive-approval timeout")
    p_hold.add_argument("--date", required=True)
    p_hold.add_argument("--by", help="who issued the hold, e.g. 'graham via telegram'")
    p_hold.add_argument("--reason", help="why keep it held")

    p_dir = sub.add_parser("directive", help="Inspect or clear the pending human directive")
    p_dir.add_argument("--date", required=True)
    p_dir.add_argument("--clear", action="store_true", help="Remove the pending directive")

    p_df = sub.add_parser("deploy-frontend",
                          help="Sync the static frontend to S3 (diff-only) + invalidate the CDN")
    p_df.add_argument("--dir", dest="frontend_dir", help="frontend dir (default: repo frontend/)")

    p_msg = sub.add_parser("message",
                           help="Send a Telegram message to Graham via the agent bot(s)")
    p_msg.add_argument("--text", required=True, help="message body (HTML allowed)")
    p_msg.add_argument("--to", dest="which", default="both",
                       choices=["openclaw", "hermes", "both"],
                       help="which bot(s) to send via (default: both)")

    p_nar = sub.add_parser(
        "narrate",
        help="Generate per-article audio + the rubric-gated dad↔son podcast for an edition")
    p_nar.add_argument("--date", required=True)
    p_nar.add_argument("--source", help="explicit edition JSON path/URL (default: CDN by --prefix)")
    p_nar.add_argument("--prefix", default="preview", choices=["preview", "content"],
                       help="which prefix to load the edition from (default: preview)")
    p_nar.add_argument("--language", default=None,
                       help="narrate a translated edition under its <lang>/ prefix "
                            "(default: the source language at the root prefix)")
    p_nar.add_argument("--limit", type=int, default=None,
                       help="cap the number of articles narrated (for quick test runs)")
    p_nar.add_argument("--publish", action="store_true",
                       help="upload the audio + enriched edition JSON back to S3")
    p_nar.add_argument("--live", action="store_true",
                       help="with --publish, write to content/ (default: preview/)")
    p_nar.add_argument("--out", help="also write the enriched edition JSON to this local path")

    return parser


def _frontend_dir() -> str:
    # content_pipeline/agent/cli.py → repo root → frontend/
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(repo, "frontend")


def cmd_run(args) -> int:
    # Imported here so `build_parser` (and its test) don't pull the agent stack.
    from content_pipeline.agent.editor_in_chief import EditionHeld, run_edition
    from content_pipeline.agent.publish import _version_id

    date_iso = args.date or _today()
    # One generated_at for this run → its version id (vid), threaded through the whole
    # apply path (review-request, verdicts, notify markers) so multiple applies in one
    # day are each reviewed + announced + published as distinct versions.
    gen = _now_iso()
    vid = _version_id(gen)
    logging.info("[cli] running edition for %s (vid=%s)", date_iso, vid)

    # Decoupling marker: tell the (independent) publisher a run is in flight, so a
    # poll that races generation sees `generating` and simply retries later.
    if getattr(args, "publish_draft", False):
        _announce_safe(date_iso, "generating")

    # Integrity HOLD: if too few real, fresh, link-validated sources survived
    # (search degraded, everything was stale, or the agent gathered nothing),
    # run_edition raises EditionHeld — we publish NOTHING and alert loudly. Better a
    # held day than the 2026-06-04 fabricated one. status=failed keeps the gate from
    # ever publishing it (gate only publishes 'complete').
    # Operator override: `--no-recency` passes an empty exclude-set so run_edition
    # skips the last-few-editions de-dup (otherwise None → it excludes them). Lets a
    # forced same-day re-version publish when the day's fresh-source pool is depleted.
    recent_keys = set() if getattr(args, "no_recency", False) else None
    if recent_keys is not None:
        logging.warning("[cli] --no-recency: recency de-dup DISABLED for this run "
                        "(stories may overlap recent editions)")
    # When publishing a draft for review, grade the finished edition in-pipeline with
    # the rubric judge (a separate model); the verdict rides on the paper and is then
    # written to S3 so the gate can consense on it. A local `run` (no --publish-draft)
    # skips the live judge call.
    grade = None
    remediate = None
    if getattr(args, "publish_draft", False):
        from content_pipeline.agent.article_review import auto_remediate
        from content_pipeline.agent.rubric_review import grade_edition
        grade = grade_edition
        # Per-article gate: drop fabricated/dead-link articles + publish the valid
        # rest (a fabricated headliner promotes a valid story; unfixable → EditionHeld
        # HARD hold). Runs before grade + narration so both see the cleaned edition.
        remediate = auto_remediate
    try:
        paper = run_edition(date_iso, generated_at=gen, recent_keys=recent_keys,
                            grade=grade, remediate=remediate)
    except EditionHeld as held:
        reasons = held.reasons or ["edition held"]
        logging.error("[cli] edition %s HELD — nothing published: %s",
                      date_iso, "; ".join(reasons))
        if getattr(args, "publish_draft", False):
            _announce_safe(date_iso, "failed")
            _notify_safe("held", date_iso, reasons=reasons, vid=vid)
        print("edition HELD — not published:\n  " + "\n  ".join(reasons))
        return 2

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
        _announce_safe(date_iso, "complete", vid=vid)
        # Write the in-pipeline rubric verdict so the idempotent gate can publish on
        # it (replacing the two VMs' verdicts) — same S3 plumbing, a single "rubric".
        _write_rubric_verdict_safe(date_iso, paper, vid=vid)
        # Tell Graham (via both agents' channels) a draft is up for review.
        ymd = "/".join(date_iso.split("-"))
        _notify_safe("generated", date_iso, vid=vid,
                     draft_url=f"https://craicgpt.ie/preview/{ymd}/paper_content.json")

        # ── Multi-lingual: translate the published English preview into each other
        #    language and publish each as its OWN preview draft, sharing the English
        #    images (already absolute CDN URLs → publish skips re-uploading them). Each
        #    is staged locally so the narrate step + gate can promote it. Best-effort per
        #    language — a failure drops that language for the day; English still stands.
        from content_pipeline.agent import review as _review
        from content_pipeline.generate.translate import translate_paper

        for lang in content_cfg.languages:
            if lang == content_cfg.source_language:
                continue
            try:
                translated = translate_paper(preview, lang)   # preview carries abs English URLs
                vres = _review.validate_paper(translated)
                if not vres.get("valid"):
                    logging.warning("[cli] %s translation structurally invalid — skipped: %s",
                                    lang, vres.get("reasons"))
                    continue
                tkey = publish_paper(copy.deepcopy(translated), date_iso, live=False, language=lang)
                with open(_draft_path(date_iso, lang), "w", encoding="utf-8") as fh:
                    json.dump(translated, fh, indent=2, ensure_ascii=False)
                print(f"  translated draft [{lang}]: {tkey}")
            except Exception as exc:  # noqa: BLE001 — one language failing never holds the rest
                logging.warning("[cli] translation %s failed: %s", lang, exc)
    return 0


def _notify_safe(event: str, date_iso: str, **kw) -> None:
    """Fire an edition-lifecycle Telegram alert to both agents' channels. Like
    ``_announce_safe``, a notification must never break the pipeline."""
    try:
        from content_pipeline import notifications

        if event == "generated":
            notifications.notify_generated(date_iso, kw["draft_url"], vid=kw.get("vid"))
        elif event == "published":
            notifications.notify_published(
                date_iso, kw["live_url"], note=kw.get("note"),
                approvers=kw.get("approvers"), link_count=kw.get("link_count"),
                version=kw.get("version"), vid=kw.get("vid"))
        elif event == "held":
            notifications.notify_held(date_iso, kw.get("reasons") or [], vid=kw.get("vid"))
    except Exception as exc:  # noqa: BLE001
        logging.warning("[cli] notify %s failed: %s", event, exc)


def _announce_safe(date_iso: str, state: str, *, vid: Optional[str] = None) -> None:
    """Write the status flag (+ review-request on complete). Never let a status
    write break generation — the publisher just retries if the flag is missing.
    ``vid`` keys the review-request to this edition-version so the agents review it."""
    from content_pipeline.agent import review

    try:
        if state == "complete":
            ymd = "/".join(date_iso.split("-"))
            review.write_review_request(
                date_iso, agents=review.DEFAULT_AGENTS,
                draft_url=f"https://craicgpt.ie/preview/{ymd}/paper_content.json",
                vid=vid, at=_now_iso())
            review.write_status(date_iso, "complete", at=_now_iso(),
                                extra={"draft_key": f"preview/{ymd}/paper_content.json", "vid": vid})
        else:
            review.write_status(date_iso, state, at=_now_iso())
    except Exception as exc:  # noqa: BLE001
        logging.warning("[cli] status announce (%s) failed: %s", state, exc)


def _write_rubric_verdict_safe(date_iso: str, paper: dict, *, vid: Optional[str] = None) -> None:
    """Persist the in-pipeline rubric verdict to S3 as ``verdict-rubric.json``.

    The judge ran at generate time (``run_edition``) and stamped the verdict onto
    ``paper["edition"]["rubric"]``; we write it through the same verdict plumbing the
    gate reads, as a single ``rubric`` agent (replacing openclaw + hermes). Fail-soft:
    a missing/failed verdict just leaves the gate WAITing, never a crash."""
    from content_pipeline.agent import review

    verdict = (paper.get("edition") or {}).get("rubric") or {}
    decision = verdict.get("verdict")
    if not decision:
        logging.warning("[cli] no rubric verdict on the paper; gate will WAIT")
        return
    try:
        review.write_verdict(date_iso, "rubric", decision,
                             verdict.get("reasons", []), vid=vid, at=_now_iso())
        logging.info("[cli] rubric verdict %s written for %s (vid=%s)", decision, date_iso, vid)
    except Exception as exc:  # noqa: BLE001
        logging.warning("[cli] writing rubric verdict failed: %s", exc)


def _is_translation(language: Optional[str]) -> bool:
    """True for a real translation language (not the source, which stays at the root prefix
    — English content lives at content/ and /en/ is served as a CloudFront alias)."""
    return bool(language) and language != content_cfg.source_language


def _draft_path(date_iso: str, language: Optional[str] = None) -> str:
    suffix = f"_{language}" if _is_translation(language) else ""
    return f"/tmp/paper_content_{date_iso}{suffix}.json"


def _load_draft(date_iso: str, language: Optional[str] = None) -> dict:
    """The locally-staged draft (preferred — it keeps local image paths so publish
    can re-upload them) or, if absent, the published preview copy (for this language)."""
    path = _draft_path(date_iso, language)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return _load_edition(date_iso, None, prefix="preview", language=language)


def _publish_paper_live(date_iso: str, paper: dict, *, note: Optional[str] = None,
                        language: Optional[str] = None) -> int:
    from content_pipeline.agent.publish import publish_paper
    from content_pipeline.compile import mark_approved

    paper = mark_approved(paper, approver="cli", at=_now_iso())
    key = publish_paper(paper, date_iso, live=True, language=language)
    print(f"published live{f' ({note})' if note else ''}: s3://{paper.get('_bucket', '')} {key}")
    return 0


def _publish_live(date_iso: str, draft_path: str, *, language: Optional[str] = None) -> int:
    with open(draft_path, encoding="utf-8") as fh:
        paper = json.load(fh)
    return _publish_paper_live(date_iso, paper, language=language)


def _publish_translations_live(date_iso: str, *, retranslate_from: Optional[dict] = None) -> dict:
    """Promote each translation edition to its ``<lang>/content/`` tree on the SAME English
    verdict that authorised the source edition (translations are faithful, not re-judged).

    Normally each language's narrated preview draft is promoted as-is; for remediation
    (``retranslate_from`` set) the cleaned English edition is re-translated first, since
    dropping a story changes counts/layout. Best-effort + ISOLATED per language: a failure
    (or a language not generated today) is logged and skipped — it never affects the English
    publish or the other languages."""
    out: dict = {}
    for lang in content_cfg.languages:
        if lang == content_cfg.source_language:
            continue
        try:
            if retranslate_from is not None:
                from content_pipeline.generate.translate import translate_paper
                paper = translate_paper(retranslate_from, lang)
            else:
                paper = _load_draft(date_iso, lang)   # narrated local draft, else preview S3 copy
            rc = _publish_paper_live(date_iso, paper, language=lang, note=f"translation [{lang}]")
            out[lang] = "published" if rc == 0 else "failed"
        except Exception as exc:  # noqa: BLE001 — one language never sinks the English publish
            logging.warning("[cli] translation %s live publish skipped: %s", lang, exc)
            out[lang] = f"skipped: {exc}"
    return out


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


def _load_edition(date_iso: str, source: Optional[str], prefix: str = "content",
                  language: Optional[str] = None) -> dict:
    """Load an edition JSON from an explicit URL/path, or the default CDN URL.

    A translation language loads from its ``<lang>/<prefix>/…`` tree; the source language
    (English) loads from the root ``<prefix>/…`` (its content is not language-prefixed)."""
    y, m, d = date_iso.split("-")
    pfx = f"{language}/{prefix}" if _is_translation(language) else prefix
    source = source or f"https://craicgpt.ie/{pfx}/{y}/{m}/{d}/paper_content.json"
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


def cmd_narrate(args) -> int:
    """Narrate an edition: per-article audio + the rubric-gated dad↔son podcast.

    Loads the (validated) edition, enriches it with audio via the narration step, and —
    with ``--publish`` — uploads the audio + the audio-enriched JSON to S3 (``preview/``
    unless ``--live``). TTS runs on the M3; this verb runs on .75 or the M3, never the laptop.
    """
    from content_pipeline.generate.narration import narrate_paper

    prefix = getattr(args, "prefix", "preview") or "preview"
    language = getattr(args, "language", None)
    paper = _load_edition(args.date, args.source, prefix=prefix, language=language)
    paper = narrate_paper(paper, limit=getattr(args, "limit", None), language=language)

    ai = paper.get("ai") or {}
    arts = [ai.get("headliner"), *(ai.get("subarticles") or []),
            *(ai.get("shorts") or []), *(paper.get("fun") or [])]
    summary = {
        "date": args.date,
        "articles_narrated": sum(1 for a in arts if a and a.get("audio_url")),
        "podcast": bool(paper.get("podcast")),
        "podcast_tldr": bool(paper.get("podcast_tldr")),
    }
    if getattr(args, "out", None):
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(paper, fh, ensure_ascii=False, indent=2)
        summary["out"] = args.out
    if getattr(args, "publish", False):
        from content_pipeline.agent.publish import publish_paper
        live = getattr(args, "live", False)
        summary["published_key"] = publish_paper(paper, args.date, live=live, language=language)
        summary["live"] = live
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def _check_links(paper: dict, *, fetch=None) -> dict:
    """Validate EVERY source_url with the SAME browser-UA check generation uses.

    The gate used to HEAD each URL with httpx's default (bot) User-Agent — but real
    sources a reader's browser reaches fine (CNBC, OpenAI, VentureBeat, Microsoft's
    AI blog) answer that bot UA with 403/429, so editions whose links generation had
    ALREADY browser-validated were falsely HELD as "unreachable" (2026-06-04/05). And
    a bot UA can't tell a real OpenAI URL from an invented one — both 403; a browser
    UA returns 200 for the real one, 404 for the invented one. Reusing
    :func:`curation.validate_source_link` (fetches as a browser, treats any non-2xx /
    error as unreachable) makes the gate agree with generation: a generation-validated
    link can never be falsely held here, while an invented URL (browser 404) still
    fails. ``fetch`` is injectable for tests (a ``url -> status`` map). Returns
    ``{all_ok, checked, failed:[url]}``."""
    from content_pipeline.research.curation import validate_source_link

    ai = paper.get("ai") or {}
    items = [ai.get("headliner"), *(ai.get("subarticles") or []),
             *(ai.get("shorts") or []), *(paper.get("fun") or [])]
    urls = [u for it in items if (u := (it or {}).get("source_url"))]
    failed = [u for u in urls if not validate_source_link(u, fetch=fetch)]
    return {"all_ok": not failed, "checked": len(urls), "failed": failed}


def cmd_verdict(args) -> int:
    from content_pipeline.agent import review

    key = review.write_verdict(args.date, args.agent, args.decision,
                               args.reason or [], vid=getattr(args, "vid", None), at=_now_iso())
    print(f"verdict written: {args.agent}={args.decision.upper()} → {key}")
    return 0


def _edition_paper(date_iso: str, prefix: str) -> Optional[dict]:
    """The edition JSON currently at ``<prefix>/<date>``, or None if absent/unreadable."""
    from content_pipeline.agent.publish import _default_s3, s3_key
    from content_pipeline.content_config import content_cfg

    try:
        obj = _default_s3().get_object(Bucket=content_cfg.s3_bucket,
                                       Key=s3_key(date_iso, prefix))
        return json.loads(obj["Body"].read())
    except Exception:  # noqa: BLE001 — missing key / unreadable → None
        return None


def _narration_score(paper: dict) -> int:
    """How audio-enriched an edition is: narrated items + the podcast + the TL;DR.

    Used only for ORDERING (is the draft more narrated than what's live?), so a simple
    count is enough — narration never swaps one item's audio for another's."""
    ai = paper.get("ai") or {}
    items = [ai.get("headliner"), *(ai.get("subarticles") or []),
             *(ai.get("shorts") or []), *(paper.get("fun") or [])]
    n = sum(1 for it in items if (it or {}).get("audio_url"))
    return n + (1 if paper.get("podcast") else 0) + (1 if paper.get("podcast_tldr") else 0)


def _already_live(date_iso: str) -> bool:
    """True only if the LIVE edition is already the CURRENT draft — same
    ``generated_at`` AND at least as audio-enriched as the local draft.

    Content-aware idempotency: editions are versioned, so 'live' means 'this exact
    edition is the latest', not merely 'something exists at the key'. The gate
    therefore republishes (revs a new version) when the draft differs from what's
    live — including a STALE cross-date object left by an incident takedown — but
    will NOT re-mint a version on every poll of an unchanged edition.

    Narration-aware (2026-06-10): narrate enriches the LOCAL draft in place AFTER
    generation and does not touch ``generated_at``, so on a slow morning the gate's
    06:00 poll can promote the edition audio-less minutes before narrate finishes.
    Comparing ``generated_at`` alone then strands the finished audio on disk forever
    ("already-live" every subsequent poll). So when the timestamps match, also ask:
    did the local draft gain narration the live edition lacks? If yes → not live →
    the next poll re-promotes (same version id, audio included). Equal-or-less
    enrichment stays already-live, so a draft can never UN-publish live audio, and
    re-publishing an unchanged edition still mints no new version."""
    from content_pipeline.content_config import content_cfg

    live = _edition_paper(date_iso, content_cfg.content_prefix)
    if not live or not live.get("generated_at"):
        return False
    draft = _edition_paper(date_iso, content_cfg.preview_prefix)
    if not draft or not draft.get("generated_at"):
        return True  # nothing to compare against → treat live as authoritative
    if live["generated_at"] != draft["generated_at"]:
        return False
    # Same edition — but the gate publishes the LOCAL draft (narrate only enriches
    # the /tmp copy, never S3 preview), so that is what live must be compared with.
    try:
        local = _load_draft(date_iso)
    except Exception:  # noqa: BLE001 — no local/preview draft reachable → don't churn
        return True
    return _narration_score(local) <= _narration_score(live)


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


def _source_link_count(date_iso: str) -> Optional[int]:
    """How many source links the (now-published) edition carries — all of which the
    gate's mandatory link-check verified before publishing. Best-effort receipt."""
    try:
        paper = _load_draft(date_iso)
        ai = paper.get("ai") or {}
        items = [ai.get("headliner"), *(ai.get("subarticles") or []),
                 *(ai.get("shorts") or []), *(paper.get("fun") or [])]
        return sum(1 for it in items if (it or {}).get("source_url"))
    except Exception:  # noqa: BLE001
        return None


def _latest_version_label(date_iso: str) -> Optional[str]:
    """The newest version label from the live manifest (e.g. 'v2 · 17:30')."""
    from content_pipeline.agent.publish import _default_s3, s3_key
    from content_pipeline.content_config import content_cfg

    try:
        obj = _default_s3().get_object(
            Bucket=content_cfg.s3_bucket,
            Key=s3_key(date_iso, content_cfg.content_prefix, "versions.json"))
        versions = json.loads(obj["Body"].read()).get("versions") or []
        return versions[0].get("label") if versions else None
    except Exception:  # noqa: BLE001
        return None


def _after_publish(date_iso: str, *, note: Optional[str] = None,
                   approvers: Optional[list] = None, vid: Optional[str] = None) -> dict:
    """Post-publish side effects shared by every publish path: keep the deployed
    frontend in lockstep with the repo (so the site never renders a stale shell
    against fresh content) and fire the 'published' Telegram alert — now carrying
    the validation receipts (who approved, links verified, which version). Frontend
    sync failure must not fail the content publish."""
    out: dict = {}
    try:
        from content_pipeline.agent.frontend import sync_frontend
        from content_pipeline.agent.i18n_html import generate_localized_pages

        # Refresh the per-language HTML shells (frontend/<lang>/…) from the English
        # templates so the sync below ships them in lockstep with the content.
        generate_localized_pages(_frontend_dir())
        out["frontend"] = sync_frontend(_frontend_dir())["uploaded"]
    except Exception as exc:  # noqa: BLE001
        logging.warning("[cli] frontend sync after publish failed: %s", exc)
        out["frontend_error"] = str(exc)
    ymd = "/".join(date_iso.split("-"))
    _notify_safe("published", date_iso, vid=vid,
                 live_url=f"https://craicgpt.ie/content/{ymd}/paper_content.json", note=note,
                 approvers=approvers, link_count=_source_link_count(date_iso),
                 version=_latest_version_label(date_iso))
    return out


def _minutes_since(iso_ts: Optional[str]) -> Optional[float]:
    """Minutes elapsed since an ISO8601 timestamp (UTC-aware), or None if unparseable."""
    if not iso_ts:
        return None
    from datetime import datetime, timezone
    try:
        t = datetime.fromisoformat(str(iso_ts).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds() / 60.0
    except Exception:  # noqa: BLE001 — a garbled timestamp just disables the timer
        return None


def _stamp_held_since(date_iso: str, status: Optional[dict]) -> None:
    """Anchor the HITL passive-approval clock on the first valid judgement hold,
    preserving the rest of the status object."""
    from content_pipeline.agent import review
    try:
        st = status or {}
        extra = {k: v for k, v in st.items() if k not in ("date", "state", "at")}
        extra["held_since"] = _now_iso()
        review.write_status(date_iso, st.get("state", "complete"), at=st.get("at"), extra=extra)
    except Exception as exc:  # noqa: BLE001 — never let the clock-stamp break the poll
        logging.warning("[cli] stamping held_since failed: %s", exc)


def _run_gate(date_iso: str, required: tuple, *, publish: bool) -> dict:
    """The decoupled, idempotent publisher decision + enactment. Reads status,
    verdicts and any human directive; computes the host-side structural check;
    decides via :func:`review.gate`; and (when ``publish``) enacts publish /
    override / remediate / hold, firing the matching Telegram alert. Returns the
    decision dict (with ``published`` / ``dropped`` annotations)."""
    from content_pipeline.agent import review
    from content_pipeline.agent.publish import _version_id
    from content_pipeline.content_config import content_cfg

    # The version under consideration = the current preview draft's generated_at.
    # Read THIS version's verdicts (so the gate consenses on what it will actually
    # publish, not a stale earlier version) and key the alerts to it.
    draft_gen = (_edition_paper(date_iso, content_cfg.preview_prefix) or {}).get("generated_at")
    vid = _version_id(draft_gen) if draft_gen else None

    status = review.read_status(date_iso)
    verdicts = review.read_verdicts(date_iso, vid=vid)
    directive = review.read_directive(date_iso)

    # HITL passive-approval clock: how long has this version been held, and after how
    # many minutes do we passively approve absent a human directive? (0 → disabled.)
    passive_after = content_cfg.hitl_passive_minutes or None
    held_since = (status or {}).get("held_since")
    held_minutes = _minutes_since(held_since)

    # Host-side deterministic re-check before any publish (only worth fetching the
    # draft once content is marked complete). The agents own "harmless"; we own
    # "technically valid" — belt and braces against a bad draft slipping through.
    valid, invalid_reasons = True, []
    if status and status.get("state") == "complete" and not _already_live(date_iso):
        try:
            valid, invalid_reasons = _host_validate(date_iso)
        except Exception as exc:  # noqa: BLE001 — can't fetch draft → not-yet-valid, retry
            valid, invalid_reasons = False, [f"could not fetch/validate draft: {exc}"]

    g = review.gate(date_iso, verdicts=verdicts, status=status,
                    already_live=_already_live(date_iso), valid=valid,
                    invalid_reasons=invalid_reasons, required=required, directive=directive,
                    held_minutes=held_minutes, passive_after_minutes=passive_after)
    g["voted"] = {a: review.verdict_of(verdicts[a]) or None for a in verdicts}
    if not publish:
        return g

    by = (directive or {}).get("by") or "operator"
    if g["action"] in ("publish", "override-publish", "passive-publish"):
        note = None
        if g["action"] == "override-publish":
            note = f"override by {by}"
        elif g["action"] == "passive-publish":
            note = f"passive-approval — no human response within {int(passive_after)} min"
        rc = _publish_live(date_iso, _draft_path(date_iso))
        g["published"] = rc == 0
        if rc == 0:
            approvers = [a for a, v in (g.get("voted") or {}).items() if v == "APPROVE"]
            g.update(_after_publish(date_iso, note=note, approvers=approvers, vid=vid))
            # Promote the translations on the same English verdict (additive, isolated).
            g["languages"] = _publish_translations_live(date_iso)
    elif g["action"] == "remediate-publish":
        g.update(_remediate_and_publish(date_iso, g.get("drop") or [], by=by))
    elif g["action"] == "hold":
        # Surface the HOLD (once per version). On the FIRST structurally-valid judgement
        # hold, START the HITL clock and tell Graham he has a window to respond before it
        # passively auto-publishes. A structural/link failure (valid=False) is a HARD
        # hold — no clock, no passive-approval.
        reasons = list(g.get("reasons") or [])
        first_valid_hold = bool(valid and passive_after and not held_since)
        if first_valid_hold:
            reasons.append(f"auto-publishes in {int(passive_after)} min unless you respond "
                           "— `cli override` to publish now, or `cli hold` to keep it held")
        _notify_safe("held", date_iso, reasons=reasons, vid=vid)
        if first_valid_hold:
            _stamp_held_since(date_iso, status)
    return g


def _validate_with_links(paper: dict) -> tuple:
    """Host-side 'safe to publish?' check: structural validation AND a live
    link-check of EVERY source_url. Any unreachable link ⇒ invalid.

    This is the single gate the publisher trusts — link-checking is MANDATORY here,
    never opt-in, because the 2026-06-04 fabricated-URL edition slipped through a
    publish path that skipped it. Returns ``(valid, reasons)``."""
    from content_pipeline.agent import review

    vres = review.validate_paper(paper)
    valid = bool(vres["valid"])
    reasons = list(vres["reasons"])
    link = _check_links(paper)
    if not link["all_ok"]:
        valid = False
        shown = ", ".join(link["failed"][:5]) + ("…" if len(link["failed"]) > 5 else "")
        reasons.append(f"{len(link['failed'])} of {link['checked']} source link(s) "
                       f"unreachable: {shown}")
    return valid, reasons


def _host_validate(date_iso: str) -> tuple:
    return _validate_with_links(_load_edition(date_iso, None, prefix="preview"))


def _remediate_and_publish(date_iso: str, drop: list, *, by: str) -> dict:
    """Drop the flagged item(s), re-validate the cleaned edition structurally, then
    republish it to preview/ AND publish live. If removal leaves a structurally
    invalid edition, hold instead (and say so)."""
    from content_pipeline.agent import review
    from content_pipeline.agent.publish import publish_paper

    out: dict = {}
    paper = _load_draft(date_iso)
    cleaned, dropped = review.remove_items(paper, drop)
    out["dropped"] = dropped
    valid, vreasons = _validate_with_links(cleaned)
    if not valid:
        out["action"] = "hold"
        out["published"] = False
        reasons = ["remediation left the edition unsafe to publish: " + r
                   for r in vreasons]
        out["reasons"] = reasons
        _notify_safe("held", date_iso, reasons=reasons)
        return out

    # Persist the cleaned edition: refresh the local draft + the preview copy so
    # what goes live and what's in preview match, then publish live.
    with open(_draft_path(date_iso), "w", encoding="utf-8") as fh:
        json.dump(cleaned, fh, indent=2, ensure_ascii=False)
    import copy

    publish_paper(copy.deepcopy(cleaned), date_iso, live=False)
    rc = _publish_paper_live(date_iso, cleaned, note=f"remediated by {by}")
    out["published"] = rc == 0
    if rc == 0:
        note = f"remediated by {by}: dropped {len(dropped)} item(s)"
        out.update(_after_publish(date_iso, note=note))
        # Re-translate the CLEANED edition (counts/layout changed) and promote each language.
        out["languages"] = _publish_translations_live(date_iso, retranslate_from=cleaned)
    return out


def cmd_gate(args) -> int:
    """The decoupled, idempotent publisher poll. Exit 0 published/already-live,
    2 hold, 3 retry-later (no content yet / awaiting a verdict)."""
    g = _run_gate(args.date, _require(args), publish=args.publish)
    print(json.dumps(g, indent=2, ensure_ascii=False))
    return {"already-live": 0, "publish": 0, "override-publish": 0,
            "remediate-publish": 0, "hold": 2, "retry": 3}.get(g["action"], 3)


def cmd_override(args) -> int:
    """Human override: publish the edition over the agents' HOLD. Writes the
    directive (so an out-of-band gate poll will also honour it) and, with
    --publish, enacts it now."""
    from content_pipeline.agent import review

    key = review.write_directive(args.date, "force-publish", by=args.by,
                                 reason=args.reason, at=_now_iso())
    print(f"directive written: force-publish {args.date} → {key}")
    if not args.publish:
        return 0
    g = _run_gate(args.date, _require(args), publish=True)
    print(json.dumps(g, indent=2, ensure_ascii=False))
    return {"already-live": 0, "override-publish": 0, "publish": 0,
            "hold": 2, "retry": 3}.get(g["action"], 3)


def cmd_remediate(args) -> int:
    """Human remediation: drop the flagged article(s) (matched on title) and
    publish the cleaned edition. Writes the directive and, with --publish, enacts."""
    from content_pipeline.agent import review

    key = review.write_directive(args.date, "remove-and-publish", drop=args.drop,
                                 by=args.by, reason=args.reason, at=_now_iso())
    print(f"directive written: remove-and-publish {args.date} drop={args.drop} → {key}")
    if not args.publish:
        return 0
    g = _run_gate(args.date, _require(args), publish=True)
    print(json.dumps(g, indent=2, ensure_ascii=False))
    return {"already-live": 0, "remediate-publish": 0, "publish": 0,
            "hold": 2, "retry": 3}.get(g["action"], 3)


def cmd_hold(args) -> int:
    """Human HOLD: pin the edition held and SUPPRESS the passive-approval timeout.
    Writes a 'hold' directive the gate honours; it will not auto-publish until you
    clear it (`cli directive --clear`) or override (`cli override`)."""
    from content_pipeline.agent import review

    key = review.write_directive(args.date, "hold", by=args.by, reason=args.reason, at=_now_iso())
    print(f"directive written: hold {args.date} → {key}")
    return 0


def cmd_directive(args) -> int:
    """Inspect or clear the pending human directive for a date."""
    from content_pipeline.agent import review

    if args.clear:
        review.clear_directive(args.date, at=_now_iso())
        print(f"directive cleared for {args.date}")
        return 0
    d = review.read_directive(args.date)
    print(json.dumps(d, indent=2, ensure_ascii=False) if d else "(no directive)")
    return 0


def cmd_message(args) -> int:
    """Send an ad-hoc Telegram message to Graham via the agent bot(s). This is the
    host-side sender the `messaging-graham` skill routes through (the .75 host holds
    both bot tokens; agent VMs hold only their own)."""
    from content_pipeline import notifications

    results = notifications.send_message(args.text, which=args.which)
    delivered = sum(1 for r in results if r["ok"])
    print(json.dumps({"to": args.which, "delivered": delivered,
                      "results": results}, ensure_ascii=False))
    # exit non-zero only if a channel was configured but NONE delivered
    return 0 if (delivered or not results) else 1


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
    if args.command == "narrate":
        return cmd_narrate(args)
    if args.command == "verdict":
        return cmd_verdict(args)
    if args.command == "consensus":
        return cmd_consensus(args)
    if args.command == "announce":
        return cmd_announce(args)
    if args.command == "gate":
        return cmd_gate(args)
    if args.command == "override":
        return cmd_override(args)
    if args.command == "remediate":
        return cmd_remediate(args)
    if args.command == "hold":
        return cmd_hold(args)
    if args.command == "directive":
        return cmd_directive(args)
    if args.command == "message":
        return cmd_message(args)
    if args.command == "deploy-frontend":
        return cmd_deploy_frontend(args)
    print(f"unknown command {args.command!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
