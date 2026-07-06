"""
content_pipeline/notifications.py
=================================
Operator notifications for the daily edition lifecycle, over Telegram.

The .75 engine is the **single, deterministic** source of these alerts — it is
the place that knows when a draft has been generated and, via the publish gate,
when an edition goes live or is held. The approval agents deliberately do NOT
send them: that path kept failing silently ("no home channel configured") and an
editorial HOLD slipped past unseen, leaving the site looking stale with nobody
told why. Centralising here fixes that.

Every lifecycle event fans out to **both** agents' Telegram channels (hermes +
openclaw) so Graham gets the same visibility wherever he happens to be looking.

Two design rules:

* **Fail-soft.** A notification must never break generation or publishing — every
  send is wrapped, a missing token/chat-id is a quiet skip, not an error.
* **Once per event.** The publish gate polls every ~10 minutes, so each alert is
  guarded by an S3 marker (``preview/<date>/notified-<event>.json``): it fires on
  the first qualifying poll and stays quiet thereafter.

Stdlib ``urllib`` only — no new dependency for a one-line HTTP POST.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any, Iterable, Optional

from content_pipeline.agent.publish import s3_key
from content_pipeline.content_config import content_cfg

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
# Telegram's sendMessage text limit — clip before sending, a 400 on length is
# as silent a killer as one on markup.
TELEGRAM_MAX_LEN = 4096


# --- channel targets --------------------------------------------------------
def _channel_targets(which: str = "both") -> list[tuple[str, str, str]]:
    """``[(label, bot_token, chat_id)]`` for the requested channel(s).

    Each agent has its own bot; both default to the shared operator chat unless a
    per-agent chat id overrides it. A channel missing a token or a chat id is
    dropped, so an unconfigured deployment is a quiet no-op. ``which`` selects
    ``"openclaw"``, ``"hermes"`` or ``"both"`` (the default)."""
    shared = content_cfg.telegram_chat_id
    candidates = [
        ("openclaw", content_cfg.telegram_openclaw_bot_token,
         content_cfg.telegram_openclaw_chat_id or shared),
        ("hermes", content_cfg.telegram_hermes_bot_token,
         content_cfg.telegram_hermes_chat_id or shared),
    ]
    targets = [(label, token, chat) for (label, token, chat) in candidates if token and chat]
    if which and which != "both":
        targets = [t for t in targets if t[0] == which]
    return targets


# --- low-level send ---------------------------------------------------------
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


def send_message(text: str, *, which: str = "both",
                 targets: Optional[Iterable[tuple[str, str, str]]] = None,
                 timeout: float = 10.0) -> list[dict]:
    """Fan ``text`` out to the requested channel(s) (each via its own bot).
    ``which`` is ``"openclaw"``, ``"hermes"`` or ``"both"`` (ignored if explicit
    ``targets`` are passed). Returns a per-target result list (empty if Telegram
    isn't configured — a quiet, intentional skip)."""
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


# --- idempotency marker -----------------------------------------------------
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


def notify_once(event: str, date_iso: str, text: str, *,
                vid: Optional[str] = None,
                s3: Any | None = None, bucket: Optional[str] = None,
                targets: Optional[Iterable[tuple[str, str, str]]] = None) -> dict:
    """Send ``text`` at most once per ``(date_iso, event, vid)``.

    The marker is only written once a send actually lands somewhere, so a
    transient outage doesn't permanently suppress the alert. If S3 is unreachable
    we still send (a duplicate beats a silent miss). ``vid`` (a version id) keys
    the marker per edition-version, so a same-day re-apply notifies again rather
    than being deduped against an earlier version."""
    bucket = bucket or content_cfg.s3_bucket
    client = s3
    if client is None:
        try:
            client = _default_s3()
        except Exception:  # noqa: BLE001 — no creds/boto3 → send without dedupe
            client = None

    key = notified_key(date_iso, event, vid)
    if client is not None and _flag_exists(client, bucket, key):
        return {"sent": False, "reason": "already-notified", "event": event}

    results = send_message(text, targets=targets)
    sent = any(r["ok"] for r in results)
    if client is not None and sent:
        try:
            _set_flag(client, bucket, key, event, date_iso)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[notify] could not set %s marker: %s", event, exc)
    return {"sent": sent, "results": results, "event": event}


# --- lifecycle helpers (called from cli.py) ---------------------------------
def notify_generated(date_iso: str, draft_url: str, *, vid: Optional[str] = None,
                     s3: Any | None = None) -> dict:
    text = (f"📰 <b>CraicGPT draft generated</b> — {date_iso}\n"
            f"Judged in-pipeline by the rubric; the publish gate auto-promotes it live on "
            f"APPROVE — I'll only ping you if it's held.\n{draft_url}")
    return notify_once("generated", date_iso, text, vid=vid, s3=s3)


def notify_published(date_iso: str, live_url: str, *, note: Optional[str] = None,
                     approvers: Optional[Iterable[str]] = None,
                     link_count: Optional[int] = None, version: Optional[str] = None,
                     vid: Optional[str] = None, s3: Any | None = None) -> dict:
    """Announce a live publish WITH its validation receipts inline — who approved,
    how many source links were verified, and which version — so a publish is never
    a bare "it's live" with no visible validation (the 2026-06-04 worry)."""
    bits = []
    approvers = list(approvers or [])
    if approvers:
        bits.append("approved by " + " + ".join(f"{a} ✓" for a in approvers))
    if link_count is not None:
        bits.append(f"{link_count} source links verified")
    if version:
        bits.append(str(version))
    receipt = ("\n🔎 " + " · ".join(bits)) if bits else ""
    extra = f"\n<i>{note}</i>" if note else ""
    text = (f"✅ <b>CraicGPT edition published live</b> — {date_iso}{receipt}{extra}\n{live_url}")
    return notify_once("published", date_iso, text, vid=vid, s3=s3)


def notify_held(date_iso: str, reasons: Iterable[str], *, vid: Optional[str] = None,
                s3: Any | None = None) -> dict:
    body = "\n".join(f"• {r}" for r in (list(reasons) or ["(no reason given)"]))
    text = (f"✋ <b>CraicGPT edition HELD</b> — {date_iso}\n"
            f"Not published — the approval gate held it. Reasons:\n{body}")
    return notify_once("held", date_iso, text, vid=vid, s3=s3)


def notify_flagged(date_iso: str, flagged_by_ref: dict[str, dict], *,
                   graded: bool = True, vid: Optional[str] = None,
                   s3: Any | None = None) -> dict:
    """A published-anyway QUALITY-CONTROL alert: the advisory per-article gate flagged
    one or more stories (kept + stamped in the UI, NOT dropped) — Graham should
    spot-check them. Distinct event from a hard ``held`` (the edition DID publish)."""
    if not flagged_by_ref and graded:
        return {}
    lines = [f"• <code>{ref}</code> — {qc.get('flag', 'flagged')}: {qc.get('reason', '')}"
             for ref, qc in sorted(flagged_by_ref.items())]
    body = "\n".join(lines) if lines else "• (none)"
    tail = "" if graded else ("\n⚠️ fabrication grade was unavailable this run — "
                              "published WITHOUT per-article stamps; eyeball the lead.")
    text = (f"🔎 <b>CraicGPT quality-control flags</b> — {date_iso}\n"
            f"Published live with a warning stamp on {len(flagged_by_ref)} story(ies); "
            f"please spot-check:\n{body}{tail}")
    return notify_once("qc_flagged", date_iso, text, vid=vid, s3=s3)
