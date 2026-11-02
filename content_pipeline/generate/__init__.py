"""Generation modules for the daily content engine.

- ``personas``: parody-journalist roster (celebrity/political voices) for the
  fun-news rewriter.
- ``ai_writer``: Graham's cynical/witty voice for the AI-landscape articles.
- ``images``: Qwen-Image 2.1 / 2.1-Turbo image generation via the LiteLLM proxy
  (per-tier routes, per-image fallback and deadline).
- ``image_preflight``: the read-only memory pre-flight on the M3 render slot.
"""
