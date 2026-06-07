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
    return {"items": [
        {"ref": "ai.headliner",
         "before": [{"who": "tom", "text": "What's a context window, Da?"}],
         "after": [{"who": "graham", "text": "So now you know."}]},
        {"ref": "ai.subarticles.0",
         "before": [{"who": "tom", "text": "Chips like crisps?"}], "after": []},
        {"ref": "ai.shorts.0", "before": [], "after": [{"who": "tom", "text": "Mad."}]},
        {"ref": "fun.0",
         "before": [{"who": "tom", "text": "This one's gas."}], "after": []},
    ]}


def test_script_is_topped_and_tailed_with_the_signature():
    res = ps.build_podcast_script(SAMPLE, generate=_fake_generate)
    turns = res["turns"]
    assert turns[0][0] == "graham"
    assert "craicgpt" in turns[0][1].lower()  # the "Goooood morning, CraicGPT!" cold-open
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


def test_banter_turns_are_present_and_voiced_to_the_right_speaker():
    res = ps.build_podcast_script(SAMPLE, generate=_fake_generate)
    tom_text = " ".join(t for who, t in res["turns"] if who == "tom")
    assert "What's a context window" in tom_text
    # banter_text is the model-written turns only — what the rubric gate will judge.
    assert "context window" in res["banter_text"].lower()
    assert "It can hold a book." not in res["banter_text"]  # verbatim article NOT in the gated text


def test_before_banter_precedes_the_reading_which_precedes_after_banter():
    res = ps.build_podcast_script(SAMPLE, generate=_fake_generate)
    flat = res["turns"]
    # find the headliner reading turn
    read_idx = next(i for i, (w, t) in enumerate(flat) if "It can hold a book." in t)
    before_idx = next(i for i, (w, t) in enumerate(flat) if "context window" in t.lower())
    after_idx = next(i for i, (w, t) in enumerate(flat) if t == "So now you know.")
    assert before_idx < read_idx < after_idx


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


def test_digest_tells_the_banter_who_reads_each_article():
    # the prompt digest carries reader + position so the model can write hand-offs.
    pairs = [("ai.headliner", SAMPLE["ai"]["headliner"]),
             ("ai.subarticles.0", SAMPLE["ai"]["subarticles"][0])]
    digest = ps._digest(pairs)
    assert "read by GRAHAM" in digest and "read by TOM" in digest
    assert "first" in digest


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
