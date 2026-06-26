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


def _fake_render(turns, **kw):
    return ("/tmp/podcast.mp3", "tts-model")


def test_sets_audio_url_on_every_article():
    paper = narration.narrate_paper(
        _sample(), narrate_article=_fake_article, build_script=_fake_build,
        render_podcast=_fake_render)
    assert paper["ai"]["headliner"]["audio_url"] == "/tmp/graham-Long Context.mp3"
    assert paper["ai"]["subarticles"][0]["audio_url"].endswith("Chips.mp3")
    assert paper["ai"]["shorts"][0]["audio_url"].endswith("Short.mp3")
    assert paper["fun"][0]["audio_url"].endswith("Foil Arms.mp3")
    assert paper["ai"]["headliner"]["_audio_voice"] == "graham"


def test_articles_narrate_concurrently_and_all_get_audio(monkeypatch):
    # With concurrency>1 the per-article readings must run in PARALLEL (so the M3's extra
    # workers are used), and every item must still get audio with the right alternation.
    import threading
    import time as _t
    from content_pipeline.content_config import content_cfg
    monkeypatch.setattr(content_cfg, "narrate_tts_concurrency", 4)
    inflight = {"now": 0, "max": 0}
    lock = threading.Lock()

    def _slow_article(item, *, voice="graham", **kw):
        with lock:
            inflight["now"] += 1
            inflight["max"] = max(inflight["max"], inflight["now"])
        _t.sleep(0.05)
        with lock:
            inflight["now"] -= 1
        return (f"/tmp/{voice}-{item['title']}.mp3", "tts-model")

    paper = narration.narrate_paper(
        _sample(), narrate_article=_slow_article, build_script=_fake_build,
        render_podcast=_fake_render)
    items = [paper["ai"]["headliner"], paper["ai"]["subarticles"][0],
             paper["ai"]["shorts"][0], paper["fun"][0]]
    assert all(i["audio_url"] for i in items)            # every reading produced audio
    assert inflight["max"] >= 2                          # they genuinely overlapped
    assert paper["ai"]["headliner"]["_audio_voice"] == "graham"  # alternation preserved


def test_desk_reads_alternate_while_editor_sections_stay_graham():
    paper = narration.narrate_paper(
        _sample(), narrate_article=_fake_article, build_script=_fake_build,
        render_podcast=_fake_render)
    assert paper["ai"]["headliner"]["_audio_voice"] == "graham"      # desk item 0
    assert paper["ai"]["subarticles"][0]["_audio_voice"] == "tom"    # desk item 1
    assert paper["editors_brief"]["_audio_voice"] == "graham"        # editor's own
    assert paper["about"]["_audio_voice"] == "graham"                # editor's own


def test_attaches_podcast_with_banter_ungated():
    """No banter gate (removed 2026-06-10 — too strict): the banter always ships."""
    paper = narration.narrate_paper(
        _sample(), narrate_article=_fake_article, build_script=_fake_build,
        render_podcast=_fake_render)
    assert paper["podcast"]["audio_url"] == "/tmp/podcast.mp3"
    assert "GRAHAM: Welcome." in paper["podcast"]["transcript"]
    assert "TOM: Howya!" in paper["podcast"]["transcript"]   # the banter is voiced
    assert "rubric" not in paper["podcast"]                   # no per-podcast verdict


def test_attaches_tldr_headline_bulletin():
    paper = narration.narrate_paper(
        _sample(), narrate_article=_fake_article, build_script=_fake_build,
        render_podcast=_fake_render)
    assert paper["podcast_tldr"]["audio_url"] == "/tmp/podcast.mp3"
    assert paper["podcast_tldr"]["_kind"] == "tldr"
    assert "GRAHAM:" in paper["podcast_tldr"]["transcript"]   # the bulletin transcript


def test_per_article_audio_failure_is_soft():
    def _flaky(item, *, voice="graham", **kw):
        if item["title"] == "Chips":
            raise RuntimeError("tts down")
        return (f"/tmp/{item['title']}.mp3", "tts-model")

    paper = narration.narrate_paper(
        _sample(), narrate_article=_flaky, build_script=_fake_build,
        render_podcast=_fake_render)
    assert paper["ai"]["headliner"]["audio_url"].endswith("Long Context.mp3")
    assert paper["ai"]["subarticles"][0]["audio_url"] is None  # failed one is soft-null


def test_banterless_script_still_renders():
    def _build_no_banter(paper, **kw):
        return {"turns": [("graham", "Just readings.")], "script_text": "GRAHAM: Just readings.",
                "banter_text": "", "refs": []}

    paper = narration.narrate_paper(
        _sample(), narrate_article=_fake_article, build_script=_build_no_banter,
        render_podcast=_fake_render)
    assert paper["podcast"]["audio_url"] == "/tmp/podcast.mp3"


