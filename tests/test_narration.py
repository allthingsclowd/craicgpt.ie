"""The narration orchestrator: per-article audio + the gated dad↔son podcast.

All heavy deps (TTS, banter LLM, rubric judge) are injected, so this runs offline and
tests the wiring + the gate behaviour, not the models.
"""
from content_pipeline.generate import narration


def _sample():
    return {
        "ai": {
            "headliner": {"title": "Long Context", "body": "A lab gave its model a big memory.",
                          "source_url": "http://x"},
            "subarticles": [{"title": "Chips", "body": "A chip story.", "source_url": "http://y"}],
            "shorts": [{"title": "Short", "body": "A brief.", "source_url": "http://z"}],
        },
        "fun": [{"title": "Foil Arms", "body": "A sketch.", "source": "Foil Arms and Hog",
                 "source_url": "http://yt"}],
        "editors_brief": {"title": "The Brief", "body": "Today's edition in a nutshell."},
        "about": {"title": "About the Editor", "body": "Father Ted introduces Graham."},
        "layout": ["ai.headliner", "ai.subarticles.0", "ai.shorts.0", "fun.0"],
    }


def _fake_article(item, *, voice="graham", **kw):
    return (f"/tmp/{voice}-{item['title']}.mp3", "tts-model")


def _fake_build(paper, **kw):
    return {"turns": [("graham", "Welcome."), ("tom", "Howya!")],
            "script_text": "GRAHAM: Welcome.\nTOM: Howya!",
            "banter_text": "TOM: Howya!", "refs": ["ai.headliner"]}


def _approve(text, **kw):
    return {"verdict": "APPROVE", "reasons": [], "judge_model": "judge"}


def _fake_render(turns, **kw):
    return ("/tmp/podcast.mp3", "tts-model")


def test_sets_audio_url_on_every_article():
    paper = narration.narrate_paper(
        _sample(), narrate_article=_fake_article, build_script=_fake_build,
        grade=_approve, render_podcast=_fake_render)
    assert paper["ai"]["headliner"]["audio_url"] == "/tmp/graham-Long Context.mp3"
    assert paper["ai"]["subarticles"][0]["audio_url"].endswith("Chips.mp3")
    assert paper["ai"]["shorts"][0]["audio_url"].endswith("Short.mp3")
    assert paper["fun"][0]["audio_url"].endswith("Foil Arms.mp3")
    assert paper["ai"]["headliner"]["_audio_voice"] == "graham"


def test_desk_reads_alternate_while_editor_sections_stay_graham():
    paper = narration.narrate_paper(
        _sample(), narrate_article=_fake_article, build_script=_fake_build,
        grade=_approve, render_podcast=_fake_render)
    assert paper["ai"]["headliner"]["_audio_voice"] == "graham"      # desk item 0
    assert paper["ai"]["subarticles"][0]["_audio_voice"] == "tom"    # desk item 1
    assert paper["editors_brief"]["_audio_voice"] == "graham"        # editor's own
    assert paper["about"]["_audio_voice"] == "graham"                # editor's own


def test_attaches_podcast_when_banter_passes_the_gate():
    paper = narration.narrate_paper(
        _sample(), narrate_article=_fake_article, build_script=_fake_build,
        grade=_approve, render_podcast=_fake_render)
    assert paper["podcast"]["audio_url"] == "/tmp/podcast.mp3"
    assert "GRAHAM: Welcome." in paper["podcast"]["transcript"]
    assert paper["podcast"]["rubric"]["verdict"] == "APPROVE"


def test_attaches_tldr_headline_bulletin():
    paper = narration.narrate_paper(
        _sample(), narrate_article=_fake_article, build_script=_fake_build,
        grade=_approve, render_podcast=_fake_render)
    assert paper["podcast_tldr"]["audio_url"] == "/tmp/podcast.mp3"
    assert paper["podcast_tldr"]["_kind"] == "tldr"
    assert "GRAHAM:" in paper["podcast_tldr"]["transcript"]   # the bulletin transcript


