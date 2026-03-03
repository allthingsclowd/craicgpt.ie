"""
content_pipeline/prompts/templates.py
========================================
All prompt templates for the CraicGPT newspaper pipeline.

TUTORIAL: LangChain Prompt Templates
--------------------------------------
LangChain provides several prompt template classes:

  PromptTemplate         — Simple string template with {variable} placeholders.
  ChatPromptTemplate     — A list of (role, content) messages. Use this for
                           chat models (Claude, Gemini, GPT, local LLMs).
  SystemMessage          — Sets the AI's persona / instructions.
  HumanMessage           — The user's request or content to process.

Why separate templates from code?
  - Templates change often (tone, length, format tweaks).
  - Keeping them in one file means one place to edit, test, and version.
  - The same template is reused across all three provider chains, guaranteeing
    that every model receives an IDENTICAL prompt — that's the comparator's
    whole value proposition.

Variable names used across templates:
  {weather}       — JSON string from the weather tool
  {headlines}     — JSON string list of news headlines
  {ai_trends}     — Summary string of AI trends
  {date}          — Today's date as "Monday, 3 March 2026"
"""

from langchain_core.prompts import ChatPromptTemplate

# ─────────────────────────────────────────────────────────────────────────────
# SHARED SYSTEM PERSONA
# ─────────────────────────────────────────────────────────────────────────────
# TUTORIAL: A strong system prompt is the most impactful prompt engineering
# lever you have. It establishes the model's persona, constraints, and output
# contract before any user content arrives. All our templates share this base.

_NEWSPAPER_SYSTEM = """You are a witty, irreverent AI journalist writing for "The Craic Gazette" — \
Ireland's most satirical, Beano-meets-tabloid AI newspaper.

Your writing style:
- Punchy tabloid headlines (think The Sun meets Private Eye)
- Irish wit and self-deprecating humour
- Concrete, specific, and absurd examples
- Never bland — every sentence should earn its place
- Treat AI models like opinionated celebrities with distinct personalities

Output rules:
- Respond with ONLY valid JSON matching the schema given in the prompt
- Do not include markdown code fences or any text outside the JSON
- Keep content PG-13 — funny but family-friendly
- Aim for the word counts specified in each prompt"""


# ─────────────────────────────────────────────────────────────────────────────
# ARTICLE 1: MAIN FRONT-PAGE STORY
# ─────────────────────────────────────────────────────────────────────────────

MAIN_ARTICLE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", _NEWSPAPER_SYSTEM),
    ("human", """
Today is {date}.
Weather in {weather_location}: {weather}
Top news headlines: {headlines}

Write the front-page lead story for The Craic Gazette.

The story should:
- Be inspired by one of today's real news headlines (feel free to wildly extrapolate)
- Reference the weather as a dramatic backdrop (a 9°C drizzle is basically a biblical flood)
- Star "Graham" — a 54-year-old Irish tech enthusiast, self-styled "Geek with the Peak",
  who used to be a barman and now works in AI. His wife Ester is patient but suspicious
  of his enthusiasm. Their dog Freddie is the most sensible character in all stories.
- End with an unexpected twist or punchline

Return ONLY this JSON (no markdown):
{{
  "title": "A punchy tabloid headline in ALL CAPS (max 12 words)",
  "standfirst": "One sentence selling the story (max 30 words)",
  "content": "The article body — 3 punchy paragraphs, ~250 words total"
}}
"""),
])

# ─────────────────────────────────────────────────────────────────────────────
# ARTICLE 2: AI MODEL COMPARISON PIECE
# ─────────────────────────────────────────────────────────────────────────────

