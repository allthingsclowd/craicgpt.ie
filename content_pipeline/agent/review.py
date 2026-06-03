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


def status_key(date_iso: str) -> str:
    return s3_key(date_iso, content_cfg.preview_prefix, "status.json")


def review_request_key(date_iso: str) -> str:
    return s3_key(date_iso, content_cfg.preview_prefix, "review-request.json")


def _get_json(s3, bucket, key) -> Optional[dict]:
    try:
        return json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
    except Exception:  # noqa: BLE001 — missing key / not-yet-written → None
        return None


def write_status(date_iso: str, state: str, *, s3: Any | None = None,
                 bucket: Optional[str] = None, at: Optional[str] = None,
                 extra: Optional[dict] = None) -> str:
    """Write the generation status flag (``generating`` | ``complete`` | ``failed``).

    The decoupled publisher polls this; nothing is physically chained."""
    s3 = s3 or _default_s3()
    bucket = bucket or content_cfg.s3_bucket
    obj = {"date": date_iso, "state": state, "at": at}
    if extra:
        obj.update(extra)
    s3.put_object(Bucket=bucket, Key=status_key(date_iso),
                  Body=json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8"),
                  ContentType="application/json", CacheControl="no-cache")
    logger.info("[review] status %s for %s", state, date_iso)
    return status_key(date_iso)


def read_status(date_iso: str, *, s3: Any | None = None,
                bucket: Optional[str] = None) -> Optional[dict]:
    s3 = s3 or _default_s3()
    return _get_json(s3, bucket or content_cfg.s3_bucket, status_key(date_iso))


def write_review_request(date_iso: str, *, agents: Iterable[str], draft_url: str,
                         s3: Any | None = None, bucket: Optional[str] = None,
                         at: Optional[str] = None) -> str:
    """Drop the marker the agents poll for: 'a draft is ready for your review'."""
    s3 = s3 or _default_s3()
    bucket = bucket or content_cfg.s3_bucket
    s3.put_object(Bucket=bucket, Key=review_request_key(date_iso),
                  Body=json.dumps({"date": date_iso, "draft_url": draft_url,
                                   "agents": list(agents), "requested_at": at},
                                  ensure_ascii=False, indent=2).encode("utf-8"),
                  ContentType="application/json", CacheControl="no-cache")
    logger.info("[review] review-request for %s → agents %s", date_iso, list(agents))
    return review_request_key(date_iso)


def read_review_request(date_iso: str, *, s3: Any | None = None,
                        bucket: Optional[str] = None) -> Optional[dict]:
    s3 = s3 or _default_s3()
    return _get_json(s3, bucket or content_cfg.s3_bucket, review_request_key(date_iso))


def gate(date_iso: str, *, verdicts: dict[str, dict], status: Optional[dict],
         already_live: bool, valid: bool = True, invalid_reasons: Optional[list] = None,
         required: Iterable[str] = DEFAULT_AGENTS,
         directive: Optional[dict] = None) -> dict[str, Any]:
    """Pure decision for the idempotent publisher poll. Returns
    ``{"action": ..., "decision": ..., "reasons": [...]}`` where action is one of:

    * ``"already-live"``      — content/<date> exists; nothing to do.
    * ``"retry"``             — no complete content yet, or awaiting a verdict.
    * ``"publish"``           — complete + two-agent APPROVE + host-valid → publish.
    * ``"hold"``              — an agent held, OR host-side validation failed; notify.
    * ``"override-publish"``  — a human directive force-publishes over a HOLD/WAIT.
    * ``"remediate-publish"`` — a human directive drops the flagged item(s), then
                                publishes (the host re-validates AFTER removal).

    ``valid`` is the host-side deterministic check (the agents own "harmless",
    the host owns "technically valid") — a draft the agents somehow approved but
    that fails structural validation is held, never published. A human
    ``directive`` (see :func:`read_directive`) overrides an agent HOLD/WAIT, but a
    force-publish still requires structural validity — you can override the
    "harmless" judgement, not ship a structurally broken page.
    """
    if already_live:
        return {"action": "already-live", "decision": "APPROVE", "reasons": []}
    if not status or status.get("state") != "complete":
        return {"action": "retry", "decision": "WAIT",
                "reasons": [f"content not ready (state={status.get('state') if status else None})"]}
    consensus = compute_consensus(verdicts, required=required)
    if consensus["decision"] == "APPROVE":
        if not valid:
            return {"action": "hold", "decision": "HOLD",
                    "reasons": ["host validation failed: " + r for r in (invalid_reasons or [])]}
        return {"action": "publish", "decision": "APPROVE", "reasons": []}

    # Consensus is HOLD or WAIT. A human directive (issued via the CLI on .75 or
    # written to S3 by an approval agent on Graham's say-so) overrides it.
    action = (directive or {}).get("action")
    if action == "force-publish":
        if not valid:
            return {"action": "hold", "decision": "HOLD",
                    "reasons": ["override blocked — structural validation failed: "
                                + r for r in (invalid_reasons or [])],
                    "directive": directive}
        return {"action": "override-publish", "decision": "OVERRIDE",
                "reasons": [f"human override by {directive.get('by') or 'operator'}"],
                "directive": directive}
    if action == "remove-and-publish":
        return {"action": "remediate-publish", "decision": "OVERRIDE",
                "reasons": [f"human remediation by {directive.get('by') or 'operator'}"],
                "drop": list(directive.get("drop") or []), "directive": directive}

    if consensus["decision"] == "HOLD":
        return {"action": "hold", "decision": "HOLD", "reasons": consensus["reasons"]}
    return {"action": "retry", "decision": "WAIT", "reasons": consensus["reasons"]}


