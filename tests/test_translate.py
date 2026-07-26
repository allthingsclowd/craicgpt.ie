"""Tests for translate_paper — translating a finished English edition.

The LLM call is injected as ``generate(prompt) -> dict``, so this runs offline.
Covers: prose fields translated, mechanical fields (URLs/images/models/credits)
preserved verbatim, attribution stamped, source-language passthrough, the source
paper left unmutated, and per-section English fallback on a translation failure.
"""

import copy
import json
import re

from content_pipeline.generate.translate import translate_paper


def _english_paper():
    return {
        "date": "2026-06-08",
        "generated_at": "2026-06-08T05:00:00Z",
        "pipeline_version": "3.0",
        "edition": {"approved_by": None, "approved_at": None, "language": "en",
                    "available_languages": ["en", "de"]},
        "editors_brief": {"title": "Brief", "body": "The state of play."},
        "ai": {
            "headliner": {"title": "Big AI news", "standfirst": "Stand", "body": "Body text",
                          "source_url": "https://example.com/a", "image_url": "https://cdn/x.png",
                          "_text_model": "qwen"},
            "subarticles": [{"title": "Sub one", "body": "sub body",
                             "source_url": "https://example.com/s1"}],
            "shorts": [{"title": "Short one", "body": "short body",
                        "source_url": "https://example.com/sh1"}],
        },
        "fun": [{"title": "Funny", "body": "ha", "source": "Foil Arms and Hog",
                 "persona": "Jack Blarney",
                 "byline": "As told to The Craic Gazette by Jack Blarney",
                 "satire_disclaimer": "Satire. Not real.",
                 "source_url": "https://youtube.com/v", "image_url": "https://cdn/f.png"}],
        "about": {"title": "About", "body": "About body"},
        "layout": ["ai.headliner", "fun.0"],
        "context": {},
    }


_MARKER_RE = re.compile(r"^===T(\d+)===$", re.M)


def _items_from(prompt):
    """The marker-delimited items the real prompt sends, in order."""
    parts = _MARKER_RE.split(prompt)
    return [s.strip() for s in parts[2::2]]


def _fake_translate(prompt):
    """A deterministic stand-in translator speaking the REAL wire protocol: marker
    text in, marker text out, every item prefixed 'DE:'.

    This fake is the point of the change. The old one took `prompt -> dict`, so it
    sat ABOVE the parse and no test could ever exercise the escaping contract that
    actually broke. Now the tests go through the same _parse_items the model does.
    """
    items = _items_from(prompt)
    if not items:  # single-field fallback prompt carries no markers
        return "DE:" + prompt.split("\n\n")[-1].strip()
    return "\n\n".join(f"===T{i}===\nDE:{s}" for i, s in enumerate(items))


def test_translate_paper_translates_prose_keeps_mechanics():
    out = translate_paper(_english_paper(), "de", generate=_fake_translate)
    # Prose is translated...
    assert out["ai"]["headliner"]["title"] == "DE:Big AI news"
    assert out["ai"]["headliner"]["standfirst"] == "DE:Stand"
    assert out["ai"]["headliner"]["body"] == "DE:Body text"
    assert out["ai"]["subarticles"][0]["title"] == "DE:Sub one"
    assert out["ai"]["shorts"][0]["body"] == "DE:short body"
    assert out["fun"][0]["title"] == "DE:Funny"
    assert out["fun"][0]["satire_disclaimer"] == "DE:Satire. Not real."
    assert out["editors_brief"]["body"] == "DE:The state of play."
    assert out["about"]["title"] == "DE:About"
    # ...while every mechanical field is preserved byte-for-byte.
    assert out["ai"]["headliner"]["source_url"] == "https://example.com/a"
    assert out["ai"]["headliner"]["image_url"] == "https://cdn/x.png"   # SHARED English image
    assert out["ai"]["headliner"]["_text_model"] == "qwen"
    assert out["fun"][0]["source"] == "Foil Arms and Hog"              # creator credit kept
    assert out["fun"][0]["persona"] == "Jack Blarney"                  # persona name kept
    assert out["fun"][0]["source_url"] == "https://youtube.com/v"
    assert out["layout"] == ["ai.headliner", "fun.0"]


def test_translate_paper_stamps_attribution():
    out = translate_paper(_english_paper(), "de", generate=_fake_translate)
    assert out["edition"]["language"] == "de"
    assert out["edition"]["source_language"] == "en"
    assert out["edition"]["translated_by"]                 # the model name is recorded
    assert "translation_holds" not in out["edition"]


