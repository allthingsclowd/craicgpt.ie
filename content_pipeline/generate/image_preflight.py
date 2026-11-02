"""
content_pipeline/generate/image_preflight.py
============================================
A read-only memory pre-flight on the M3's render slot, run once before the image stage.

WHY (fleet #219)
----------------
The 2026-10-28 and 2026-11-02 editions were lost to what looked like a sampler stall at
step 0. It was a model LOAD hanging for hours under unified-memory starvation: the M3 sat
at critical memory pressure, ComfyUI kept one model set resident and loaded another on
top, and the kernel never recovered. The shim's ``/health`` said ``ok`` the whole time.

So before the first render we ask three questions (#222, "hygiene, not policy"):

* is memory pressure **normal**;
* is there room for the model set plus a 40 GB margin
  (``content_cfg.image_preflight_min_free_gb``);
* is the shim **idle**, or at least not stuck on an OLD job
  (``content_cfg.image_preflight_max_job_age_s``)?

WHAT IT DOES ABOUT A "NO"
-------------------------
It waits briefly (``image_preflight_wait_s``) in case the slot clears — a Hermes render
finishing, say — then pages Graham ``decision_needed`` ONCE through the existing ops-event
lane (:func:`notifications.notify_image_preflight`) and **proceeds anyway**. The page is
a SAFE decision whose passive action is "proceed": it buys him the chance to free the M3
at 05:15 rather than discover a held edition at 07:00. It never blocks the run, and it
never raises — per-image deadlines and the per-image fallback are what bound the damage
if the slot really is sick.

TOLERANT BY DESIGN
------------------
Today's shim reports only ``ok``/``busy``/``queue_*``. Fleet #230 adds memory pressure,
available GB and the running job's age. Field names are read from several plausible
spellings, flat or nested under ``memory`` / ``job``; an absent field skips its check
rather than failing it. Deterministic, stdlib only — no LLM anywhere in here.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from content_pipeline.content_config import content_cfg

logger = logging.getLogger(__name__)

POLL_SECONDS = 15.0

# macOS kern.memorystatus_vm_pressure_level: 1 normal, 2 warn, 4 critical.
_NORMAL_WORDS = {"normal", "ok", "green", "1"}


@dataclass
class SlotReading:
    """One verdict on the render slot: healthy or not, why, and what was read."""

    ok: bool
    reasons: list[str] = field(default_factory=list)
    snapshot: dict = field(default_factory=dict)


def _fetch_health() -> Optional[dict]:
    """GET the shim's /health; ``None`` when it cannot be reached or parsed."""
    try:
        with urllib.request.urlopen(content_cfg.image_shim_health_url,  # noqa: S310 — LAN shim
                                    timeout=10) as resp:
            return json.loads(resp.read() or b"{}")
    except Exception as exc:  # noqa: BLE001 — unreachable is a READING, not an error
        logger.warning("[image_preflight] /health unreachable: %s", exc)
        return None


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _pick(health: dict, flat: tuple[str, ...], nested: tuple[tuple[str, str], ...]) -> Any:
    """First present value among flat keys, then ``parent.child`` nested keys."""
    for k in flat:
        if health.get(k) is not None:
            return health[k]
    for parent, child in nested:
        sub = health.get(parent)
        if isinstance(sub, dict) and sub.get(child) is not None:
            return sub[child]
    return None


def _pressure_is_normal(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) <= 1
    return str(value).strip().lower() in _NORMAL_WORDS


def assess(health: Optional[dict], *, min_free_gb: Optional[float] = None,
           max_job_age_s: Optional[float] = None) -> SlotReading:
    """Judge one /health reading. Pure — the seam the tests drive."""
    min_free = content_cfg.image_preflight_min_free_gb if min_free_gb is None else min_free_gb
    max_age = content_cfg.image_preflight_max_job_age_s if max_job_age_s is None else max_job_age_s
    if health is None:
        return SlotReading(False, ["shim /health unreachable"], {"reachable": False})

    pressure = _pick(health, ("memory_pressure", "memory_pressure_level", "pressure",
                              "vm_pressure_level"),
                     (("memory", "pressure"), ("memory", "pressure_level"), ("memory", "level")))
    avail = _pick(health, ("memory_available_gb", "available_gb", "mem_available_gb",
                           "free_gb"),
                  (("memory", "available_gb"), ("memory", "available"), ("memory", "free_gb")))
    age = _pick(health, ("job_age_s", "job_age_sec", "job_age_seconds", "running_job_age_s"),
                (("job", "age_s"), ("job", "age_seconds"), ("job", "age_sec"),
                 ("running", "age_s")))
    busy = bool(health.get("busy")) or bool(health.get("queue_running"))
    snapshot = {"reachable": True, "shim_ok": health.get("ok"), "busy": busy,
                "memory_pressure": pressure, "memory_available_gb": avail, "job_age_s": age,
                "queue_pending": health.get("queue_pending")}

    reasons: list[str] = []
    if health.get("ok") is False:
        reasons.append("shim reports not ok (ComfyUI unreachable or a workflow missing)")
    if pressure is not None and not _pressure_is_normal(pressure):
        reasons.append(f"memory pressure {pressure} (want normal)")
    try:
        if avail is not None and float(avail) < min_free:
            reasons.append(f"{float(avail):.0f} GB available (want >= {min_free:.0f} GB: "
                           "the model set + 40 GB)")
    except (TypeError, ValueError):
        pass
    if busy:
        try:
            if age is None:
                reasons.append("shim busy (job age unknown)")
            elif float(age) > max_age:
                reasons.append(f"shim busy with a job {float(age):.0f} s old "
                               f"(older than {max_age:.0f} s)")
        except (TypeError, ValueError):
            reasons.append("shim busy (job age unreadable)")
    return SlotReading(not reasons, reasons, snapshot)


def preflight(date_iso: str, *, fetch: Optional[Callable[[], Optional[dict]]] = None,
              sleep: Optional[Callable[[float], None]] = None,
              notify: Optional[Callable[..., Any]] = None,
              attempts: Optional[int] = None) -> SlotReading:
    """Check the slot; wait briefly while it is sick; page once and proceed. Never raises.

    ``attempts`` polls are made ``POLL_SECONDS`` apart (default: enough to cover
    ``content_cfg.image_preflight_wait_s``). Counting polls rather than wall time keeps the
    loop honest under an injected no-op ``sleep``.
    """
    fetch = fetch or _fetch_health
    sleep = sleep or _sleep
    if attempts is None:
        attempts = int(max(0.0, content_cfg.image_preflight_wait_s) // POLL_SECONDS) + 1
    attempts = max(1, attempts)

    reading = SlotReading(False, ["not checked"], {})
    for i in range(attempts):
        try:
            reading = assess(fetch())
        except Exception as exc:  # noqa: BLE001
            reading = SlotReading(False, [f"pre-flight error: {exc}"], {})
        if reading.ok:
            return reading
        if i < attempts - 1:
            logger.info("[image_preflight] slot not ready (%s); waiting %ss",
                        "; ".join(reading.reasons), POLL_SECONDS)
            sleep(POLL_SECONDS)

    logger.warning("[image_preflight] slot still sick after %d checks: %s — paging and "
                   "proceeding", attempts, "; ".join(reading.reasons))
    try:
        if notify is None:
            from content_pipeline import notifications

            notify = notifications.notify_image_preflight
        notify(date_iso, reading.reasons, snapshot=reading.snapshot)
    except Exception as exc:  # noqa: BLE001 — a page failing must never stop the images
        logger.warning("[image_preflight] could not page: %s", exc)
    return reading
