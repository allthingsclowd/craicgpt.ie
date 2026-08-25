"""The cartoon image pipeline: render tiers, the visual-gag step, and the plumbing.

Covers issues #101 (fit 18 images in the budget), #102 (the gag step) and #103
(cartoons on the AI shorts). All offline — the image and LLM calls are injected.

`image_styles.py` had no test file at all before this work, so the tier table and
the prompt composition are getting their first coverage here.
"""

import pytest

from content_pipeline.generate.image_gag import build_gag
from content_pipeline.generate.image_styles import (
    HERO,
    NEGATIVE_PROMPT,
    STANDARD,
    STYLE_PRESETS,
    THUMBNAIL,
    build_image_prompt,
    render_spec_for,
)

_STYLE = {"name": "test", "descriptor": "A bold cartoon"}


# ── Render tiers (#101) ───────────────────────────────────────────────────────
def test_the_three_tiers_are_distinct_and_ordered_by_cost():
    assert HERO.steps > STANDARD.steps == THUMBNAIL.steps
    assert HERO.size == STANDARD.size != THUMBNAIL.size
    assert HERO.est_seconds > STANDARD.est_seconds > THUMBNAIL.est_seconds


@pytest.mark.parametrize("tier,spec", [("hero", HERO), ("standard", STANDARD),
                                       ("thumbnail", THUMBNAIL)])
def test_render_spec_lookup(tier, spec):
    assert render_spec_for(tier) is spec


def test_an_unknown_tier_costs_a_middling_image_rather_than_crashing():
    """A new slot type appearing upstream must not sink an edition."""
    assert render_spec_for("something-new") is STANDARD


def test_every_size_is_a_multiple_of_16():
    """The ComfyUI shim 400s otherwise — it is the one hard constraint on size (#105)."""
    for spec in (HERO, STANDARD, THUMBNAIL):
        w, _, h = spec.size.partition("x")
        assert int(w) % 16 == 0 and int(h) % 16 == 0, spec.size


def test_a_full_edition_fits_the_generate_task_cap():
    """THE budget assertion. 3 hero + 5 standard + 10 thumbnails, plus the measured
    ~45 min non-image half, must fit `craicgpt_generate_daily`'s 11,400 s cap with
    room for a bad day. At an all-hero 28 steps this would be 3h38m and blow it."""
    images = 3 * HERO.est_seconds + 5 * STANDARD.est_seconds + 10 * THUMBNAIL.est_seconds
    non_image_worst = 70 * 60          # slowest generate observed in 12 days of history
    assert images + non_image_worst < 11_400, f"{(images + non_image_worst) / 60:.0f} min"


# ── Prompt composition (#102) ─────────────────────────────────────────────────
def test_a_gag_becomes_the_scene():
    p = build_image_prompt({"title": "OpenAI slows down", "body": "b"}, _STYLE,
                           "a robot brain skidding to a halt")
    assert "a robot brain skidding to a halt" in p
    assert "A bold cartoon" in p


def test_without_a_gag_we_still_get_a_usable_prompt():
    """A missing gag must cost wit, never an image — validate_paper requires one."""
    p = build_image_prompt({"title": "T", "body": "the body text"}, _STYLE, None)
    assert "T" in p and "the body text" in p


def test_the_negative_prompt_covers_roundness_and_text():
    for term in ("sharp edges", "angular", "photorealistic", "text", "watermark"):
        assert term in NEGATIVE_PROMPT


def test_presets_are_wellformed():
    assert STYLE_PRESETS
    for s in STYLE_PRESETS:
        assert s["name"] and s["descriptor"]


# ── The gag step (#102) ───────────────────────────────────────────────────────
def _gen(gag):
    return lambda prompt: {"gag": gag}


def test_build_gag_returns_the_line():
    assert build_gag({"title": "T", "body": "B"}, generate=_gen("a funny thing")) == "a funny thing"


def test_build_gag_tells_the_model_when_it_is_a_motorcycle():
    """The vertical is passed IN, never inferred — a model asked to guess draws a car."""
    seen = []

    def gen(prompt):
        seen.append(prompt)
        return {"gag": "g"}

    build_gag({"title": "T", "body": "B", "_vertical": "moto"}, generate=gen)
    assert "MOTORCYCLE STORY" in seen[0]
    seen.clear()
    build_gag({"title": "T", "body": "B", "_vertical": "comedy"}, generate=gen)
    assert "MOTORCYCLE STORY" not in seen[0]