def test_translate_paper_source_language_passthrough():
    out = translate_paper(_english_paper(), "en", generate=_fake_translate)
    assert out["ai"]["headliner"]["title"] == "Big AI news"   # untouched
    assert "translated_by" not in out["edition"]
    assert out["edition"]["language"] == "en"


def test_translate_paper_does_not_mutate_source():
    en = _english_paper()
    snap = copy.deepcopy(en)
    translate_paper(en, "de", generate=_fake_translate)
    assert en == snap   # deep-copied → the English source is never touched


def test_one_bad_reply_no_longer_sinks_a_whole_section():
    """A single unusable reply used to revert the ENTIRE AI section to English — 13
    of an edition's 17 articles — because the section was one call. It is now
    per-item batches with a per-field retry, so a transient failure costs nothing."""
    calls = {"n": 0}

    def flaky(prompt):
        calls["n"] += 1
        if calls["n"] == 1:                # the first batch of the AI section
            raise ValueError("model JSON unparseable")
        return _fake_translate(prompt)

    out = translate_paper(_english_paper(), "de", generate=flaky)
    assert out["ai"]["headliner"]["title"] == "DE:Big AI news"   # recovered per field
    assert out["fun"][0]["title"] == "DE:Funny"
    assert "translation_holds" not in out["edition"]             # nothing was held


def test_a_section_that_cannot_translate_at_all_stays_english_and_is_held():
    """The fail-soft contract still stands: if NOTHING in a section comes back, the
    English text is kept and the section is named in translation_holds — which is
    what the Telegram alert and the coverage floor key off."""

    def dead_for_ai(prompt):
        # the AI section is translated first; fail every call it makes
        if "Big AI news" in prompt or "Sub one" in prompt or "Short one" in prompt \
                or "Stand" in prompt or "Body text" in prompt or "sub body" in prompt \
                or "short body" in prompt:
            raise ValueError("route down")
        return _fake_translate(prompt)

    out = translate_paper(_english_paper(), "de", generate=dead_for_ai)
    assert out["ai"]["headliner"]["title"] == "Big AI news"   # AI stayed English
    assert out["fun"][0]["title"] == "DE:Funny"               # other sections translated
    assert out["edition"]["translation_holds"] == ["ai"]      # and it is surfaced


# --- coverage: catching a paper that shipped as English -----------------------


def _paper_with(ai_title: str, fun_body: str) -> dict:
    return {
        "ai": {
            "headliner": {"title": ai_title, "standfirst": "Stand", "body": "Body"},
            "subarticles": [{"title": "Sub", "body": "SubBody"}],
            "shorts": [{"title": "Short", "body": "ShortBody"}],
        },
        "fun": [{"title": "Fun", "body": fun_body, "byline": "By", "satire_disclaimer": "Satire"}],
        "editors_brief": {"title": "Brief", "body": "BriefBody"},
        "about": {"title": "About", "body": "AboutBody"},
    }


def test_coverage_is_zero_when_nothing_was_translated():
    # THE failure this exists to catch: _merge_back leaves the English string in
    # place when a field is missing, so a wholly-failed translation is byte-identical
    # to a valid English paper and sails through validate_paper.
    from content_pipeline.generate.translate import translation_coverage

    english = _paper_with("Title", "FunBody")
    cov = translation_coverage(english, dict(english))
    assert cov["total"] > 0
    assert cov["translated"] == 0
    assert cov["ratio"] == 0.0


def test_coverage_is_one_when_everything_changed():
    from content_pipeline.generate.translate import translation_coverage

    english = _paper_with("Title", "FunBody")
    german = {
        "ai": {
            "headliner": {"title": "Titel", "standfirst": "Vorspann", "body": "Korpus"},
            "subarticles": [{"title": "Unter", "body": "UnterKorpus"}],
            "shorts": [{"title": "Kurz", "body": "KurzKorpus"}],
        },
        "fun": [
            {"title": "Spass", "body": "SpassKorpus", "byline": "Von", "satire_disclaimer": "Satire!"}
        ],
        "editors_brief": {"title": "Notiz", "body": "NotizKorpus"},
        "about": {"title": "Ueber", "body": "UeberKorpus"},
    }
    cov = translation_coverage(english, german)
    assert cov["ratio"] == 1.0
    assert cov["translated"] == cov["total"]