def test_records_audio_and_podcast_trace_events():
    paper = narration.narrate_paper(
        _sample(), narrate_article=_fake_article, build_script=_fake_build,
        render_podcast=_fake_render)
    kinds = [e["kind"] for e in paper["context"]["agent_trace"]]
    assert "audio" in kinds and "podcast" in kinds


def test_podcast_render_failure_is_traced():
    def _render_no_podcast(turns, **kw):
        if any("Welcome." in t for _, t in turns):
            raise RuntimeError("tts down")
        return ("/tmp/tldr.mp3", "tts-model")

    paper = narration.narrate_paper(
        _sample(), narrate_article=_fake_article, build_script=_fake_build,
        render_podcast=_render_no_podcast)
    assert paper["podcast"] is None                       # render failure stays soft
    pod = [e for e in paper["context"]["agent_trace"] if e["kind"] == "podcast"]
    assert pod and "render failed" in pod[0]["name"].lower()


def test_narrates_the_editor_in_chief_sections():
    paper = narration.narrate_paper(
        _sample(), narrate_article=_fake_article, build_script=_fake_build,
        render_podcast=_fake_render)
    assert paper["editors_brief"]["audio_url"]   # the Editor's Brief is listenable
    assert paper["about"]["audio_url"]            # the About page is listenable


def test_parody_fun_item_reads_in_its_clone_when_deployed(monkeypatch):
    from content_pipeline.content_config import content_cfg
    monkeypatch.setattr(content_cfg, "available_parody_voices", "ronald_dump")
    paper = _sample()
    paper["fun"][0]["persona"] = "Ronald Dump"    # make the fun item a parody with a clone
    out = narration.narrate_paper(
        paper, narrate_article=_fake_article, build_script=_fake_build,
        render_podcast=_fake_render)
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
                            render_podcast=_fake_render)
    assert captured["build_lang"] == "de"
    assert captured["article_lang"] == "de"


# --- the banter gate was REMOVED (2026-06-10, Graham: "too strict") ----------
def test_a_stale_podcast_hold_from_the_gated_era_is_cleared():
    """Drafts narrated before the gate was removed may carry edition.podcast_hold;
    a re-narration must not ship that stale marker next to a podcast that now
    always carries its banter."""
    paper = _sample()
    paper["edition"] = {"podcast_hold": ["meta-commentary, not banter"]}
    paper = narration.narrate_paper(
        paper, narrate_article=_fake_article, build_script=_fake_build,
        render_podcast=_fake_render)
    assert paper["podcast"]["audio_url"] == "/tmp/podcast.mp3"
    assert "podcast_hold" not in paper["edition"]


def test_narrate_paper_respects_language_budget():
    """Past the per-language wall-clock budget, the remaining articles read without
    audio (audio_url=None) rather than running on — partial audio, never a timeout.
    Narration is enrichment (text already published), so this costs no quality."""
    narrated = []

    def counting_article(item, *, voice="graham", **kw):
        narrated.append(item.get("title"))
        return (f"/tmp/{voice}.mp3", "tts-model")

    # clock reads: deadline setup (0 -> deadline 60), article-0 check (10 < 60 ->
    # narrate), article-1 check (100 >= 60 -> break). Padding is harmless.
    ticks = iter([0.0, 10.0] + [100.0] * 20)

    paper = narration.narrate_paper(
        _sample(),
        narrate_article=counting_article,
        build_script=_fake_build,
        render_podcast=_fake_render,
        budget_s=60,
        clock=lambda: next(ticks),
    )
    assert len(narrated) == 1  # only the first article was narrated before the budget ran out
    audio_urls = [a.get("audio_url") for a in narration._article_targets(paper)]
    assert audio_urls[0] is not None  # the one we got to
    assert any(u is None for u in audio_urls[1:])  # the rest left fail-soft


def test_narrate_paper_no_budget_narrates_all():
    """Default (no budget) is unchanged — every article is narrated, clock untouched."""
    narrated = []

    def counting_article(item, *, voice="graham", **kw):
        narrated.append(item.get("title"))
        return ("/tmp/a.mp3", "m")

    paper = narration.narrate_paper(
        _sample(),
        narrate_article=counting_article,
        build_script=_fake_build,
        render_podcast=_fake_render,
    )
    assert len(narrated) == len(narration._article_targets(paper))
    assert all(a.get("audio_url") for a in narration._article_targets(paper))
