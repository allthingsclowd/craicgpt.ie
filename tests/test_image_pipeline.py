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


# ── The daily style rotation (#100) ───────────────────────────────────────────
from content_pipeline.generate.image_styles import (  # noqa: E402
    TEXT_CLAUSE,
    TEXT_STEP_FLOOR,
    assign_styles,
    negative_prompt_for,
    style_for_edition,
)

_A_FORTNIGHT = [f"2026-09-{d:02d}" for d in range(1, 15)]


def test_the_whole_edition_shares_one_style():
    """Graham's call: rotate daily, not within an edition — a paper whose every
    picture is a different art style reads as incoherent."""
    assert len({s["name"] for s in assign_styles(18, seed="2026-09-01")}) == 1


def test_consecutive_editions_never_repeat_a_style():
    """A hash-mod looked evenly distributed over a year but put SEVEN consecutive
    editions in plasticine. 'Rotate' means visit each in turn, so this counts days."""
    names = [style_for_edition(d)["name"] for d in _A_FORTNIGHT]
    assert all(a != b for a, b in zip(names, names[1:])), names


def test_the_rotation_is_even_over_a_full_cycle():
    cycle = len(STYLE_PRESETS)
    names = [style_for_edition(d)["name"] for d in _A_FORTNIGHT[:cycle]]
    assert len(set(names)) == cycle, "one full cycle must visit every style exactly once"


def test_re_running_a_date_reproduces_its_look():
    assert style_for_edition("2026-09-03")["name"] == style_for_edition("2026-09-03")["name"]


def test_a_non_date_seed_still_yields_a_style():
    """Tests and ad-hoc calls pass arbitrary seeds; there is no sequence to preserve."""
    assert style_for_edition("not-a-date") in STYLE_PRESETS


def test_every_preset_is_a_cartoon_with_no_sharp_edges():
    """The brief was funny, colourful and round. Guard against a photoreal preset
    creeping back in the way `editorial-photo` used to lead the rotation."""
    for s in STYLE_PRESETS:
        assert "photorealistic" not in s["descriptor"].lower(), s["name"]
        assert any(w in s["descriptor"].lower() for w in ("cartoon", "comic", "claymation")), s["name"]


# ── The text policy (#106) ────────────────────────────────────────────────────


def test_the_hero_prompt_permits_a_bubble_and_the_others_stay_wordless():
    p_hero = build_image_prompt({"title": "T", "body": "b"}, _STYLE, "a gag", HERO)
    assert "letter them onto a surface" in p_hero
    for spec in (STANDARD, THUMBNAIL):
        p = build_image_prompt({"title": "T", "body": "b"}, _STYLE, "a gag", spec)
        assert "purely visual scene" in p
        assert "letter them onto a surface" not in p


def test_omitting_the_spec_stays_wordless():
    """Fail SAFE: an un-specced call must not accidentally licence lettering."""
    assert "purely visual scene" in build_image_prompt({"title": "T"}, _STYLE, "a gag")




def test_the_text_clause_keeps_it_short():
    """Five words is FLUX.2's documented reliability limit per quoted block, not taste."""
    assert "FIVE words" in TEXT_CLAUSE


def test_generate_images_gives_the_hero_a_text_budget_and_shorts_none(monkeypatch):
    from content_pipeline.agent import editor_in_chief as eic

    monkeypatch.setattr("content_pipeline.generate.image_gag.build_gag", lambda item, **kw: "g")
    prompts = []
    ai = {"headliner": {"title": "H", "body": "b"}, "subarticles": [],
          "shorts": [{"title": "S", "body": "b"}]}
    eic._generate_images(ai, [], "2026-09-01",
                         generate=lambda p: prompts.append(p) or ("/tmp/x.png", "m"))
    assert "letter them onto a surface" in prompts[0], "the headliner may letter a bubble"
    assert "purely visual scene" in prompts[1], "a 512px short must stay wordless"


# ── The edition's style reaches the reader (#100 tutorial payoff) ─────────────
def test_every_preset_has_a_human_label():
    """The footer shows the label, not the slug — 'Beano-style British comic', not
    'beano-comic'."""
    for s in STYLE_PRESETS:
        assert s.get("label"), s["name"]
        assert s["label"] != s["name"]


def test_the_trace_covers_every_illustrated_slot_including_shorts():
    """Regression: `_trace_images` built its own literal list of slots and omitted the
    shorts — the same mistake publish.py made. A slot missing here is generated and
    published but INVISIBLE in the Under-the-Hood drawer, which is the one surface a
    tutorial reader uses to see what the pipeline did.
    """
    from content_pipeline.agent.editor_in_chief import _trace_images
    from content_pipeline.agent.trace import TraceRecorder

    def _art(t):
        return {"title": t, "image_url": "/tmp/x.png", "_image_style": "beano-comic",
                "_image_tier": "thumbnail", "image_alt": t}

    ai = {"headliner": _art("H"), "subarticles": [_art("S1")], "shorts": [_art(f"sh{i}") for i in range(10)]}
    rec = TraceRecorder()
    _trace_images(rec, ai, [_art("f1")], "m3/comfy/flux-2-dev")
    drawn = [e for e in rec.as_list() if e.get("name") == "generate_image"]
    assert len(drawn) == 13, f"expected every slot traced, got {len(drawn)}"


# ── The image client must out-wait the slowest render (2026-08-26 incident) ───
# The openai SDK defaults to a 600 s read timeout. A 28-step flux render takes ~720 s.
# On 2026-08-26 that mismatch cost a whole edition: every hero image hung up mid-render,
# silently fell back to qwen-image, and left ComfyUI finishing the abandoned job — two
# images in 129 minutes before the run was terminated. These are the guards.
def test_the_image_client_sets_an_explicit_timeout():
    """Without this the SDK default (600 s) applies and every hero image falls back."""
    from content_pipeline.generate import images as I

    client = I._default_client()
    assert client.timeout is not None, "no timeout set — the SDK's 600 s default will apply"


