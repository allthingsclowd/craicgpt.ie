"""
content_pipeline/notifications.py
=================================
Operator notifications for the daily edition lifecycle — as **ops events**, not Telegram.

The .75 engine is the **single, deterministic** source of these alerts — it is the
place that knows when a draft has been generated and, via the publish gate, when an
edition goes live or is held. Since fleet #206 item 5 it no longer messages Graham
directly. It describes what happened as a ``grazlab.ops.event/1`` and hands it to the
fleet's ``ops_event`` Conductor workflow (the lane ``message_graham`` already used);
the policy there — map #185 decision 4 — decides who hears about it, and when:

* an **immediate page** on the ONE ops bot (``@GrazLabWatch_bot``) only for a site that
  did not publish, a service that is down, or a **decision that is needed**;
* everything else lands in the **08:00 digest**.

The bucket per lifecycle event (from the #187 sender inventory):

======================  ========  ===============  ==================================
event                   severity  kind             dedup_key
======================  ========  ===============  ==================================
generated               —         DROPPED          (no event, no send — latest.json
                                                   and status.json carry it)
published               info      published        craicgpt:published:<date>:<vid>
fun_no_comedy           warn      degraded         craicgpt:degraded:fun_no_comedy:…
translation_degraded    warn      degraded         craicgpt:degraded:translations:…
qc_flagged              warn      flagged          craicgpt:flagged:qc:<date>:<vid>
held                    page      decision_needed  craicgpt:decision_needed:held:…
======================  ========  ===============  ==================================

``held`` is the one thing that asks Graham for something within a deadline, so it is
the one event that may still reach Telegram from here — and only as a **fallback**:
when the ``ops_event`` lane owns the page — it paged, it suppressed a repeat of a key
that already paged, or a worker is mid-send when the wait runs out — nothing more is
sent (a second message would be the double-send #187 measured); when the lane is down,
rejected the event, stored it but could not deliver, or no worker picked it up, ONE
message goes out on ONE bot.

Three design rules:

* **Fail-soft.** A notification must never break generation or publishing — every
  send is wrapped; an unreachable Conductor or a missing token is a logged skip.
* **Once per event.** The publish gate polls every ~10 minutes, so each event is
  guarded by an S3 marker (``preview/<date>/notified-<event>[-<vid>].json``): it
  fires on the first qualifying poll and stays quiet thereafter.
* **One bot.** ``_channel_targets`` resolves to exactly one target: the ops bot when
  ``TELEGRAM_SENTINEL_BOT_TOKEN`` is set, else the first configured agent bot.
  ``"both"`` is accepted from old callers and collapsed.

Stdlib ``urllib`` only — no new dependency for a couple of HTTP calls.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
import urllib.parse
import urllib.request
import uuid
from typing import Any, Iterable, Optional

from content_pipeline.agent.publish import s3_key
from content_pipeline.content_config import content_cfg

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
# Telegram's sendMessage text limit — clip before sending, a 400 on length is
# as silent a killer as one on markup.
TELEGRAM_MAX_LEN = 4096

# ── the ops event contract (fleet conductor/ops_events/schema.py) ─────────────
OPS_SCHEMA = "grazlab.ops.event/1"
OPS_SOURCE = "craicgpt"
OPS_HOST = ".75"
OPS_TITLE_MAX = 120
OPS_DETAIL_MAX = 2000
# A `page` is honoured only for not_published / service_down / decision_needed — the
# fleet's apply_page_policy downgrades anything else to `warn`. The one page this module
# sends is `held` → decision_needed.
#
# An EXPLICIT hold (structural/link failure — no passive publish) has no natural deadline;
# its decision block still needs an `expires_at`, so it is the next morning's run: 24 h.
EXPLICIT_HOLD_MINUTES = 24 * 60


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _ts(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clip(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def build_event(*, severity: str, kind: str, component: str, title: str, detail: str,
                dedup_key: str, links: Optional[Iterable[str]] = None,
                decision: Optional[dict] = None, ttl_hours: int = 24,
                now: Optional[dt.datetime] = None) -> dict:
    """A ``grazlab.ops.event/1`` dict for the fleet's ``ops_event`` task. Title and
    detail are clipped to the contract's limits here so a caller never counts chars;
    the fleet validates the rest and rejects anything malformed (reported, not raised)."""
    return {
        "schema": OPS_SCHEMA,
        "ts": _ts(now or _utc_now()),
        "source": OPS_SOURCE,
        "component": component,
        "host": OPS_HOST,
        "severity": severity,
        "kind": kind,
        "title": _clip(title, OPS_TITLE_MAX),
        "detail": _clip(detail, OPS_DETAIL_MAX),
        "dedup_key": dedup_key,
        "links": [u for u in (links or []) if u],
        "decision": decision,
        "ttl_hours": ttl_hours,
        "unowned": False,
    }


# ── the Conductor lane ───────────────────────────────────────────────────────
def _http_post_json(url: str, body: dict, timeout: float) -> str:
    """POST JSON; return the response body as text. Raises on any failure."""
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — LAN Conductor
        return resp.read().decode("utf-8")


def _http_get_json(url: str, timeout: float) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 — LAN Conductor
        return json.loads(resp.read() or b"{}")


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


_TERMINAL = {"COMPLETED", "FAILED", "TERMINATED", "TIMED_OUT"}


def post_ops_event(event: dict, *, wait: bool = False, timeout: float = 10.0) -> dict:
    """Start the fleet's ``ops_event`` workflow with ``event`` (the sanctioned lane —
    fleet ``conductor/ops_events/README.md`` § Posting an event). Never raises.

    With ``wait`` it polls the execution for up to ``content_cfg.ops_page_wait_seconds``
    and reports the task's ``paged``/``stored`` output, so a page sender can tell
    whether the ONE bot was already rung before deciding to fall back."""
    base = content_cfg.conductor_url.rstrip("/")
    body = {"name": "ops_event", "version": 1, "input": {"event": event}}
    try:
        wf_id = _http_post_json(f"{base}/workflow", body, timeout).strip().strip('"')
    except Exception as exc:  # noqa: BLE001 — the lane being down must never break the run
        logger.warning("[ops_event] could not start workflow: %s", exc)
        return {"posted": False, "error": str(exc), "dedup_key": event.get("dedup_key")}
    out: dict[str, Any] = {"posted": True, "workflow_id": wf_id, "status": None,
                           "paged": None, "stored": None, "dedup_key": event.get("dedup_key")}
    if not wait:
        return out
    deadline = time.monotonic() + max(0.0, float(content_cfg.ops_page_wait_seconds))
    while True:
        try:
            # includeTasks: on a timeout we need to know whether a worker HAS the task
            # (IN_PROGRESS → it will page) or nobody polled it (SCHEDULED → nobody will).
            wf = _http_get_json(f"{base}/workflow/{wf_id}?includeTasks=true", timeout)
            out.pop("error", None)  # a transient poll error must not outlive a good answer
        except Exception as exc:  # noqa: BLE001
            out["error"] = str(exc)
            wf = {}
        status = str(wf.get("status") or "")
        if status in _TERMINAL:
            o = wf.get("output") or {}
            out.update(status=status, paged=bool(o.get("paged")), stored=bool(o.get("stored")),
                       suppressed=bool(o.get("suppressed")))
            if o.get("error"):
                out["error"] = o["error"]
            return out
        if time.monotonic() >= deadline:
            out["status"] = status or "UNKNOWN"
            out["task_status"] = next((str(t.get("status")) for t in wf.get("tasks") or []
                                       if t.get("taskType") == "ops_event"), None)
            return out
        _sleep(1.0)


def lane_owns_page(res: dict) -> bool:
    """Has the ``ops_event`` lane taken responsibility for ringing the ONE ops bot?

    Yes when it paged, when it suppressed the page because the same key paged within
    ``ttl_hours`` (that IS the dedup working), or when the wait ran out with a worker
    already holding the task (it is mid-send — a fallback now would be the double-send
    #187 measured). No when the POST failed, the event was rejected, the task FAILED
    (stored but undelivered), or the task was never picked up (the .75 worker is down)."""
    if not res.get("posted"):
        return False
    if res.get("paged") or res.get("suppressed"):
        return True
    if res.get("status") in _TERMINAL:
        return False
    return res.get("task_status") == "IN_PROGRESS"


# ── channel targets (ONE bot) ────────────────────────────────────────────────
def _channel_targets(which: str = "one") -> list[tuple[str, str, str]]:
    """``[(label, bot_token, chat_id)]`` — at most ONE target.

    ``which`` is ``"one"`` (default: the ops bot ``watch`` if its token is set, else the
    first configured agent bot), ``"watch"``, ``"openclaw"`` or ``"hermes"``. ``"both"``
    (old callers) collapses to ``"one"`` — both agent bots DM the same chat, so a fan-out
    only ever meant every message twice (#187). A missing token or chat id drops that
    candidate; an unconfigured deployment is a quiet no-op."""
    shared = content_cfg.telegram_chat_id
    candidates = [
        ("watch", content_cfg.telegram_watch_bot_token, shared),
        ("openclaw", content_cfg.telegram_openclaw_bot_token,
         content_cfg.telegram_openclaw_chat_id or shared),
        ("hermes", content_cfg.telegram_hermes_bot_token,
         content_cfg.telegram_hermes_chat_id or shared),
    ]
    configured = [(label, token, chat) for (label, token, chat) in candidates if token and chat]
    which = (which or "one").strip()
    if which in ("one", "both"):
        return configured[:1]
    return [t for t in configured if t[0] == which][:1]


# ── low-level send ───────────────────────────────────────────────────────────
def _send_once(url: str, fields: dict[str, str], timeout: float) -> tuple[bool, str]:
    """POST one ``sendMessage`` form; return ``(ok, detail)``. Never raises."""
    data = urllib.parse.urlencode(fields).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed api host
            payload = json.loads(resp.read() or b"{}")
        return bool(payload.get("ok")), str(payload.get("description", "ok"))
    except Exception as exc:  # noqa: BLE001 — a notification must never break the pipeline
        return False, str(exc)


def _post(token: str, chat_id: str, text: str, timeout: float) -> tuple[bool, str]:
    """Send ``text`` resiliently; return ``(ok, detail)``. Never raises.

    message_graham relays arbitrary text — including geek failure alerts that
    embed raw Python tracebacks (``<module>``, ``<frozen runpy>``). Telegram's
    HTML parse mode 400s on the unknown tags, and in Jul 2026 four days of
    those alerts died silently while everything read COMPLETED. So: clip to
    the API limit, and if the HTML attempt answers 400, retry once with no
    parse_mode at all — delivery beats formatting. The lifecycle helpers'
    intentional HTML (<b>, <code>) is untouched: the plain retry only fires
    on a 400."""
    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    clipped = text[:TELEGRAM_MAX_LEN]
    base = {"chat_id": chat_id, "disable_web_page_preview": "true"}
    ok, detail = _send_once(url, {**base, "text": clipped, "parse_mode": "HTML"}, timeout)
    if not ok and "400" in detail:
        logger.warning("[notify] HTML send rejected (%s); retrying as plain text", detail)
        ok, detail = _send_once(url, {**base, "text": clipped}, timeout)
    return ok, detail


def send_message(text: str, *, which: str = "one",
                 targets: Optional[Iterable[tuple[str, str, str]]] = None,
                 timeout: float = 10.0) -> list[dict]:
    """Send ``text`` to ONE channel (see ``_channel_targets``; explicit ``targets``
    override the resolver — tests and the ad-hoc ``cli message``). Returns a per-target
    result list (empty if Telegram isn't configured — a quiet, intentional skip)."""
    targets = list(targets) if targets is not None else _channel_targets(which)
    if not targets:
        logger.info("[notify] telegram not configured; skipping: %s", text[:80])
        return []
    results: list[dict] = []
    for label, token, chat_id in targets:
        ok, detail = _post(token, chat_id, text, timeout)
        (logger.info if ok else logger.warning)(
            "[notify] %s → %s%s", label, "ok" if ok else "FAILED",
            "" if ok else f" ({detail})")
        results.append({"target": label, "chat_id": chat_id, "ok": ok, "detail": detail})
    return results


# ── idempotency marker ───────────────────────────────────────────────────────
def notified_key(date_iso: str, event: str, vid: Optional[str] = None) -> str:
    # Version-keyed when vid is given so EACH same-day edition version notifies once
    # (the versioning workflow allows multiple applies/day); per-date otherwise.
    name = f"notified-{event}-{vid}.json" if vid else f"notified-{event}.json"
    return s3_key(date_iso, content_cfg.preview_prefix, name)


def _default_s3():
    import boto3

    return boto3.client("s3", region_name=content_cfg.aws_region)


def _flag_exists(s3: Any, bucket: str, key: str) -> bool:
    try:
        s3.get_object(Bucket=bucket, Key=key)
        return True
    except Exception:  # noqa: BLE001 — missing key (or any read error) → treat as not-yet-sent
        return False


def _set_flag(s3: Any, bucket: str, key: str, event: str, date_iso: str) -> None:
    s3.put_object(
        Bucket=bucket, Key=key,
        Body=json.dumps({"date": date_iso, "event": event},
                        ensure_ascii=False).encode("utf-8"),
        ContentType="application/json", CacheControl="no-cache")


def _marker(event: str, date_iso: str, vid: Optional[str], s3: Any | None,
            bucket: Optional[str]) -> tuple[Any | None, str, str]:
    """Resolve (client, bucket, key) for the once-per-event marker; client None → no dedupe."""
    bucket = bucket or content_cfg.s3_bucket
    client = s3
    if client is None:
        try:
            client = _default_s3()
        except Exception:  # noqa: BLE001 — no creds/boto3 → act without dedupe
            client = None
    return client, bucket, notified_key(date_iso, event, vid)


def _mark(client: Any | None, bucket: str, key: str, event: str, date_iso: str) -> None:
    if client is None:
        return
    try:
        _set_flag(client, bucket, key, event, date_iso)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[notify] could not set %s marker: %s", event, exc)


def notify_once(event: str, date_iso: str, text: str, *,
                vid: Optional[str] = None,
                s3: Any | None = None, bucket: Optional[str] = None,
                targets: Optional[Iterable[tuple[str, str, str]]] = None) -> dict:
    """Telegram ``text`` at most once per ``(date_iso, event, vid)`` — the raw-text
    primitive, kept for ad-hoc use. Lifecycle events go through ``emit_once``.

    The marker is only written once a send actually lands, so a transient outage
    doesn't permanently suppress the alert. If S3 is unreachable we still send (a
    duplicate beats a silent miss)."""
    client, bucket, key = _marker(event, date_iso, vid, s3, bucket)
    if client is not None and _flag_exists(client, bucket, key):
        return {"sent": False, "reason": "already-notified", "event": event}
    results = send_message(text, targets=targets)
    sent = any(r["ok"] for r in results)
    if sent:
        _mark(client, bucket, key, event, date_iso)
    return {"sent": sent, "results": results, "event": event}


def emit_once(event: str, date_iso: str, ops_event: dict, *,
              vid: Optional[str] = None, page_fallback_text: Optional[str] = None,
              s3: Any | None = None, bucket: Optional[str] = None) -> dict:
    """Post ``ops_event`` to the fleet at most once per ``(date_iso, event, vid)``.

    A ``page`` waits for the ``ops_event`` task's verdict; unless the lane owns the page
    (``lane_owns_page``: paged, suppressed as already-paged, or mid-send at the deadline),
    ``page_fallback_text`` goes out as ONE Telegram on ONE bot — the pre-digest
    behaviour, kept for a dead lane (unreachable, rejected, FAILED, or never picked up). A digest-class event never touches Telegram. The marker is written
    only when the event was accepted (or the fallback landed), so an outage never
    permanently suppresses it."""
    client, bucket, key = _marker(event, date_iso, vid, s3, bucket)
    if client is not None and _flag_exists(client, bucket, key):
        return {"sent": False, "reason": "already-notified", "event": event}

    is_page = ops_event.get("severity") == "page"
    res = post_ops_event(ops_event, wait=is_page)
    if is_page:
        accepted = lane_owns_page(res)
    else:
        accepted = bool(res.get("posted")) and res.get("stored") is not False and not res.get("error")
    telegram: list[dict] = []
    if is_page and not accepted:
        if page_fallback_text:
            logger.warning("[notify] ops_event lane did not page %s (%s); falling back to one bot",
                           event, res.get("status") or res.get("error"))
            telegram = send_message(page_fallback_text)
    sent = any(r["ok"] for r in telegram)
    if accepted or sent:
        _mark(client, bucket, key, event, date_iso)
    return {"sent": sent, "results": telegram, "event": res, "event_name": event}


# ── lifecycle helpers (called from cli.py) ───────────────────────────────────
def _vid_tail(vid: Optional[str]) -> str:
    return f":{vid}" if vid else ""


def notify_published(date_iso: str, live_url: str, *, note: Optional[str] = None,
                     approvers: Optional[Iterable[str]] = None,
                     link_count: Optional[int] = None, version: Optional[str] = None,
                     vid: Optional[str] = None, s3: Any | None = None,
                     bucket: Optional[str] = None) -> dict:
    """Record a live publish WITH its validation receipts — who approved, how many
    source links were verified, which version — as an ``info``/``published`` event
    for the digest (the 2026-06-04 worry: a publish is never a bare "it's live")."""
    bits = []
    approvers = list(approvers or [])
    if approvers:
        bits.append("approved by " + " + ".join(f"{a} ✓" for a in approvers))
    if link_count is not None:
        bits.append(f"{link_count} source links verified")
    if version:
        bits.append(str(version))
    detail = " · ".join(bits) or "published live"
    if note:
        detail += f"\n{note}"
    detail += f"\n{live_url}"
    ev = build_event(
        severity="info", kind="published", component="publish_gate",
        title=f"CraicGPT {date_iso} published live" + (f" ({version})" if version else ""),
        detail=detail, dedup_key=f"craicgpt:published:{date_iso}{_vid_tail(vid)}",
        links=[live_url])
    return emit_once("published", date_iso, ev, vid=vid, s3=s3, bucket=bucket)


def notify_held(date_iso: str, reasons: Iterable[str], *, vid: Optional[str] = None,
                passive_minutes: Optional[int] = None, no_draft: bool = False,
                s3: Any | None = None, bucket: Optional[str] = None) -> dict:
    """The ONE page: an edition is held and Graham has a decision to make.

    With ``passive_minutes`` (a judgement HOLD on a structurally valid edition) the
    decision is SAFE and passively publishes when the window lapses; without it (a
    hard structural/link hold) it is EXPLICIT and simply waits for him. ``no_draft``
    is the integrity hold from ``cli run`` (EditionHeld): nothing was written, so
    there is nothing to override — the options are a re-run or leaving the day dark.
    If the fleet's ``ops_event`` lane does not own the page (``lane_owns_page``), the
    same message goes out on ONE bot from here."""
    reasons = list(reasons) or ["(no reason given)"]
    body = "\n".join(f"• {r}" for r in reasons)
    now = _utc_now()
    if no_draft:
        options = ["rerun", "skip"]
        what = "Not generated — the edition was HELD before a draft existed"
        how = (f"`cli run --no-recency --publish-draft --date {date_iso}` re-runs it; "
               "doing nothing leaves the day without an edition.")
    else:
        options = ["override", "hold"]
        what = "Not published — the approval gate held it"
        how = f"`cli override --date {date_iso}` publishes now; `cli hold` keeps it held."
    decision: dict[str, Any] = {
        "nonce": uuid.uuid4().hex[:12],
        "tier": "SAFE" if passive_minutes else "EXPLICIT",
        "options": options,
        "expires_at": _ts(now + dt.timedelta(minutes=passive_minutes or EXPLICIT_HOLD_MINUTES)),
    }
    if passive_minutes:
        decision["passive_action"] = "publish"
    ymd = "/".join(date_iso.split("-"))
    ev = build_event(
        severity="page", kind="decision_needed", component="publish_gate",
        title=f"CraicGPT {date_iso} edition HELD — decision needed",
        detail=f"{what}. Reasons:\n{body}\n{how}",
        dedup_key=f"craicgpt:decision_needed:held:{date_iso}{_vid_tail(vid)}",
        links=[f"{content_cfg.site_base_url.rstrip('/')}/preview/{ymd}/paper_content.json"],
        decision=decision, now=now)
    text = (f"✋ <b>CraicGPT edition HELD</b> — {date_iso}\n"
            f"{what}. Reasons:\n{body}")
    return emit_once("held", date_iso, ev, vid=vid, page_fallback_text=text, s3=s3,
                     bucket=bucket)


def notify_degraded(event: str, date_iso: str, subject: str, title: str, detail: str, *,
                    vid: Optional[str] = None, s3: Any | None = None,
                    bucket: Optional[str] = None) -> dict:
    """A ``warn``/``degraded`` digest line: the edition published, but a desk or a
    language is below par (``fun_no_comedy``, ``translation_degraded``)."""
    ev = build_event(
        severity="warn", kind="degraded", component="edition", title=title, detail=detail,
        dedup_key=f"craicgpt:degraded:{subject}:{date_iso}{_vid_tail(vid)}")
    return emit_once(event, date_iso, ev, vid=vid, s3=s3, bucket=bucket)


def notify_flagged(date_iso: str, flagged_by_ref: dict[str, dict], *,
                   graded: bool = True, vid: Optional[str] = None,
                   s3: Any | None = None, bucket: Optional[str] = None) -> dict:
    """A published-anyway QUALITY-CONTROL note: the advisory per-article gate flagged
    one or more stories (kept + stamped in the UI, NOT dropped) — Graham should
    spot-check them. ``warn``/``flagged``; distinct from a hard ``held``."""
    if not flagged_by_ref and graded:
        return {}
    lines = [f"• {ref} — {qc.get('flag', 'flagged')}: {qc.get('reason', '')}"
             for ref, qc in sorted(flagged_by_ref.items())]
    body = "\n".join(lines) if lines else "• (none)"
    tail = "" if graded else ("\n⚠️ fabrication grade was unavailable this run — "
                              "published WITHOUT per-article stamps; eyeball the lead.")
    ev = build_event(
        severity="warn", kind="flagged", component="article_gate",
        title=f"CraicGPT {date_iso}: {len(flagged_by_ref)} story(ies) published with a QC stamp",
        detail=f"Please spot-check:\n{body}{tail}",
        dedup_key=f"craicgpt:flagged:qc:{date_iso}{_vid_tail(vid)}")
    return emit_once("qc_flagged", date_iso, ev, vid=vid, s3=s3, bucket=bucket)
