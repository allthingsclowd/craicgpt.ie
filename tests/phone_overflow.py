"""Fail when a built page is wider than a phone or tablet screen.

    python tests/phone_overflow.py frontend /index.html

The header standard (thegeekwiththepeak.com map #208) has one invariant: at any width from
320px up the document is never wider than the viewport. A control that outgrows the masthead
shows up as horizontal scroll on a phone and nowhere in a unit test, so this measures the real
layout.

Headless Chrome clamps its window to about 500px wide, so a page asked for 360 lays out at
500 and looks fine. Each page is therefore loaded in an <iframe> of the exact width, served
from a local HTTP server so the harness may read the frame's ``scrollWidth``.
"""

from __future__ import annotations

import functools
import http.server
import json
import re
import shutil
import subprocess
import sys
import threading
import urllib.parse
from pathlib import Path

WIDTHS = (320, 360, 412, 600, 768, 1024, 1199)
CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome",
    "chromium",
    "chromium-browser",
)
HARNESS = "_phone_overflow_harness.html"
_HARNESS_HTML = """<!doctype html><body style="margin:0"><script>
const q = new URLSearchParams(location.search);
const jobs = [];
const widths = JSON.parse(q.get('widths'));
for (const p of JSON.parse(q.get('paths'))) for (const w of widths) jobs.push([p, w]);
const out = [];
function next() {
  if (!jobs.length) { document.title = 'RESULT' + JSON.stringify(out) + 'END'; return; }
  const [p, w] = jobs.shift();
  const f = document.createElement('iframe');
  f.style.cssText = `width:${w}px;height:600px;border:0`;
  f.src = p;
  f.onload = () => setTimeout(() => {
    const d = f.contentDocument;
    // -1 marks a page that did not load the site shell (a 404 has no masthead), so a
    // mistyped path fails instead of measuring an empty document as "no overflow".
    out.push([p, w, d.querySelector('.site-header') ? d.documentElement.scrollWidth : -1]);
    f.remove();
    next();
  }, 400);
  document.body.appendChild(f);
}
next();
</script></body>"""


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Stay silent: a request log per iframe drowns the test output."""


def find_chrome() -> str | None:
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
        found = shutil.which(candidate)
        if found:
            return found
    return None


def measure(
    dist: Path, paths: list[str], widths: tuple[int, ...] = WIDTHS
) -> list[tuple[str, int, int]]:
    """(path, viewport width, document scrollWidth) for every path at every width."""
    chrome = find_chrome()
    if chrome is None:
        raise RuntimeError("no Chrome or Chromium found to measure layout with")
    harness = dist / HARNESS
    handler = functools.partial(_QuietHandler, directory=str(dist))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        harness.write_text(_HARNESS_HTML, encoding="utf-8")
        query = urllib.parse.urlencode(
            {"paths": json.dumps(paths), "widths": json.dumps(list(widths))}
        )
        url = f"http://127.0.0.1:{server.server_address[1]}/{HARNESS}?{query}"

        budget = 3000 + 900 * len(paths) * len(widths)
        dom = subprocess.run(
            [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--window-size=1400,800",
                f"--virtual-time-budget={budget}",
                "--dump-dom",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        ).stdout
    finally:
        server.shutdown()
        server.server_close()
        harness.unlink(missing_ok=True)
    match = re.search(r"RESULT(\[.*?\])END", dom)
    if match is None:
        raise RuntimeError("the layout harness returned no measurements")
    rows = [(p, w, sw) for p, w, sw in json.loads(match.group(1))]
    missing = sorted({p for p, _, sw in rows if sw < 0})
    if missing:
        raise RuntimeError(f"page(s) did not load the site shell: {', '.join(missing)}")
    return rows


def overflowing(rows: list[tuple[str, int, int]]) -> list[tuple[str, int, int]]:
    return [row for row in rows if row[2] > row[1]]


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    rows = measure(Path(argv[1]), argv[2:] or ["/"])
    bad = overflowing(rows)
    for path, width, scroll in bad:
        print(f"  OVERFLOW {path} at {width}px: document is {scroll}px wide (+{scroll - width})")
    if not bad:
        print(f"  no horizontal overflow: {len(rows)} page/width pairs")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
