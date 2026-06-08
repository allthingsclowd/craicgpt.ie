"""Offline tests for the dad↔son podcast script builder.

The banter LLM is injected (``generate``), so these run with no network. The key
invariant: article bodies are read VERBATIM (deterministic, already rubric-approved),
and only the dad↔son banter is model-written (and later rubric-gated).
"""
from content_pipeline.generate import podcast_script as ps


SAMPLE = {
    "date": "2026-05-12",
    "ai": {
        "headliner": {
            "title": "Long Context",
            "standfirst": "Big memory.",
            "body": "A lab gave its model a huge memory. It can hold a book.",
            "source_url": "http://x",
        },
        "subarticles": [
            {"title": "Sub One", "body": "A second story about chips.", "source_url": "http://y"}
        ],
        "shorts": [
            {"title": "Short One", "body": "A brief thing happened today.", "source_url": "http://z"}
        ],
    },
    "fun": [
        {"title": "Foil Arms", "body": "The lads did a class sketch.",
         "source": "Foil Arms and Hog", "source_url": "http://yt"}
    ],
    "layout": ["ai.headliner", "ai.subarticles.0", "ai.shorts.0", "fun.0"],
}


def _fake_generate(prompt):
    # the new "one clip per article" shape: each host-read article gets a one-line pre/post
    return {"items": [
        {"ref": "ai.headliner", "pre": "Right, let's open with the big one.",
         "post": "So now you know — over to you, Tom."},
        {"ref": "ai.subarticles.0", "pre": "Chips like crisps, Da?", "post": "Mad stuff, that."},
        {"ref": "ai.shorts.0", "pre": "", "post": "Quick one there."},
        {"ref": "fun.0", "pre": "This one's gas.", "post": "Back to you, Graham."},
    ]}


def test_script_is_topped_and_tailed_with_the_signature():
    res = ps.build_podcast_script(SAMPLE, generate=_fake_generate)
    turns = res["turns"]
    assert turns[0][0] == "graham"
    assert "craicgpt" in turns[0][1].lower()  # the clean "welcome to CraicGPT" cold-open
    assert turns[-1][0] == "graham"
    assert "god bless" in turns[-1][1].lower()


def test_article_bodies_are_read_verbatim_with_alternating_voices():
    res = ps.build_podcast_script(SAMPLE, generate=_fake_generate)
    all_text = " ".join(t for _, t in res["turns"])
    assert "It can hold a book." in all_text            # headliner body, verbatim
    assert "A second story about chips." in all_text     # subarticle body, verbatim
    # the hosts take turns: the headliner is read by Graham, the next article by Tom.
    reader = {}
    for who, t in res["turns"]:
        if "It can hold a book." in t:
            reader["headliner"] = who
        if "A second story about chips." in t:
            reader["sub"] = who
    assert reader["headliner"] == "graham"
    assert reader["sub"] == "tom"


def test_links_are_woven_into_the_readers_clip_and_only_links_are_gated():
    res = ps.build_podcast_script(SAMPLE, generate=_fake_generate)
    # the headliner reader (Graham) opens with his pre and the verbatim reading is in the
    # SAME clip — one piece per article, not a separate banter turn.
    graham_text = " ".join(t for who, t in res["turns"] if who == "graham")
    assert "Right, let's open with the big one." in graham_text   # the reader's pre link
    assert "It can hold a book." in graham_text                   # ...same clip as the reading
    # banter_text is ONLY the model-written links — the verbatim reading is NOT in it.
    assert "Right, let's open with the big one." in res["banter_text"]
    assert "It can hold a book." not in res["banter_text"]


def test_pre_precedes_reading_precedes_post_within_one_clip():
    res = ps.build_podcast_script(SAMPLE, generate=_fake_generate)
    # all three live in ONE consolidated clip, in order: pre → verbatim reading → post.
    clip = next(t for w, t in res["turns"] if "It can hold a book." in t)
    assert clip.index("let's open with the big one") < clip.index("It can hold a book.") \
        < clip.index("over to you, Tom")


def test_script_text_is_speaker_tagged_for_the_transcript():
    res = ps.build_podcast_script(SAMPLE, generate=_fake_generate)
    assert "GRAHAM:" in res["script_text"]
    assert "TOM:" in res["script_text"]