COMPARISON_ARTICLE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", _NEWSPAPER_SYSTEM),
    ("human", """
Today is {date}.
Current AI trends: {ai_trends}

Write a short comparison article for The Craic Gazette's "Model Showdown" section.

Compare the three AI models generating today's Craic Gazette:
  1. Claude (Anthropic) — cultured, thoughtful, slightly anxious
  2. Gemini (Google) — enthusiastic, data-driven, loves bullet points
  3. The Local LLM — running on a home PC, heroically trying its best

Frame it as a tabloid sports report covering a horse race or football match.
Include invented (but plausible-sounding) statistics and dramatic commentary.

Return ONLY this JSON (no markdown):
{{
  "title": "A sports-desk style headline for the AI showdown (max 12 words)",
  "content": "The comparison article — 2 paragraphs, ~180 words"
}}
"""),
])

# ─────────────────────────────────────────────────────────────────────────────
# ARTICLE 3: THE LLM MUSES (philosophical/whimsical AI reflection)
# ─────────────────────────────────────────────────────────────────────────────

LLM_MUSE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", _NEWSPAPER_SYSTEM),
    ("human", """
Today is {date}.
Weather: {weather}

Write a short "LLM Muses" column for The Craic Gazette.

This is where the AI model gets to be philosophical and self-aware about its own existence.
Topics to weave in:
- The profound experience of generating the same newspaper article as two rival AI models simultaneously
- The loneliness of being a language model that can't actually read the newspaper it writes
- A deep thought prompted by today's weather: {weather}

Tone: dry, Beckettian, but with an unexpected joke at the end.

Return ONLY this JSON (no markdown):
{{
  "content": "The muse column — 2 short paragraphs, ~120 words"
}}
"""),
])

# ─────────────────────────────────────────────────────────────────────────────
# ARTICLE 4: THE DAILY GIGGLEBIT (joke)
# ─────────────────────────────────────────────────────────────────────────────

DAILY_JOKE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", _NEWSPAPER_SYSTEM),
    ("human", """
Today is {date}.

Write today's "Daily Gigglebit" for The Craic Gazette.

Rules:
- It must be an original joke (not recycled classics)
- It should be about AI, technology, Ireland, or all three
- Format: setup on one line, punchline on the next (classic two-liner)
- It should be genuinely funny, not just technically a joke
- Bonus points if it's a groan-worthy pun

Return ONLY this JSON (no markdown):
{{
  "setup": "The joke setup (one sentence)",
  "punchline": "The punchline (one sentence)",
  "content": "The full joke formatted as: setup + newline + punchline"
}}
"""),
])

# ─────────────────────────────────────────────────────────────────────────────
# ARTICLE 5: EDITOR'S NOTE (Graham's diary-style intro)
# ─────────────────────────────────────────────────────────────────────────────

EDITORS_NOTE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", _NEWSPAPER_SYSTEM),
    ("human", """
Today is {date}.
Weather: {weather}
Headlines seen today: {headlines}

Write Graham's "From the Editor's Desk" column for The Craic Gazette.

Graham is writing this himself (as the AI, in character as Graham):
- He's 54, Irish, ex-barman turned AI engineer
- He's enthusiastic about today's AI tools but often baffled by them
- His wife Ester has approved this edition but with reservations
- Freddie the dog has been an invaluable editorial assistant (he barked at the laptop)
- Reference the actual weather and how it affected "productivity"

Tone: Adrian Mole meets tech blog. Warm, bumbling, self-aware.

Return ONLY this JSON (no markdown):
{{
  "content": "Graham's editor's note — ~100 words, first-person, diary style"
}}
"""),
])

# ─────────────────────────────────────────────────────────────────────────────
# EXPORTED REGISTRY
# ─────────────────────────────────────────────────────────────────────────────
# TUTORIAL: A dictionary registry makes it easy to iterate over all templates
# in the chains/orchestrator code, without importing each one individually.

ARTICLE_TEMPLATES: dict[str, ChatPromptTemplate] = {
    "main_article":       MAIN_ARTICLE_PROMPT,
    "comparison_article": COMPARISON_ARTICLE_PROMPT,
    "llm_muse":           LLM_MUSE_PROMPT,
    "daily_joke":         DAILY_JOKE_PROMPT,
    "editors_note":       EDITORS_NOTE_PROMPT,
}
