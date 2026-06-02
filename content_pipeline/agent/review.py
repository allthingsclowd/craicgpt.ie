"""
content_pipeline/agent/review.py
================================
The autonomous-approval backbone the openclaw + hermes agents run each morning.

The skill ``approving-craicgpt-editions`` asks each agent to: validate the draft
(technically valid AND harmless), write its verdict so the peer can see it, and
publish only on two-agent consensus. This module makes the **deterministic** half
testable code:

* :func:`validate_paper` — schema/structure checks ("technically valid"). Pure,
  offline. The "harmless" judgement stays with the LLM agent.
* :func:`write_verdict` / :func:`read_verdicts` — the S3 verdict exchange.
* :func:`compute_consensus` — two-agent rule: any HOLD → HOLD; all required
  APPROVE → APPROVE; missing a verdict → WAIT (never publish on one say-so).

Counts are checked against the edition spec (1 headliner + 2 subarticles +
~10 shorts + ~5 fun) with a little tolerance so a *good* edition is never held
over an off-by-one — a missed day is cheap, a bad public edition is not, but a
falsely-held good one is a waste.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterable, Optional

from content_pipeline.agent.publish import s3_key
from content_pipeline.content_config import content_cfg

logger = logging.getLogger(__name__)

# Minimums — below these the edition is structurally broken, not just light.
MIN_SUBARTICLES = 2
MIN_SHORTS = 8
MIN_FUN = 4

DEFAULT_AGENTS = ("openclaw", "hermes")


def _is_http_url(u: Any) -> bool:
    return isinstance(u, str) and (u.startswith("http://") or u.startswith("https://"))


def _nonempty(item: dict, key: str) -> bool:
    v = item.get(key)
    return isinstance(v, str) and bool(v.strip())


def validate_paper(paper: dict[str, Any]) -> dict[str, Any]:
    """Deterministic 'technically valid' check. Returns
    ``{"valid": bool, "reasons": [str], "counts": {...}}`` — never raises."""
    reasons: list[str] = []
    ai = paper.get("ai") or {}
    headliner = ai.get("headliner") or {}
    subs = ai.get("subarticles") or []
    shorts = ai.get("shorts") or []
    fun = paper.get("fun") or []

    # Headliner — needs title, body, a real source link and an image.
    for key in ("title", "body"):
        if not _nonempty(headliner, key):
            reasons.append(f"headliner missing {key}")
    if not _is_http_url(headliner.get("source_url")):
        reasons.append("headliner missing a valid http source_url")
    if not _is_http_url(headliner.get("image_url")):
        reasons.append("headliner missing an image_url")

    # Counts.
    if len(subs) < MIN_SUBARTICLES:
        reasons.append(f"too few subarticles: {len(subs)} (need >= {MIN_SUBARTICLES})")
    if len(shorts) < MIN_SHORTS:
        reasons.append(f"too few AI shorts: {len(shorts)} (need >= {MIN_SHORTS})")
    if len(fun) < MIN_FUN:
        reasons.append(f"too few fun stories: {len(fun)} (need >= {MIN_FUN})")

    # Every AI text item needs title + body + a real source link.
    for label, items in (("subarticle", subs), ("short", shorts)):
        for i, it in enumerate(items):
            if not (_nonempty(it, "title") and _nonempty(it, "body")):
                reasons.append(f"{label} {i} missing title/body")
            if not _is_http_url(it.get("source_url")):
                reasons.append(f"{label} {i} missing a valid http source_url")

    # Every fun item: title/body, source link, image, AND the satire disclaimer.
    for i, it in enumerate(fun):
        if not (_nonempty(it, "title") and _nonempty(it, "body")):
            reasons.append(f"fun {i} missing title/body")
        if not _is_http_url(it.get("source_url")):
            reasons.append(f"fun {i} missing a valid http source_url")
        if not _is_http_url(it.get("image_url")):
            reasons.append(f"fun {i} missing an image_url")
        if not _nonempty(it, "satire_disclaimer"):
            reasons.append(f"fun {i} missing the satire disclaimer")

    return {
        "valid": not reasons,
        "reasons": reasons,
        "counts": {"subarticles": len(subs), "shorts": len(shorts), "fun": len(fun)},
    }


# --- verdict exchange -------------------------------------------------------
def verdict_key(date_iso: str, agent: str) -> str:
    return s3_key(date_iso, content_cfg.preview_prefix, f"verdict-{agent}.json")


def _default_s3():
    import boto3

    return boto3.client("s3", region_name=content_cfg.aws_region)


def write_verdict(date_iso: str, agent: str, verdict: str, reasons: Iterable[str],
                  *, s3: Any | None = None, bucket: Optional[str] = None,
                  at: Optional[str] = None) -> str:
    """Write ``verdict-<agent>.json`` to the preview prefix; return its key."""
    s3 = s3 or _default_s3()
    bucket = bucket or content_cfg.s3_bucket
    key = verdict_key(date_iso, agent)
    body = json.dumps(
        {"agent": agent, "verdict": verdict.upper(), "reasons": list(reasons), "at": at},
        ensure_ascii=False, indent=2,
    ).encode("utf-8")
    s3.put_object(Bucket=bucket, Key=key, Body=body,
                  ContentType="application/json", CacheControl="no-cache")
    logger.info("[review] verdict %s/%s → %s", agent, verdict.upper(), key)
    return key


def read_verdicts(date_iso: str, *, s3: Any | None = None,
                  bucket: Optional[str] = None) -> dict[str, dict]:
    """Read all ``verdict-*.json`` for the date → ``{agent: verdict_dict}``."""
    s3 = s3 or _default_s3()
    bucket = bucket or content_cfg.s3_bucket
    prefix = verdict_key(date_iso, "").rsplit("verdict-", 1)[0] + "verdict-"
    listing = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    out: dict[str, dict] = {}
    for obj in listing.get("Contents", []):
        key = obj["Key"]
        if not key.endswith(".json"):
            continue
        raw = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        data = json.loads(raw)
        out[data.get("agent") or key] = data
    return out


def compute_consensus(verdicts: dict[str, dict],
                      *, required: Iterable[str] = DEFAULT_AGENTS) -> dict[str, Any]:
    """Two-agent rule. Returns ``{"decision": APPROVE|HOLD|WAIT, "reasons": [...],
    "approvals": [...], "holds": [...]}``.

    * any agent HOLD → ``HOLD`` (surface its reasons)
    * a required agent has not voted yet → ``WAIT`` (never publish on one say-so)
    * all required agents APPROVE → ``APPROVE``
    """
    required = tuple(required)
    holds, approvals, reasons = [], [], []
    for agent, v in verdicts.items():
        decision = (v.get("verdict") or "").upper()
        if decision == "HOLD":
            holds.append(agent)
            reasons.extend(v.get("reasons") or [f"{agent} held"])
        elif decision == "APPROVE":
            approvals.append(agent)

    if holds:
        return {"decision": "HOLD", "reasons": reasons, "approvals": approvals, "holds": holds}
    missing = [a for a in required if a not in verdicts]
    if missing:
        return {"decision": "WAIT", "reasons": [f"awaiting verdict from: {', '.join(missing)}"],
                "approvals": approvals, "holds": holds}
    return {"decision": "APPROVE", "reasons": [], "approvals": approvals, "holds": holds}
