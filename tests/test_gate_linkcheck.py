"""The publish gate's link-check must agree with generation's link-validation.

The 2026-06-04/05 HOLDs: the gate's ``_check_links`` validated every source_url
with httpx's DEFAULT (bot) User-Agent — and real sources that present fine to a
browser (CNBC, OpenAI, VentureBeat, Microsoft's AI blog) answer that bot UA with
403/429. So editions whose AI sources generation had ALREADY browser-validated
were falsely held as "unreachable". Worse, a bot UA returns 403 for BOTH a real
and an invented OpenAI URL, so it can't tell them apart; a browser UA returns 200
for the real one and 404 for the invented one.

The fix: the gate validates each link with the SAME browser-UA check generation
uses (``curation.validate_source_link``), so a generation-validated URL can never
be falsely held — while an invented URL (browser 404) still fails. These tests
inject the per-URL status (the seam ``validate_source_link`` already exposes) so
they run offline.
"""

from content_pipeline.agent.cli import _check_links


def _paper(urls, fun_urls=()):
    urls = list(urls)
    return {
        "ai": {
            "headliner": {"source_url": urls[0]} if urls else {},
            "subarticles": [{"source_url": u} for u in urls[1:2]],
            "shorts": [{"source_url": u} for u in urls[2:]],
        },
        "fun": [{"source_url": u} for u in fun_urls],
    }


def test_check_links_all_ok_when_every_url_resolves():
    paper = _paper(["https://a/1", "https://a/2", "https://a/3"], fun_urls=["https://f/1"])
    res = _check_links(paper, fetch=lambda u: 200)
    assert res["all_ok"] is True
    assert res["failed"] == []
    assert res["checked"] == 4


def test_check_links_passes_browser_reachable_fails_invented():
    # A real-but-bot-blocked host resolves 200 to a browser UA; an invented slug
    # 404s. The gate must keep the first and fail only the invented one.
    status = {
        "https://openai.com/index/real-launch": 200,   # real (browser 200, bot 403)
        "https://www.cnbc.com/2026/06/03/real": 200,    # real (browser 200, bot 403)
        "https://openai.com/index/invented-slug": 404,  # hallucinated (browser 404)
    }
    paper = _paper(list(status))
    res = _check_links(paper, fetch=lambda u: status[u])
    assert res["failed"] == ["https://openai.com/index/invented-slug"]
    assert res["all_ok"] is False
    assert res["checked"] == 3


def test_gate_and_generation_share_one_linkcheck():
    # The CONTRACT that prevents the regression: feed the SAME per-URL status to
    # generation's AI-candidate validation and to the gate's link-check; a URL kept
    # by generation must never be in the gate's failed set (and vice-versa). They
    # validate links through one shared browser-UA check.
    from content_pipeline.agent.editor_in_chief import _validate_ai_candidates

    status = {"https://ok/1": 200, "https://bot-blocked/2": 200, "https://dead/3": 404}
    fetch = lambda u: status[u]  # noqa: E731

    cands = [{"title": f"story {i}", "summary": "s", "source_url": u}
             for i, u in enumerate(status)]
    survivors, _ = _validate_ai_candidates(cands, fetch=fetch)
    survivor_urls = {c["source_url"] for c in survivors}

    failed = set(_check_links(_paper(list(status)), fetch=fetch)["failed"])

    assert survivor_urls == {"https://ok/1", "https://bot-blocked/2"}
    assert failed == {"https://dead/3"}
    assert survivor_urls.isdisjoint(failed)  # generation-pass => gate-pass


def test_check_links_treats_fetch_error_as_unreachable():
    # A genuinely dead domain (fetch raises) must fail the gate — validate_source_link
    # already maps any fetch exception to "don't publish it".
    def boom(_u):
        raise OSError("no such host")

    res = _check_links(_paper(["https://gone/1"]), fetch=boom)
    assert res["failed"] == ["https://gone/1"]
    assert res["all_ok"] is False