def test_limit_caps_the_number_of_articles():
    res = ps.build_podcast_script(SAMPLE, generate=_fake_generate, limit=1)
    graham_text = " ".join(t for who, t in res["turns"] if who == "graham")
    assert "It can hold a book." in graham_text                 # headliner kept
    assert "A second story about chips." not in graham_text     # subarticle dropped by limit


def test_signature_intro_folds_in_the_edition_date():
    intro = ps.build_signature_intro("2026-05-12")
    assert "12th of May, 2026" in intro[0][1]
    # and it flows through the built script (the cold-open carries the date)
    res = ps.build_podcast_script(SAMPLE, generate=_fake_generate)
    assert "May, 2026" in res["turns"][0][1]


def test_date_phrase_handles_a_bad_date_gracefully():
    assert ps._date_phrase("not-a-date") == "today"


def test_outro_sends_listeners_back_to_the_site():
    res = ps.build_podcast_script(SAMPLE, generate=_fake_generate)
    outro = " ".join(t for _, t in res["turns"][-3:]).lower()
    assert "craicgpt.ie" in outro
    assert "tomorrow" in outro


def test_digest_tells_the_model_who_reads_each_article():
    # the prompt digest carries reader + position so the model can write flowing links.
    plan = ps._plan([("ai.headliner", SAMPLE["ai"]["headliner"]),
                     ("ai.subarticles.0", SAMPLE["ai"]["subarticles"][0])])
    digest = ps._digest(plan)
    assert "read by GRAHAM" in digest and "read by TOM" in digest
    assert "FIRST" in digest


# --- TL;DR headline bulletin ------------------------------------------------
def test_tldr_is_topped_tailed_and_alternates_voices():
    res = ps.build_tldr_script(SAMPLE)
    turns = res["turns"]
    assert "headline" in turns[0][1].lower()                      # intro hook
    assert "craicgpt.ie" in " ".join(t for _, t in turns[-2:]).lower()  # outro → the site
    assert res["banter_text"] == ""                               # deterministic, no gate
    n_intro = len(ps.build_tldr_intro(SAMPLE["date"]))
    beats = turns[n_intro: len(turns) - len(ps.TLDR_OUTRO)]
    assert [w for w, _ in beats][:2] == ["graham", "tom"]         # alternating anchors
    assert "Long Context" in " ".join(t for _, t in beats)        # the edition's own title


def test_tldr_stays_within_its_word_budget():
    big = {
        "date": "2026-05-12",
        "layout": ["ai.headliner", "ai.subarticles.0", "ai.shorts.0", "fun.0"],
        "ai": {
            "headliner": {"title": "Head " * 40, "standfirst": "s " * 80, "body": "b " * 200,
                          "source_url": "x"},
            "subarticles": [{"title": "Sub", "standfirst": "d " * 80, "body": "b " * 80,
                             "source_url": "y"}],
            "shorts": [{"title": "Short", "body": "b " * 80, "source_url": "z"}],
        },
        "fun": [{"title": "Fun", "body": "b " * 80, "source": "X"}],
    }
    res = ps.build_tldr_script(big, max_seconds=180)
    assert sum(len(t.split()) for _, t in res["turns"]) <= 360    # trimmed under budget


def test_tldr_keeps_at_least_one_headline_even_if_huge():
    one = {"date": "2026-05-12", "layout": ["ai.headliner"],
           "ai": {"headliner": {"title": "Big", "body": "word " * 500, "source_url": "x"}}}
    res = ps.build_tldr_script(one, max_seconds=180)
    assert res["refs"] == ["ai.headliner"]                        # never drops the only story


# --- parody character voices (no clones) ------------------------------------
def test_parody_items_get_a_character_voice_framing():
    paper = {
        "date": "2026-05-12", "layout": ["fun.0"],
        "ai": {"headliner": {}, "subarticles": [], "shorts": []},
        "fun": [{"title": "Tremendous", "body": "The best AI, believe me.",
                 "source": "Some Clip", "persona": "Ronald Dump", "satire_disclaimer": "Parody."}],
    }
    res = ps.build_podcast_script(paper, generate=lambda p: {"items": []})
    reading = " ".join(t for _, t in res["turns"])
    assert "in the unmistakable style of Ronald Dump" in reading   # character framing
    assert "The best AI, believe me." in reading                   # body stays verbatim


