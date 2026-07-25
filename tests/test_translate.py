"""Tests for translate_paper — translating a finished English edition.

The LLM call is injected as ``generate(prompt) -> dict``, so this runs offline.
Covers: prose fields translated, mechanical fields (URLs/images/models/credits)
preserved verbatim, attribution stamped, source-language passthrough, the source
paper left unmutated, and per-section English fallback on a translation failure.
"""

import copy
import json

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


def _fake_translate(prompt):
    """A deterministic stand-in translator: prefixes every string value with 'DE:',
    preserving the exact shape the real prompt sends."""
    payload = json.loads(prompt.split("JSON to translate:\n", 1)[1])

    def tr(v):
        if isinstance(v, str):
            return "DE:" + v
        if isinstance(v, list):
            return [tr(x) for x in v]
        if isinstance(v, dict):
            return {k: tr(x) for k, x in v.items()}
        return v

    return tr(payload)


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


def test_translate_paper_section_failure_falls_back_to_english():
    calls = {"n": 0}

    def flaky(prompt):
        calls["n"] += 1
        if calls["n"] == 1:                # the AI section is translated first
            raise ValueError("model JSON unparseable")
        return _fake_translate(prompt)

    out = translate_paper(_english_paper(), "de", generate=flaky)
    assert out["ai"]["headliner"]["title"] == "Big AI news"   # AI stayed English
    assert out["fun"][0]["title"] == "DE:Funny"               # other sections translated
    assert out["edition"]["translation_holds"] == ["ai"]      # the fallback is surfaced


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