@pytest.mark.parametrize("bad", [
    lambda p: (_ for _ in ()).throw(RuntimeError("engine down")),   # raises
    lambda p: {"gag": "   "},                                       # blank
    lambda p: {},                                                   # missing field
    lambda p: None,                                                 # nothing at all
])
def test_build_gag_is_fail_soft(bad):
    """Never raises. The caller falls back to the literal prompt and still gets art."""
    assert build_gag({"title": "T", "body": "B"}, generate=bad) is None


def test_build_gag_skips_an_empty_item_without_calling_the_model():
    called = []
    build_gag({}, generate=lambda p: called.append(p) or {"gag": "x"})
    assert called == []


# ── The harness wiring (#102 / #103) ──────────────────────────────────────────
def test_generate_images_stamps_the_gag_and_tier(monkeypatch):
    from content_pipeline.agent import editor_in_chief as eic

    monkeypatch.setattr("content_pipeline.generate.image_gag.build_gag",
                        lambda item, **kw: f"gag for {item['title']}")
    ai = {"headliner": {"title": "H", "body": "b"}, "subarticles": [],
          "shorts": [{"title": "S", "body": "b"}]}
    eic._generate_images(ai, [], "2026-08-25", generate=lambda p: ("/tmp/x.png", "m"))

    assert ai["headliner"]["_image_gag"] == "gag for H"
    assert ai["headliner"]["_image_tier"] == "hero"
    assert ai["shorts"][0]["_image_tier"] == "thumbnail"
    # The gag doubles as alt text — better for a screen reader than the headline,
    # because it describes what is actually in the picture.
    assert ai["headliner"]["image_alt"] == "gag for H"


def test_a_failed_image_clears_the_url_rather_than_raising(monkeypatch):
    from content_pipeline.agent import editor_in_chief as eic

    monkeypatch.setattr("content_pipeline.generate.image_gag.build_gag", lambda item, **kw: "g")

    def boom(prompt):
        raise RuntimeError("comfy down")

    ai = {"headliner": {"title": "H", "body": "b"}, "subarticles": [], "shorts": []}
    eic._generate_images(ai, [], "2026-08-25", generate=boom)
    assert ai["headliner"]["image_url"] is None


# ── save_image: the render spec reaches the wire, and names the file (#103) ────
def test_save_image_forwards_the_render_spec(monkeypatch, tmp_path):
    from content_pipeline.generate import images as I

    seen = {}

    def fake_generate_image(prompt, **kw):
        seen.update(kw)
        return I.GeneratedImage(model="m", prompt=prompt, b64_png="aGk=")

    monkeypatch.setattr(I, "generate_image", fake_generate_image)
    monkeypatch.setattr(I.content_cfg, "image_dir", str(tmp_path))
    I.save_image("p", size="512x512", steps=8, negative_prompt="no cars")
    assert seen["size"] == "512x512"
    assert seen["steps"] == 8
    assert seen["negative_prompt"] == "no cars"


def test_the_same_prompt_at_two_tiers_does_not_collide(monkeypatch, tmp_path):
    """The filename hashes the prompt AND the spec.

    Hashing the prompt alone would make a 512px thumbnail and a 1024px hero of the
    same story share a file, and whichever rendered first would win silently.
    """
    from content_pipeline.generate import images as I

    monkeypatch.setattr(I, "generate_image",
                        lambda prompt, **kw: I.GeneratedImage(model="m", prompt=prompt, b64_png="aGk="))
    monkeypatch.setattr(I.content_cfg, "image_dir", str(tmp_path))
    hero, _ = I.save_image("same prompt", size="1024x1024", steps=28)
    thumb, _ = I.save_image("same prompt", size="512x512", steps=8)
    assert hero != thumb


def test_extra_body_carries_the_params_and_omits_them_when_unset():
    """steps/seed/negative_prompt are not typed SDK kwargs — they must ride extra_body
    or they are dropped before the wire, and the shim would return a full-cost image
    with HTTP 200 regardless (#105)."""
    from content_pipeline.generate import images as I

    calls = []

    class _Img:
        b64_json = "aGk="
        url = None

    class _Resp:
        data = [_Img()]

    class _Client:
        class images:
            @staticmethod
            def generate(**kw):
                calls.append(kw)
                return _Resp()

    I.generate_image("p", model="r", steps=8, seed=7, negative_prompt="no cars", client=_Client())
    assert calls[0]["extra_body"] == {"steps": 8, "seed": 7, "negative_prompt": "no cars"}

    calls.clear()
    I.generate_image("p", model="r", client=_Client())
    assert "extra_body" not in calls[0], "an unset spec must not send an empty extra_body"