def test_non_parody_items_have_no_character_framing():
    # credited-creator fun (no persona) is read straight — no theatrical intro.
    res = ps.build_podcast_script(SAMPLE, generate=_fake_generate)
    assert "unmistakable style of" not in " ".join(t for _, t in res["turns"])


def test_parody_item_with_a_deployed_clone_reads_in_its_own_voice(monkeypatch):
    from content_pipeline.content_config import content_cfg
    monkeypatch.setattr(content_cfg, "available_parody_voices", "ronald_dump")
    paper = {
        "date": "2026-05-12", "layout": ["fun.0"],
        "ai": {"headliner": {}, "subarticles": [], "shorts": []},
        "fun": [{"title": "Tremendous", "body": "The best AI, believe me.",
                 "source": "Some Clip", "persona": "Ronald Dump", "satire_disclaimer": "Parody."}],
    }
    res = ps.build_podcast_script(paper, generate=lambda p: {"items": []})
    reads = [(w, t) for w, t in res["turns"] if "The best AI, believe me." in t]
    assert reads and reads[0][0] == "ronald_dump"          # read in the cloned parody voice
    assert "unmistakable style of" not in " ".join(t for _, t in res["turns"])  # no text framing


# --- the reworked intro + conversational parody hand-offs --------------------
def test_intro_is_clean_self_intros_not_a_shout():
    intro = ps.build_signature_intro("2026-05-12")
    assert intro[0][0] == "graham" and "I'm Graham" in intro[0][1]   # Graham introduces himself
    assert intro[1][0] == "tom" and "I'm Tom" in intro[1][1]         # Tom breaks in, introduces himself
    assert "moooor" not in intro[0][1].lower()                       # no elongated shout


PARODY_SAMPLE = {
    "date": "2026-05-12",
    "layout": ["ai.headliner", "fun.0", "fun.1"],
    "ai": {"headliner": {"title": "Long Context", "body": "It can hold a book.",
                         "source_url": "x"}, "subarticles": [], "shorts": []},
    "fun": [
        {"title": "Tremendous", "body": "The best AI, believe me.",
         "source": "Clip", "persona": "Ronald Dump", "satire_disclaimer": "Parody."},
        {"title": "Gorgeous", "body": "A wild, lovely thing.",
         "source": "Clip", "persona": "Saoirse Ronaround", "satire_disclaimer": "Parody."},
    ],
}


def test_parody_guest_gets_a_simple_seniority_host_welcome(monkeypatch):
    from content_pipeline.content_config import content_cfg
    monkeypatch.setattr(content_cfg, "available_parody_voices", "ronald_dump,saoirse_ronaround")
    flat = ps.build_podcast_script(PARODY_SAMPLE, generate=lambda p: {"items": []})["turns"]
    # Ronald Dump (older) → welcomed by Graham, then reads in HIS OWN voice
    di = next(i for i, (w, t) in enumerate(flat) if "The best AI, believe me." in t)
    assert flat[di][0] == "ronald_dump"                                       # reads in his own voice
    assert flat[di - 1][0] == "graham" and "Ronald Dump" in flat[di - 1][1]    # older -> Graham welcome
    assert "thanks for having me" in flat[di][1].lower()                      # the guest's fixed ack
    # Saoirse (younger) → welcomed by Tom
    si = next(i for i, (w, t) in enumerate(flat) if "A wild, lovely thing." in t)
    assert flat[si][0] == "saoirse_ronaround"
    assert flat[si - 1][0] == "tom" and "Saoirse" in flat[si - 1][1]           # younger -> Tom welcome


def test_banter_prompt_marks_guests_and_tells_the_model_to_skip_them(monkeypatch):
    from content_pipeline.content_config import content_cfg
    monkeypatch.setattr(content_cfg, "available_parody_voices", "ronald_dump,saoirse_ronaround")
    captured = {}

    def _cap(prompt):
        captured["p"] = prompt
        return {"items": []}

    ps.build_podcast_script(PARODY_SAMPLE, generate=_cap)   # the host headliner triggers the call
    p = captured["p"]
    assert "GUEST 'Ronald Dump'" in p and "GUEST 'Saoirse Ronaround'" in p
    assert "welcomed by GRAHAM" in p and "welcomed by TOM" in p
    assert "write NO item" in p                                  # told to skip the guests