def test_the_image_timeout_outlasts_the_slowest_tier():
    """THE regression assertion. A tier whose render outruns the client is a silent
    fallback, not an error — you get a picture from a route nobody chose."""
    from content_pipeline.content_config import content_cfg

    slowest = max(HERO.est_seconds, STANDARD.est_seconds, THUMBNAIL.est_seconds)
    assert content_cfg.image_request_timeout > slowest, (
        f"image_request_timeout={content_cfg.image_request_timeout}s does not cover the "
        f"slowest tier ({slowest:.0f}s) — raise it or lower the tier"
    )


def test_the_image_timeout_matches_the_rest_of_the_path():
    """Every other hop allows 1800 s (LiteLLM image routes, nginx, the ComfyUI shim's
    1500 s queue wait). The client should not be the tightest link again."""
    from content_pipeline.content_config import content_cfg

    assert content_cfg.image_request_timeout >= 1800


def test_the_image_timeout_is_env_tunable(monkeypatch):
    """Same convention as GENERATE_TIMEOUT_S — a degraded day is tuned without a redeploy."""
    from content_pipeline.content_config import ContentConfig

    monkeypatch.setenv("IMAGE_REQUEST_TIMEOUT", "2400")
    assert ContentConfig().image_request_timeout == 2400.0


def test_the_chat_timeout_is_not_reused_for_images():
    """CONTENT_REQUEST_TIMEOUT is 180 s — three minutes. Pointing the image client at it
    would reintroduce the bug in a worse form."""
    from content_pipeline.content_config import content_cfg

    assert content_cfg.image_request_timeout != content_cfg.request_timeout


# ── FLUX.2 hates negation — every prompt fragment must be positive ────────────
# Black Forest Labs: "FLUX.2 does not support negative prompts. Always describe what you
# want, not what you want to avoid." The Mistral encoder treats negation as semantically
# LOADED — their worked example is that "without glasses" renders glasses. On 2026-08-26 our
# nine-NO text ban coincided with every style candidate rendering a "STOP" sign anyway.
_NEGATION = __import__("re").compile(r"\b(no|not|never|without|avoid|zero)\b", __import__("re").I)


def _fragments():
    from content_pipeline.generate import image_styles as st

    yield "NO_TEXT_CLAUSE", st.NO_TEXT_CLAUSE
    yield "TEXT_CLAUSE", st.TEXT_CLAUSE
    yield "_MOTO_IMAGE_CLAUSE", st._MOTO_IMAGE_CLAUSE
    for p in st.STYLE_PRESETS:
        yield f"preset:{p['name']}", p["descriptor"]


def test_no_prompt_fragment_uses_english_negation():
    offenders = {name: _NEGATION.findall(text) for name, text in _fragments()
                 if _NEGATION.search(text)}
    assert not offenders, (
        f"negation found in {offenders} — FLUX.2's encoder reads these as things to DRAW. "
        "Rewrite positively: say what should be in the frame."
    )


def test_the_negative_prompt_is_empty():
    """Guidance-distilled models have no unconditional pass to attach one to."""
    from content_pipeline.generate.image_styles import HERO, STANDARD, negative_prompt_for

    for spec in (HERO, STANDARD, None):
        assert negative_prompt_for(spec) == ""


def test_the_gag_alone_is_the_scene():
    """The headline must not be handed to the model as renderable text — on 2026-08-26 it
    lettered a 13-word headline into a speech bubble, well past the 5-word reliability limit."""
    from content_pipeline.generate.image_styles import HERO, build_image_prompt

    long_title = "Mistral's Saudi Gamble The Sovereign AI Playbook Goes To The Gulf"
    p = build_image_prompt({"title": long_title, "body": "b"}, _STYLE, "a chef serves a brain", HERO)
    assert long_title not in p
    assert "a chef serves a brain" in p


def test_the_text_clause_asks_for_quoted_words_on_a_surface():
    """FLUX.2 paints letters onto objects; it needs the string quoted and bound to a surface."""
    from content_pipeline.generate.image_styles import TEXT_CLAUSE

    assert "quotes" in TEXT_CLAUSE
    assert "FIVE words" in TEXT_CLAUSE


def test_the_image_client_does_not_retry_expensive_renders():
    """SDK default is 2 retries; each one launches a fresh 12-minute GPU render."""
    from content_pipeline.generate import images as I

    assert I._default_client().max_retries == 0


def test_only_the_hero_opts_into_text():
    """Graham's call: text on the HERO images. It is an editorial choice about the page,
    not a by-product of the step count — raising the cheap tiers to 20 steps on
    2026-08-26 silently switched text on everywhere until this was made explicit."""
    assert HERO.allows_text
    assert not STANDARD.allows_text
    assert not THUMBNAIL.allows_text


def test_any_tier_allowing_text_has_enough_steps_to_letter_it():
    """The physical constraint that survives: below ~20 steps FLUX letterforms mangle."""
    for spec in (HERO, STANDARD, THUMBNAIL):
        if spec.allows_text:
            assert spec.steps >= TEXT_STEP_FLOOR, f"{spec} lets text through at {spec.steps} steps"


def test_no_tier_under_samples_flux():
    """FLUX.2 [dev] targets 20-50 steps. The 8-step tiers shipped missing limbs and
    garbled lettering on 2026-08-26; 20 is the floor now, for every tier."""
    for spec in (HERO, STANDARD, THUMBNAIL):
        assert spec.steps >= 20, f"{spec} under-samples FLUX.2 at {spec.steps} steps"
