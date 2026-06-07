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