def test_guest_clip_is_ack_plus_reading_plus_signoff_and_is_not_gated(monkeypatch):
    from content_pipeline.content_config import content_cfg
    monkeypatch.setattr(content_cfg, "available_parody_voices", "ronald_dump")
    res = ps.build_podcast_script(PARODY_SAMPLE, generate=lambda p: {"items": []})
    clip = next(t for w, t in res["turns"] if w == "ronald_dump")
    assert "thanks for having me" in clip.lower()               # fixed ack template
    assert "The best AI, believe me." in clip                   # verbatim reading, in his own voice
    assert "back to you, lads" in clip.lower()                  # fixed sign-off template
    # the fixed guest framing is deterministic, so it's NOT in the gated banter text
    assert "thanks for having me" not in res["banter_text"].lower()


def test_undeployed_guest_cannot_speak_banter_falls_back_to_host(monkeypatch):
    from content_pipeline.content_config import content_cfg
    monkeypatch.setattr(content_cfg, "available_parody_voices", "")

    def _gen(prompt):
        return {"items": [{"ref": "fun.0", "before": [], "after": [
            {"who": "ronald_dump", "text": "Believe me."}]}]}

    res = ps.build_podcast_script(PARODY_SAMPLE, generate=_gen)
    assert not any(w == "ronald_dump" for w, _ in res["turns"])      # no clone -> guest is silent


# --- multi-lingual: translation note, localised framing, CJK budget ----------
def _de_paper():
    return {**SAMPLE, "edition": {"language": "de", "source_language": "en",
                                  "translated_by": "qwen3.6-test"}}


def test_translated_podcast_opens_with_a_spoken_translation_note():
    res = ps.build_podcast_script(_de_paper(), generate=lambda p: {"items": []})
    first = res["turns"][0]
    assert first[0] == "graham"
    assert "qwen3.6-test" in first[1]                              # names the real model
    assert "übersetzt" in first[1].lower()                        # the German note
    # the cold-open follows the note, and the framing is German
    assert any("willkommen bei craicgpt" in t.lower() for _, t in res["turns"][:3])
    # the note is deterministic framing — NOT part of the gated banter
    assert "übersetzt" not in res["banter_text"].lower()


def test_english_edition_has_no_translation_note():
    res = ps.build_podcast_script(SAMPLE, generate=_fake_generate)
    assert "translated" not in res["turns"][0][1].lower()
    assert "übersetzt" not in " ".join(t for _, t in res["turns"]).lower()


def test_banter_prompt_asks_for_target_language_links():
    captured = {}
    ps.build_podcast_script(_de_paper(), generate=lambda p: captured.setdefault("p", p) or {"items": []})
    assert "German" in captured["p"]                              # the LLM is told to write in German


def test_localised_intro_uses_target_language_and_date():
    intro = ps.build_signature_intro("2026-05-12", "de")
    assert "Guten Morgen" in intro[0][1]
    assert "12. Mai 2026" in intro[0][1]                          # localised date form


def test_tldr_japanese_budgets_by_characters_and_notes_translation():
    paper = {
        "date": "2026-05-12", "layout": ["ai.headliner", "ai.subarticles.0"],
        "edition": {"language": "ja", "source_language": "en", "translated_by": "qwen"},
        "ai": {"headliner": {"title": "長い文脈", "body": "ある研究所がモデルに大きな記憶を与えた。"},
               "subarticles": [{"title": "チップ", "body": "チップの話。"}], "shorts": []},
        "fun": [],
    }
    res = ps.build_tldr_script(paper, max_seconds=180)
    assert "翻訳" in res["turns"][0][1] and "qwen" in res["turns"][0][1]   # JA note + model
    assert res["refs"]                                            # kept at least one headline
    # the budget helper picks characters-per-second for CJK and counts characters, not words
    assert ps._tldr_budget(180, "ja") == int((180 - ps.TLDR_JINGLE_SECONDS) * ps.TLDR_BUDGET_CPS)
    assert ps._speaking_units("これはテスト", "ja") == 6            # chars, not one "word"
    assert ps._speaking_units("two words", "en") == 2
