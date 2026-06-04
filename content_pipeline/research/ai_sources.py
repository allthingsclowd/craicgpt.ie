"""
content_pipeline/research/ai_sources.py
========================================
Curated AI-source registry — the high-signal feeds the AI desk harvests daily.

Graham's hand-picked source list (companies/labs, thought leaders, publications).
We keep the RSS/Atom feed URL for each source that publishes one; ``feeds.harvest``
pulls recent items deterministically so the AI desk always has a rich pool of
REAL, dated sources to rank (no LLM under-searching, no fabrication).

Each entry is ``(source_name, feed_url)``. Dead/changed feeds are skipped at
runtime, so a stale URL degrades gracefully. The set below is the subset of
Graham's list that exposes a working public feed (verified at build time).

Known gaps (no usable public feed → handled elsewhere / future enhancement):
- **X / Twitter** feeds — no reliable free API; the agentic researcher still
  surfaces notable posts via Brave search.
- **YouTube** channels — need channel-id resolution + a transcript fetch; the
  recent-video feed is a future enhancement (``?channel_id=`` Atom feeds).
- Several company pages don't publish a stable public RSS feed (Anthropic, xAI,
  Mistral, Meta AI, Stability, Cohere, Midjourney, Perplexity, Runway, Inflection,
  Scale) — their news still arrives via the publications below (TechCrunch /
  VentureBeat / The Verge / Ars / Wired) and the agentic researcher's Brave search.
"""

from __future__ import annotations

# ── Company / lab news + engineering blogs ────────────────────────────────────
_COMPANIES: list[tuple[str, str]] = [
    ("OpenAI", "https://openai.com/news/rss.xml"),
    ("Google AI", "https://blog.google/technology/ai/rss/"),
    ("Google DeepMind", "https://deepmind.google/blog/rss.xml"),
    ("Microsoft AI", "https://blogs.microsoft.com/ai/feed/"),
    ("Meta AI", "https://ai.meta.com/blog/rss/"),
    ("Hugging Face", "https://huggingface.co/blog/feed.xml"),
    ("BAIR (Berkeley AI)", "https://bair.berkeley.edu/blog/feed.xml"),
]

# ── Thought leaders — personal blogs + Substacks ──────────────────────────────
_LEADERS: list[tuple[str, str]] = [
    ("Sam Altman", "https://blog.samaltman.com/posts.atom"),
    ("Gary Marcus", "https://garymarcus.substack.com/feed"),
    ("Ethan Mollick", "https://www.oneusefulthing.org/feed"),
    ("Import AI — Jack Clark", "https://importai.substack.com/feed"),
    ("Lex Fridman", "https://lexfridman.com/feed/"),
    ("Simon Willison", "https://simonwillison.net/atom/everything/"),
]

# ── Publications — the reliable volume sources ────────────────────────────────
_PUBLICATIONS: list[tuple[str, str]] = [
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
    ("Wired AI", "https://www.wired.com/feed/tag/ai/latest/rss"),
    ("MIT Technology Review AI", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
    ("arXiv cs.AI", "http://export.arxiv.org/rss/cs.AI"),
    ("arXiv cs.LG", "http://export.arxiv.org/rss/cs.LG"),
    ("IEEE Spectrum AI", "https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss"),
    ("MarkTechPost", "https://www.marktechpost.com/feed/"),
    ("Synced", "https://syncedreview.com/feed/"),
    ("Towards Data Science", "https://towardsdatascience.com/feed"),
    ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("Ars Technica AI", "https://arstechnica.com/ai/feed/"),
]

# The full harvest set. Order doesn't matter — harvest caps per-feed and the LLM
# ranks by significance afterwards.
AI_FEEDS: list[tuple[str, str]] = _COMPANIES + _LEADERS + _PUBLICATIONS
