"""
shared/enrich/enrich.py
=======================
A course-agnostic **content-enhancement agent**: given one course item and the
ATT&CK tactic (or lesson topic) it teaches, find ONE genuinely relevant, RECENT,
real-world hook — a breach, a CVE, an in-the-wild campaign — and frame it as a
one-line teaching tie-in in Graham's voice, carrying its citation.

Why this module exists
----------------------
A lesson on, say, *Valid Accounts* (ATT&CK T1078) lands ten times harder when it
opens with "remember the Change Healthcare breach that started with a single
stolen login and no MFA?" than with an abstract definition. That hook is a matter
of *judgement* — somebody has to KNOW which recent incident actually illustrates
this tactic — and judgement is exactly the thing we spend an LLM call on. The
plumbing around it (building the prompt, parsing the reply, checking the shape,
stamping which model ran) is deterministic and lives here in code.

TUTORIAL: deterministic harness, LLM does the judgement
-------------------------------------------------------
This is the house pattern (see the CraicGPT sibling's ``generate/image_gag.py``,
which turns a story into a visual gag). The fence is drawn deliberately:

* The MODEL contributes exactly one thing — the idea: *which* real incident maps
  to this tactic, and how to phrase the tie-in.
* The CODE does everything reproducible — assembling the prompt, extracting JSON
  from a chatty reply, validating that the hook is well-formed and CITED, routing
  the call local-first with a cross-box fallback, and recording which route
  actually served the text so the attribution is honest.

Nothing here decides layout, picks the item, or verifies facts by fiat; those are
either the caller's job or (for live link-checking) an injected verifier.

TUTORIAL: integrity over output — the reason it can return ``None``
-------------------------------------------------------------------
The single most important design choice: **a fabricated hook is worse than no
hook at all.** A course that cites a breach which never happened is a course that
has lied to its students, and offensive-security students will check. So the
contract is fail-soft and honest, mirroring ``image_gag.build_gag``:

* If the model cannot recall a genuinely relevant recent incident, it is told to
  DECLINE (``found: false``) — and declining returns ``None``.
* If the reply is missing a citation, carries a placeholder URL
  (``example.com``…), or is otherwise malformed, we return ``None`` rather than
  attach a half-hook.
* If an (optional, injected) ``verify_url`` says the citation is unreachable, we
  return ``None``.

``None`` means *the caller keeps the item exactly as it was.* Enrichment is a
nice-to-have; correctness is not negotiable. This module therefore NEVER raises on
a model or transport failure — it logs and returns ``None``.

Offline-testable by construction
--------------------------------
The LLM boundary is an injected :class:`LLMClient` (a ``Protocol``). Tests pass a
tiny stub and exercise the whole harness with no network and no LLM. The REAL
client (:func:`default_llm`) imports its SDK **lazily inside the run path**, so
importing this module — and running the tests — needs nothing beyond the stdlib.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Callable, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# A live citation checker: (url) -> True if the citation is reachable/valid. The
# network CLI wires a real HEAD request here; the pure, offline path leaves it unset.
VerifyUrl = Callable[[str], bool]


# ─────────────────────────────────────────────────────────────────────────────
# Model routes — VISIBLE and env-overridable, read via a factory (no singleton)
# ─────────────────────────────────────────────────────────────────────────────
# TUTORIAL: the house rule is "factory functions for models, never module-level
# singletons, and read routes from env". These names are the grazlab catalog
# defaults; production overrides them in /etc/craicgpt.env. They are constants so
# a reader can SEE the default route without chasing an env var, and they are read
# through _model_routes() (below) at call time so a test or a deployment can flip
# ENRICH_MODEL / ENRICH_FALLBACK_MODEL without re-importing.
DEFAULT_ENRICH_MODEL = "dgx/vllm/qwen3.8-27b-nvfp4"
DEFAULT_ENRICH_FALLBACK_MODEL = "m3/mlx/qwen3.8-27b-8bit"

# LiteLLM proxy defaults — the whole fleet is reached by MODEL NAME through one
# base_url, so this module never hardcodes an engine host or a key.
DEFAULT_LITELLM_BASE_URL = "https://llm.grazlab.thescriptingpaddy.com/v1"
DEFAULT_LITELLM_API_KEY = "sk-no-key-required"


def _model_routes() -> tuple[str, str]:
    """Return ``(local_model, fallback_model)`` from env, defaults visible above."""
    return (
        os.getenv("ENRICH_MODEL", DEFAULT_ENRICH_MODEL),
        os.getenv("ENRICH_FALLBACK_MODEL", DEFAULT_ENRICH_FALLBACK_MODEL),
    )


# ─────────────────────────────────────────────────────────────────────────────
# The injectable LLM boundary
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class LLMResponse:
    """One completion plus the route that actually produced it.

    Carrying ``model`` here (rather than reading it back off a stateful client) is
    what makes attribution HONEST: :class:`Enrichment` stamps the exact route that
    served the text, even when a cross-box fallback fired.
    """

    text: str
    model: str


@runtime_checkable
class LLMClient(Protocol):
    """The one seam this module talks to the outside world through.

    TUTORIAL: a ``Protocol`` (structural typing) is the lightest possible
    dependency-injection boundary — anything with a matching ``complete`` method
    satisfies it, so the tests pass a five-line stub and the production factory
    passes a LiteLLM-routed client, with no shared base class and no import of a
    heavy SDK to construct the type. ``complete`` takes a prompt and returns the
    RAW text; parsing it is the harness's job, not the model's.
    """

    def complete(self, prompt: str) -> LLMResponse:  # pragma: no cover - interface
        ...


# ─────────────────────────────────────────────────────────────────────────────
# The result type
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Enrichment:
    """A real-world hook attached to a course item.

    Attributes:
        headline:   The incident named plainly — e.g. "The 2024 Change Healthcare
                    ransomware breach".
        tie_in:     One or two sentences in Graham's teaching voice connecting the
                    incident to the tactic being taught.
        source_url: The citation. REQUIRED — an enrichment with no source is not an
                    enrichment, it is a claim, and this module does not ship claims.
        model_used: The route that actually generated it (local or the cross-box
                    fallback), for truthful attribution.
    """

    headline: str
    tie_in: str
    source_url: str
    model_used: str

    def as_dict(self) -> dict:
        """A JSON-friendly blurb the caller can stash on the item (e.g. under
        ``item["_enrichment"]``) or render however it likes."""
        return {
            "headline": self.headline,
            "tie_in": self.tie_in,
            "source_url": self.source_url,
            "_model": self.model_used,
        }


# ─────────────────────────────────────────────────────────────────────────────
# The prompt — the model's whole job is JUDGEMENT
# ─────────────────────────────────────────────────────────────────────────────
# TUTORIAL: note what is and isn't asked of the model. It is asked for judgement
# (which real incident fits, how to phrase the tie-in) and told, in the strongest
# terms, to DECLINE rather than invent — because the harness cannot fact-check the
# open world offline, so honesty has to be built into the ask AND enforced on the
# reply. It is NOT asked to choose the output shape (a strict JSON contract) or to
# decide relevance thresholds (the caller picks the tactic).
_ENRICH_PROMPT = (
    "You are Graham, an Irish offensive-security instructor — witty, concise, and "
    "allergic to corporate-deck-speak. You are enriching one item of course "
    "material with a real, recent, real-world hook so the lesson lands.\n\n"
    "THE TACTIC / TOPIC BEING TAUGHT: {topic}\n\n"
    "THE COURSE ITEM:\n"
    "TITLE: {title}\n"
    "{body}\n\n"
    "Find ONE genuinely relevant, RECENT (ideally within the last ~24 months) "
    "real-world incident that illustrates this tactic — a breach, an exploited "
    "CVE, or an in-the-wild campaign. Then:\n"
    "- Name it plainly in a short HEADLINE.\n"
    "- Write a TIE_IN of one or two sentences, in your teaching voice, connecting "
    "that incident to what this item teaches. Concrete, not abstract.\n"
    "- Give the canonical public SOURCE_URL for it (a vendor advisory, MITRE, a "
    "CVE record, or reputable reporting).\n\n"
    "INTEGRITY RULES — these override the desire to be helpful:\n"
    "- Only cite an incident you are genuinely confident ACTUALLY HAPPENED. Never "
    "invent a breach, a company, a CVE number, or a URL to fill the gap.\n"
    "- The source_url must be a real citation, not a placeholder like example.com.\n"
    "- If you cannot recall a genuinely relevant, real, recent incident for THIS "
    "tactic, you MUST decline: return found=false and leave the other fields "
    "empty. Declining is the correct, honourable answer — a fabricated hook fails "
    "the student.\n\n"
    'Output ONLY compact JSON (no markdown): {{"found": true|false, '
    '"headline": "...", "tie_in": "...", "source_url": "https://..."}}'
)


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic plumbing: parse + integrity checks
# ─────────────────────────────────────────────────────────────────────────────
def _extract_json(text: str) -> Optional[dict]:
    """Recover a JSON object from a possibly chatty reply — stdlib only.

    Local models like to wrap JSON in ``` fences or a ``<think>`` preamble. We try
    a straight parse first, then fall back to the first ``{`` … last ``}`` slice.
    Returns ``None`` if nothing parseable is found — a parse failure is just
    another reason to decline, never an exception that could sink a run.
    """
    if not text:
        return None
    raw = text.strip()
    # Strip a leading ```json / ``` fence if present.
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z0-9]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw.strip())
    for candidate in (raw, _brace_slice(raw)):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict):
            return data
    return None


def _brace_slice(text: str) -> Optional[str]:
    """The substring from the first ``{`` to the last ``}``, or ``None``."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


# A citation has to be an absolute http(s) URL with a real-looking host. These are
# the fabrication SMELLS — the placeholders a model reaches for when it has no real
# source but was pushed to produce one anyway. Rejecting them is a deterministic
# integrity gate; it is not a substitute for the live link-check (see verify_url).
_PLACEHOLDER_HOSTS = frozenset(
    {"example.com", "example.org", "example.net", "localhost", "test.com", "url.com"}
)
_URL_RE = re.compile(r"^https?://([^/\s]+)", re.IGNORECASE)


def _looks_like_citation(url: str) -> bool:
    """True only for an absolute http(s) URL with a plausible, non-placeholder host."""
    text = (url or "").strip()
    match = _URL_RE.match(text)
    if not match:
        return False
    host = match.group(1).lower().split("@")[-1].split(":")[0]
    if host in _PLACEHOLDER_HOSTS or host.startswith("example."):
        return False
    # A real host has a dot and a TLD-ish tail; "localhost"/"foo" do not.
    return "." in host and len(host.rsplit(".", 1)[-1]) >= 2


def _clean(value: object) -> str:
    """Collapse whitespace on a possibly-missing string field."""
    return " ".join(str(value or "").split())


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
def enrich_item(
    item: dict,
    *,
    topic: str,
    llm: Optional[LLMClient] = None,
    verify_url: Optional[VerifyUrl] = None,
) -> Optional[Enrichment]:
    """Return an :class:`Enrichment` for ``item``, or ``None`` if none is warranted.

    Args:
        item: A course item dict. Reads ``title`` and ``body`` (``summary`` and
            ``content`` are accepted as aliases) — course-agnostic, so any lesson
            shape works as long as it carries some text.
        topic: The ATT&CK tactic or lesson topic the item teaches (e.g.
            ``"Valid Accounts (T1078)"``). This is what the hook must illustrate.
        llm: The injected LLM boundary. Defaults to :func:`default_llm`, which
            routes local-first with a cross-box fallback through LiteLLM. Tests
            pass a stub, so the whole function runs offline.
        verify_url: Optional callable ``(url) -> bool``. When supplied, a hook
            whose citation fails it is discarded (returns ``None``). The network
            CLI wires a real HEAD check here; the pure path leaves it unset.

    Returns:
        A well-formed, cited :class:`Enrichment`, or ``None`` when the model
        declined, the reply was malformed/uncited, or the citation failed
        verification. On ``None`` the caller keeps the item unchanged.

    This never raises for a model/transport error — enrichment is fail-soft, so a
    flaky call simply yields ``None`` and the item is published as-is.
    """
    title = _clean(item.get("title"))
    body = _clean(item.get("body") or item.get("summary") or item.get("content"))
    if not title and not body:
        # Nothing to enrich against — skip WITHOUT spending an LLM call, exactly as
        # image_gag skips an empty item.
        return None

    client = llm if llm is not None else default_llm()
    prompt = _ENRICH_PROMPT.format(topic=_clean(topic) or "the topic at hand",
                                   title=title, body=body[:1200])

    # ── The judgement call — anything it throws becomes a decline, never a crash ──
    try:
        response = client.complete(prompt)
    except Exception as exc:  # noqa: BLE001 — a failed hook must never sink the caller
        logger.warning("[enrich] LLM call failed for %r: %s", title[:60], exc)
        return None

    data = _extract_json(response.text)
    if not data:
        logger.warning("[enrich] unparseable reply for %r", title[:60])
        return None

    # ── Integrity gate: real, well-formed, and CITED, or nothing ──
    # An explicit decline is the honourable path — respect it silently.
    if data.get("found") is False:
        logger.info("[enrich] model declined (no relevant recent hook) for %r", title[:60])
        return None

    headline = _clean(data.get("headline"))
    tie_in = _clean(data.get("tie_in"))
    source_url = _clean(data.get("source_url"))

    if not headline or not tie_in:
        logger.warning("[enrich] incomplete hook (missing headline/tie_in) for %r", title[:60])
        return None
    if not _looks_like_citation(source_url):
        # No real citation → treat as a fabrication risk and drop it. This is the
        # integrity-over-output choice in one line: we would rather ship no hook.
        logger.warning("[enrich] rejecting uncited/placeholder source %r for %r",
                       source_url, title[:60])
        return None
    if verify_url is not None:
        try:
            if not verify_url(source_url):
                logger.warning("[enrich] citation failed verification: %s", source_url)
                return None
        except Exception as exc:  # noqa: BLE001 — a broken verifier must not fabricate a pass
            logger.warning("[enrich] verifier raised for %s: %s", source_url, exc)
            return None

    return Enrichment(
        headline=headline,
        tie_in=tie_in,
        source_url=source_url,
        model_used=response.model,
    )


# ─────────────────────────────────────────────────────────────────────────────
# The REAL client — imported lazily so the module needs no heavy deps to import
# ─────────────────────────────────────────────────────────────────────────────
# TUTORIAL: this mirrors providers/litellm.get_litellm_llm + run_with_fallback in
# the CraicGPT sibling, kept self-contained so shared/enrich/ is portable. The
# langchain_openai SDK is imported INSIDE .complete(), never at module top, so the
# offline tests (which inject a stub) never touch it.


class _LiteLLMClient:
    """A LiteLLM-routed :class:`LLMClient` with a local-first, cross-box fallback.

    There is no frontier route anywhere in this system: "fallback" means the OTHER
    grazlab box (the MLX sibling of the same weights), not a hosted API. If both
    routes fail, ``complete`` raises — and :func:`enrich_item` turns that into a
    clean ``None``.
    """

    def __init__(self, local_model: str, fallback_model: str,
                 base_url: str, api_key: str) -> None:
        self._local = local_model
        self._fallback = fallback_model
        self._base_url = base_url
        self._api_key = api_key

    def _invoke(self, model: str, prompt: str) -> str:
        # Lazy import: keeps `import shared.enrich.enrich` dependency-free.
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=model,
            base_url=self._base_url,
            api_key=self._api_key,
            temperature=0.4,
            max_tokens=800,
            timeout=float(os.getenv("ENRICH_REQUEST_TIMEOUT", "120")),
            max_retries=2,
            # Qwen routes otherwise emit a long <think> preamble that eats the budget.
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        resp = llm.invoke(prompt)
        return resp.content if isinstance(resp.content, str) else str(resp.content)

    def complete(self, prompt: str) -> LLMResponse:
        try:
            return LLMResponse(text=self._invoke(self._local, prompt), model=self._local)
        except Exception as exc:  # noqa: BLE001 — cross over to the other box
            logger.warning("[enrich] local route %s failed (%s); crossing to %s",
                           self._local, exc, self._fallback)
            return LLMResponse(text=self._invoke(self._fallback, prompt), model=self._fallback)


def default_llm() -> LLMClient:
    """Factory for the production LLM client — routes read from env at call time.

    No module-level singleton: each call reads the current env, so a deployment or
    a test that flips ``ENRICH_MODEL`` gets the new route without a re-import.
    """
    local_model, fallback_model = _model_routes()
    return _LiteLLMClient(
        local_model=local_model,
        fallback_model=fallback_model,
        base_url=os.getenv("LITELLM_BASE_URL", DEFAULT_LITELLM_BASE_URL),
        api_key=os.getenv("LITELLM_API_KEY", DEFAULT_LITELLM_API_KEY),
    )