def test_coverage_tolerates_legitimately_identical_fields():
    # Brand names and short titles can legitimately survive translation unchanged,
    # so this must be a RATIO, never an exact-zero rule. Measured on a healthy live
    # edition: de scored 2/51 fields identical, es/it/ja/fr scored 0/51.
    from content_pipeline.generate.translate import translation_coverage

    english = _paper_with("CraicGPT", "FunBody")
    mostly = _paper_with("CraicGPT", "SpassKorpus")  # brand title kept, body translated
    mostly["ai"]["headliner"]["body"] = "Korpus"
    mostly["editors_brief"]["body"] = "NotizKorpus"
    cov = translation_coverage(english, mostly)
    assert 0.0 < cov["ratio"] < 1.0
    assert cov["identical_fields"]  # names the survivors, for the alert text


# --- the escaping bug this wire format exists to prevent -----------------------

# The real string from the live 2026-07-24 edition: a double quote, an apostrophe
# and a raw &amp; in one fun-desk body.
NASTY = ('Another upload from The Romesh Ranganathan Show. "Shanthi\'s Suspicions, '
         'Monkey Bites &amp; Stage Names"? Soft title.')


def test_the_old_json_contract_failed_two_ways_and_one_was_SILENT():
    """What a model actually produces when asked to hand-escape prose into JSON.

    The defect was never "the model is bad" — it was asking it to escape at all.
    Two distinct failures, and the second is the nastier one because nothing raises.
    """
    import pytest

    from content_pipeline.generate.translate import loads_lenient

    B = chr(92)  # a literal backslash, spelled out so this test cannot be mis-escaped

    # 1. HARD failure — an apostrophe comes back as \' which is not legal JSON.
    #    This is what froze thegeekwiththepeak's it/ja editions for 22 days.
    with pytest.raises(ValueError):
        loads_lenient('["Shanthi' + B + "'" + 's Suspicions"]')
    with pytest.raises(ValueError):
        loads_lenient('["He said "detectportal" today]')  # unterminated

    # 2. SILENT corruption — over-escaped quotes PARSE, and the backslashes leak
    #    into the published prose. No exception, no hold, no alert: the reader just
    #    sees He said \"detectportal\" today.
    leaked = loads_lenient('["He said ' + B * 3 + '"detectportal' + B * 3 + '" today"]')
    assert leaked == ['He said ' + B + '"detectportal' + B + '" today']
    assert B in leaked[0], "the backslash reaches the reader — this is the quiet one"


def test_quotes_and_entities_survive_the_marker_protocol():
    """The same content through the new wire format: nothing is escaped, so nothing
    can be mis-escaped. The model sees the raw string and returns raw text."""
    seen = {}

    def spy(prompt):
        seen.setdefault("first", prompt)
        return _fake_translate(prompt)

    paper = _english_paper()
    paper["fun"][0]["body"] = NASTY
    out = translate_paper(paper, "de", generate=spy)

    assert "JSON" not in seen["first"]              # we never ask for JSON back
    assert out["fun"][0]["body"] == "DE:" + NASTY   # round-tripped intact
    assert '"Shanthi\'s Suspicions' in out["fun"][0]["body"]


def test_a_partial_reply_is_rejected_rather_than_misaligned():
    """Reusing a short reply would pair translations with the WRONG source fields —
    the silent corruption the old unstrict zip allowed. A partial batch must fall to
    the per-field retry instead."""
    def drops_last(prompt):
        items = _items_from(prompt)
        if not items:                                     # per-field fallback
            return "DE:" + prompt.split("\n\n")[-1].strip()
        kept = items[:-1] if len(items) > 1 else items    # lose one marker
        return "\n\n".join(f"===T{i}===\nDE:{s}" for i, s in enumerate(kept))

    out = translate_paper(_english_paper(), "de", generate=drops_last)
    # every field still correctly paired with its own translation
    assert out["ai"]["headliner"]["title"] == "DE:Big AI news"
    assert out["ai"]["headliner"]["standfirst"] == "DE:Stand"
    assert out["ai"]["headliner"]["body"] == "DE:Body text"


def test_an_items_fields_travel_together_in_one_call():
    """Per-ITEM batching, not per-character: a headliner's standfirst is a précis of
    its body, and a fun item's body/byline/satire_disclaimer are one comic voice, so
    splitting them across calls lets the register drift."""
    batches = []

    def spy(prompt):
        items = _items_from(prompt)
        if items:
            batches.append(items)
        return _fake_translate(prompt)

    translate_paper(_english_paper(), "de", generate=spy)
    head = next(b for b in batches if "Big AI news" in b)
    assert "Stand" in head and "Body text" in head        # headliner fields together
    fun = next(b for b in batches if "Funny" in b)
    assert "ha" in fun and "Satire. Not real." in fun     # fun item's voice together
