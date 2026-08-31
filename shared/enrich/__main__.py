"""
shared/enrich/__main__.py
=========================
Network-gated CLI:  ``python -m shared.enrich <module-dir> --topic "<tactic>"``

TUTORIAL: this is the ONE place that actually touches the network — a real LLM
call (via :func:`default_llm`) plus a live citation HEAD-check. It is deliberately
NOT imported by the test-suite (tests import :mod:`shared.enrich.enrich` and inject
a stub), so nothing here runs offline. Keep all real I/O behind this ``__main__``
guard; the library stays pure.

It walks ``<module-dir>`` for ``*.json`` course items (each a dict with at least a
``title``/``body``, or a list of such dicts), enriches each against ``--topic``,
and prints the result. With ``--write`` it stashes the blurb back under the item's
``_enrichment`` key. A declined/unverifiable item is left untouched — integrity
over output all the way to the edge.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.request
from pathlib import Path
from typing import Iterable

from shared.enrich.enrich import Enrichment, default_llm, enrich_item


def _live_verify(url: str, *, timeout: float = 10.0) -> bool:
    """A real reachability check for a citation — HEAD, browser-ish UA, follow 3xx.

    Mirrors the CraicGPT gate's stance: a browser User-Agent so bot-blocking hosts
    (which many security-advisory sites are) don't false-negative a real URL. Any
    network error or a >=400 status means "cannot vouch for it" → False.
    """
    req = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": "Mozilla/5.0 (compatible; geek-red-team-academy/enrich)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - http(s) only
            return 200 <= getattr(resp, "status", 200) < 400
    except Exception as exc:  # noqa: BLE001 — unreachable == cannot cite
        logging.getLogger(__name__).warning("[enrich-cli] verify failed for %s: %s", url, exc)
        return False


def _iter_items(path: Path) -> Iterable[tuple[Path, dict]]:
    """Yield ``(file, item)`` for every course item under ``path`` (a JSON dict or
    a JSON list of dicts per file)."""
    for jf in sorted(path.rglob("*.json")):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logging.getLogger(__name__).warning("[enrich-cli] skipping %s: %s", jf, exc)
            continue
        if isinstance(data, dict):
            yield jf, data
        elif isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict):
                    yield jf, entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m shared.enrich",
        description="Attach a real, recent, cited real-world hook to course items.",
    )
    parser.add_argument("module_dir", help="Directory of *.json course items to enrich.")
    parser.add_argument("--topic", required=True,
                        help='The ATT&CK tactic / lesson topic, e.g. "Valid Accounts (T1078)".')
    parser.add_argument("--write", action="store_true",
                        help="Write the blurb back under each item's _enrichment key.")
    parser.add_argument("--no-verify", action="store_true",
                        help="Skip the live citation HEAD-check (not recommended).")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    root = Path(args.module_dir)
    if not root.exists():
        print(f"no such directory: {root}", file=sys.stderr)
        return 2

    llm = default_llm()
    verify = None if args.no_verify else _live_verify

    enriched = 0
    for jf, item in _iter_items(root):
        result: Enrichment | None = enrich_item(item, topic=args.topic, llm=llm, verify_url=verify)
        title = str(item.get("title") or "(untitled)")[:70]
        if result is None:
            print(f"·  {title}\n   (no verifiable hook — item left unchanged)")
            continue
        enriched += 1
        print(f"✓  {title}\n   {result.headline}\n   {result.tie_in}\n   {result.source_url}"
              f"  [{result.model_used}]")
        if args.write:
            item["_enrichment"] = result.as_dict()
            try:
                jf.write_text(json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8")
            except OSError as exc:
                print(f"   (could not write {jf}: {exc})", file=sys.stderr)

    print(f"\nenriched {enriched} item(s).")
    return 0


if __name__ == "__main__":  # pragma: no cover - network CLI, never run in tests
    raise SystemExit(main())