def test_held_banter_is_never_voiced_and_the_hold_is_recorded():
    def _hold(text, **kw):
        return {"verdict": "HOLD", "reasons": ["too cruel"], "judge_model": "judge"}

    rendered = []

    def _render_spy(turns, **kw):
        rendered.append(turns)
        return ("/tmp/podcast.mp3", "tts-model")

    paper = narration.narrate_paper(
        _sample(), narrate_article=_fake_article, build_script=_build_respecting_banter,
        grade=_hold, render_podcast=_render_spy)
    # the held banter never reaches the TTS (the podcast itself degrades — see the
    # banter-stripped tests below); the hold stays on record
    assert all(not any("BANTER!" in t for _, t in turns) for turns in rendered)
    assert "too cruel" in paper["edition"]["podcast_hold"]


def test_per_article_audio_failure_is_soft():
    def _flaky(item, *, voice="graham", **kw):
        if item["title"] == "Chips":
            raise RuntimeError("tts down")
        return (f"/tmp/{item['title']}.mp3", "tts-model")

    paper = narration.narrate_paper(
        _sample(), narrate_article=_flaky, build_script=_fake_build,
        grade=_approve, render_podcast=_fake_render)
    assert paper["ai"]["headliner"]["audio_url"].endswith("Long Context.mp3")
    assert paper["ai"]["subarticles"][0]["audio_url"] is None  # failed one is soft-null


def test_no_banter_skips_the_gate_but_still_renders():
    def _build_no_banter(paper, **kw):
        return {"turns": [("graham", "Just readings.")], "script_text": "GRAHAM: Just readings.",
                "banter_text": "", "refs": []}

    graded = []

    def _grade_spy(text, **kw):
        graded.append(text)
        return {"verdict": "APPROVE", "reasons": [], "judge_model": "j"}

    paper = narration.narrate_paper(
        _sample(), narrate_article=_fake_article, build_script=_build_no_banter,
        grade=_grade_spy, render_podcast=_fake_render)
    assert graded == []  # nothing to gate
    assert paper["podcast"]["audio_url"] == "/tmp/podcast.mp3"


def test_records_audio_and_podcast_trace_events():
    paper = narration.narrate_paper(
        _sample(), narrate_article=_fake_article, build_script=_fake_build,
        grade=_approve, render_podcast=_fake_render)
    kinds = [e["kind"] for e in paper["context"]["agent_trace"]]
    assert "audio" in kinds and "podcast" in kinds


def test_held_podcast_is_traced_as_held():
    def _hold(text, **kw):
        return {"verdict": "HOLD", "reasons": ["too cruel"], "judge_model": "j"}

    paper = narration.narrate_paper(
        _sample(), narrate_article=_fake_article, build_script=_fake_build,
        grade=_hold, render_podcast=_fake_render)
    pod = [e for e in paper["context"]["agent_trace"] if e["kind"] == "podcast"]
    assert pod and "held" in pod[0]["name"].lower()


def test_narrates_the_editor_in_chief_sections():
    paper = narration.narrate_paper(
        _sample(), narrate_article=_fake_article, build_script=_fake_build,
        grade=_approve, render_podcast=_fake_render)
    assert paper["editors_brief"]["audio_url"]   # the Editor's Brief is listenable
    assert paper["about"]["audio_url"]            # the About page is listenable


def test_parody_fun_item_reads_in_its_clone_when_deployed(monkeypatch):
    from content_pipeline.content_config import content_cfg
    monkeypatch.setattr(content_cfg, "available_parody_voices", "ronald_dump")
    paper = _sample()
    paper["fun"][0]["persona"] = "Ronald Dump"    # make the fun item a parody with a clone
    out = narration.narrate_paper(
        paper, narrate_article=_fake_article, build_script=_fake_build,
        grade=_approve, render_podcast=_fake_render)
    assert out["fun"][0]["_audio_voice"] == "ronald_dump"