# --- human-in-the-loop directive (override / remediate) ---------------------
DIRECTIVE_ACTIONS = ("force-publish", "remove-and-publish")


def directive_key(date_iso: str) -> str:
    return s3_key(date_iso, content_cfg.preview_prefix, "directive.json")


def write_directive(date_iso: str, action: str, *, drop: Optional[Iterable[str]] = None,
                    by: Optional[str] = None, reason: Optional[str] = None,
                    s3: Any | None = None, bucket: Optional[str] = None,
                    at: Optional[str] = None) -> str:
    """Write the human override directive the publish gate honours. ``action`` is
    ``force-publish`` (publish over the HOLD) or ``remove-and-publish`` (drop the
    items named in ``drop`` — matched on title — then publish)."""
    if action not in DIRECTIVE_ACTIONS:
        raise ValueError(f"action must be one of {DIRECTIVE_ACTIONS}, got {action!r}")
    s3 = s3 or _default_s3()
    bucket = bucket or content_cfg.s3_bucket
    body = {"date": date_iso, "action": action, "drop": list(drop or []),
            "by": by, "reason": reason, "at": at}
    s3.put_object(Bucket=bucket, Key=directive_key(date_iso),
                  Body=json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8"),
                  ContentType="application/json", CacheControl="no-cache")
    logger.info("[review] directive %s for %s (by %s)", action, date_iso, by)
    return directive_key(date_iso)


def read_directive(date_iso: str, *, s3: Any | None = None,
                   bucket: Optional[str] = None) -> Optional[dict]:
    s3 = s3 or _default_s3()
    return _get_json(s3, bucket or content_cfg.s3_bucket, directive_key(date_iso))


def clear_directive(date_iso: str, *, s3: Any | None = None,
                    bucket: Optional[str] = None) -> None:
    """Remove the directive (e.g. after it's been enacted, so it can't re-fire)."""
    s3 = s3 or _default_s3()
    try:
        s3.delete_object(Bucket=bucket or content_cfg.s3_bucket, Key=directive_key(date_iso))
    except Exception:  # noqa: BLE001 — already gone is fine
        pass


def _norm_title(s: Any) -> str:
    return " ".join(str(s or "").split()).casefold()


def remove_items(paper: dict, titles: Iterable[str]) -> tuple[dict, list[dict]]:
    """Drop list-section items (ai.shorts / ai.subarticles / fun) whose title
    matches any of ``titles`` (case-insensitive, whitespace-normalised substring).
    The single required headliner is never removed (that would break the edition;
    a held headliner is a regenerate, not a remediate). Returns
    ``(new_paper, dropped)`` where dropped is ``[{"section","title"}]``."""
    import copy

    wanted = [_norm_title(t) for t in titles if _norm_title(t)]
    paper = copy.deepcopy(paper)
    dropped: list[dict] = []

    def _filter(items, section):
        kept = []
        for it in items or []:
            title = (it or {}).get("title", "")
            if wanted and any(w in _norm_title(title) for w in wanted):
                dropped.append({"section": section, "title": title})
            else:
                kept.append(it)
        return kept

    ai = paper.get("ai") or {}
    if "shorts" in ai:
        ai["shorts"] = _filter(ai.get("shorts"), "ai.shorts")
    if "subarticles" in ai:
        ai["subarticles"] = _filter(ai.get("subarticles"), "ai.subarticles")
    paper["ai"] = ai
    if "fun" in paper:
        paper["fun"] = _filter(paper.get("fun"), "fun")
    return paper, dropped


def verdict_of(v: dict) -> str:
    """Extract a normalised verdict from an agent's file. LLM agents vary the
    schema (``verdict`` vs ``decision``, ``APPROVE`` vs ``approve``), so be
    tolerant on read — but anything we don't recognise is NOT an approval."""
    raw = v.get("verdict") or v.get("decision") or v.get("vote") or ""
    raw = str(raw).strip().upper()
    return raw if raw in ("APPROVE", "HOLD") else ""


def compute_consensus(verdicts: dict[str, dict],
                      *, required: Iterable[str] = DEFAULT_AGENTS) -> dict[str, Any]:
    """Two-agent rule. Returns ``{"decision": APPROVE|HOLD|WAIT, "reasons": [...],
    "approvals": [...], "holds": [...]}``.

    * any agent HOLD → ``HOLD`` (surface its reasons)
    * APPROVE only if **every required agent explicitly APPROVED** — a missing,
      unparseable, or null verdict counts as WAIT, never as an approval.
    """
    required = tuple(required)
    holds, approvals, reasons = [], [], []
    for agent, v in verdicts.items():
        decision = verdict_of(v)
        if decision == "HOLD":
            holds.append(agent)
            reasons.extend(v.get("reasons") or [f"{agent} held"])
        elif decision == "APPROVE":
            approvals.append(agent)

    if holds:
        return {"decision": "HOLD", "reasons": reasons, "approvals": approvals, "holds": holds}
    not_approved = [a for a in required if a not in approvals]
    if not_approved:
        return {"decision": "WAIT",
                "reasons": [f"awaiting explicit APPROVE from: {', '.join(not_approved)}"],
                "approvals": approvals, "holds": holds}
    return {"decision": "APPROVE", "reasons": [], "approvals": approvals, "holds": holds}
