"""
shared.enrich
=============
Course-agnostic content-enhancement agent: attach a real, recent, CITED
real-world hook (a breach / CVE / campaign) to a course item, framed as a
teaching tie-in in Graham's voice.

Public surface — see :mod:`shared.enrich.enrich` for the full tutorial:

* :func:`enrich_item` — the entry point; returns an :class:`Enrichment` or
  ``None`` (integrity over output — it never fabricates).
* :class:`Enrichment` — the structured result (headline / tie_in / source_url /
  model_used).
* :class:`LLMClient`, :class:`LLMResponse` — the injectable LLM boundary.
* :func:`default_llm` — the production factory (LiteLLM, local-first + cross-box
  fallback, SDK imported lazily so this package imports with zero heavy deps).
"""

from __future__ import annotations

from shared.enrich.enrich import (
    DEFAULT_ENRICH_FALLBACK_MODEL,
    DEFAULT_ENRICH_MODEL,
    Enrichment,
    LLMClient,
    LLMResponse,
    default_llm,
    enrich_item,
)

__all__ = [
    "enrich_item",
    "Enrichment",
    "LLMClient",
    "LLMResponse",
    "default_llm",
    "DEFAULT_ENRICH_MODEL",
    "DEFAULT_ENRICH_FALLBACK_MODEL",
]