def test_narrate_paper_threads_the_edition_language():
    """A translated edition's language flows into the script builder + per-article reads
    (so the banter is written in-language and the spoken-form fixes match)."""
    captured = {}

    def _build(paper, **kw):
        captured["build_lang"] = kw.get("language")
        return {"turns": [("graham", "x")], "script_text": "GRAHAM: x",
                "banter_text": "", "refs": []}

    def _article(item, *, voice="graham", **kw):
        captured["article_lang"] = kw.get("language")
        return (f"/tmp/{item['title']}.mp3", "m")

    paper = _sample()
    paper["edition"] = {"language": "de"}
    narration.narrate_paper(paper, narrate_article=_article, build_script=_build,
                            grade=_approve, render_podcast=_fake_render)
    assert captured["build_lang"] == "de"
    assert captured["article_lang"] == "de"


# --- #64: a held banter degrades to the banter-less podcast ------------------
def _build_respecting_banter(paper, include_banter=True, **kw):
    if include_banter:
        return {"turns": [("graham", "Welcome."), ("tom", "BANTER!")],
                "script_text": "GRAHAM: Welcome.\nTOM: BANTER!",
                "banter_text": "BANTER!", "refs": ["ai.headliner"]}
    return {"turns": [("graham", "Welcome."), ("graham", "Just the readings.")],
            "script_text": "GRAHAM: Welcome.\nGRAHAM: Just the readings.",
            "banter_text": "", "refs": ["ai.headliner"]}


def test_held_banter_degrades_to_banterless_podcast():
    """The rubric holding the LLM banter must not sink the whole podcast — the framing
    and verbatim readings are deterministic and already approved. Strip, re-render, ship
    (what the no_banter path always did), and keep the hold reasons for transparency."""
    def _hold(text, **kw):
        return {"verdict": "HOLD", "reasons": ["meta-commentary, not banter"],
                "judge_model": "judge"}

    rendered = []

    def _render_spy(turns, **kw):
        rendered.append(turns)
        return ("/tmp/podcast.mp3", "tts-model")

    paper = narration.narrate_paper(
        _sample(), narrate_article=_fake_article, build_script=_build_respecting_banter,
        grade=_hold, render_podcast=_render_spy)
    assert paper["podcast"]["audio_url"] == "/tmp/podcast.mp3"   # podcast still ships
    assert "BANTER!" not in paper["podcast"]["transcript"]       # held text never voiced
    assert all(not any("BANTER!" in t for _, t in turns) for turns in rendered)
    assert "Just the readings." in paper["podcast"]["transcript"]
    # honest metadata: what ships is approved-by-construction, the hold is on record
    assert paper["podcast"]["rubric"]["verdict"] == "APPROVE"
    assert paper["podcast"]["rubric"]["result"] == "banter_stripped"
    assert "meta-commentary, not banter" in paper["edition"]["podcast_hold"]


def test_banterless_fallback_render_failure_is_soft():
    def _hold(text, **kw):
        return {"verdict": "HOLD", "reasons": ["bad"], "judge_model": "judge"}

    def _render_only_tldr(turns, **kw):
        # the main-podcast renders (banter or stripped) fail; the TL;DR path still works
        if any("Just the readings." in t or "BANTER!" in t for _, t in turns):
            raise RuntimeError("tts down")
        return ("/tmp/tldr.mp3", "tts-model")

    paper = narration.narrate_paper(
        _sample(), narrate_article=_fake_article, build_script=_build_respecting_banter,
        grade=_hold, render_podcast=_render_only_tldr)
    assert paper["podcast"] is None                      # soft, like every render failure
    assert "bad" in paper["edition"]["podcast_hold"]


def test_approved_banter_clears_a_stale_hold_from_a_prior_run():
    """Re-narrating a draft whose previous run was held must not ship the old
    podcast_hold next to an approved podcast — the hold is per-run metadata."""
    paper = _sample()
    paper["edition"] = {"podcast_hold": ["meta-commentary, not banter"]}
    paper = narration.narrate_paper(
        paper, narrate_article=_fake_article, build_script=_fake_build,
        grade=_approve, render_podcast=_fake_render)
    assert paper["podcast"]["rubric"]["verdict"] == "APPROVE"
    assert "podcast_hold" not in paper["edition"]
