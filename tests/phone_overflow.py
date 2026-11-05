"""Fail when a page is wider than its screen, a header button shrinks, or a nav label spills.

    uv run python tests/phone_overflow.py <dir> /page.html

The header standard (thegeekwiththepeak.com map #208) has measurable invariants: at
any width from 320px up the document is never wider than the viewport; below 1200px every
control in the masthead's account cluster is a 44px touch target; and no nav label is wider
than its own tab or pill at any width. A control that outgrows the masthead shows up as
horizontal scroll on a phone, a squeezed one as a 30px button, a squeezed nav as text lying
on its neighbour, and none of that shows in a unit test, so this measures the real layout.

Headless Chrome clamps its window to about 500px wide, so a page asked for 360 lays out at
500 and looks fine. Each page is therefore loaded in an <iframe> of the exact width, served
from a local HTTP server so the harness may read the frame. The harness page is served from
memory: nothing is written into the measured directory, which may be one that gets deployed.
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
from typing import NamedTuple

WIDTHS = (320, 360, 412, 600, 768, 1024, 1199, 1200, 1440)
MIN_TOUCH = 44
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
function controls(d) {
  // [shortest side, longest side, count] over the visible controls in the account cluster
  let small = null, large = null, n = 0;
  for (const k of d.querySelectorAll('.site-header .account > *')) {
    const r = k.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;   // hidden, or a 1px separator
    small = Math.min(small === null ? Infinity : small, r.width, r.height);
    large = Math.max(large === null ? 0 : large, r.width, r.height);
    n += 1;
  }
  return [small, large, n];
}
function tab(d) {
  // The shorter side of the smallest visible nav link (the phone's touch targets); null if none.
  let small = null;
  for (const a of d.querySelectorAll('.shell-nav a')) {
    const r = a.getBoundingClientRect();
    if (!r.width) continue;
    small = Math.min(small === null ? Infinity : small, r.width, r.height);
  }
  return small;
}
function spills(d) {
  // Nav links whose label reaches past the link's own box on either side (text lying on
  // its neighbour), or that sit partly off screen (a fixed tab bar never widens the
  // document). The label's own rectangle is measured: scrollWidth sees only the right-hand
  // half of a centred label's overflow.
  let n = 0;
  const vw = d.documentElement.clientWidth;
  for (const a of d.querySelectorAll('.shell-nav a')) {
    const r = a.getBoundingClientRect();
    if (!r.width) continue;
    let bad = r.left < -0.5 || r.right > vw + 0.5;
    for (const node of a.childNodes) {
      if (node.nodeName.toLowerCase() === 'svg' || !node.textContent.trim()) continue;
      const range = d.createRange();
      range.selectNodeContents(node);
      const t = range.getBoundingClientRect();
      if (t.width && (t.left < r.left - 0.5 || t.right > r.right + 0.5)) bad = true;
    }
    if (bad) n += 1;
  }
  return n;
}
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
    const shell = d.querySelector('.site-header');
    const [small, large, count] = shell ? controls(d) : [null, null, 0];
    out.push([p, w, shell ? d.documentElement.scrollWidth : -1, small, large, count,
              shell ? spills(d) : 0, shell ? tab(d) : null]);
    f.remove();
    next();
  }, 400);
  document.body.appendChild(f);
}
next();
</script></body>"""


class Row(NamedTuple):
    path: str
    width: int  # the viewport
    scroll: int  # the document's scrollWidth
    smallest: float | None  # shortest side of any account control; None if none found
    largest: float | None  # longest side of any account control
    controls: int  # visible account controls
    spills: int  # nav links whose label reaches past the link, or that sit off screen
    tab: float | None  # shorter side of the smallest nav link; None if the page has no nav


class _Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] != f"/{HARNESS}":
            super().do_GET()
            return
        body = _HARNESS_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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


def measure(dist: Path, paths: list[str], widths: tuple[int, ...] = WIDTHS) -> list[Row]:
    """One ``Row`` of real-layout measurements for every path at every width."""
    chrome = find_chrome()
    if chrome is None:
        raise RuntimeError("no Chrome or Chromium found to measure layout with")
    handler = functools.partial(_Handler, directory=str(dist))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
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
    match = re.search(r"RESULT(\[.*?\])END", dom)
    if match is None:
        raise RuntimeError("the layout harness returned no measurements")
    rows = [Row(*item) for item in json.loads(match.group(1))]
    missing = sorted({r.path for r in rows if r.scroll < 0})
    if missing:
        raise RuntimeError(f"page(s) did not load the site shell: {', '.join(missing)}")
    return rows


def overflowing(rows: list[Row]) -> list[Row]:
    return [r for r in rows if r.scroll > r.width]


def undersized(rows: list[Row], minimum: int = MIN_TOUCH) -> list[Row]:
    """Rows below desktop width whose smallest account control is under the touch target.
    A page where no control was found counts: a renamed cluster must not pass as "fine"."""
    return [
        r for r in rows if r.width < 1200 and (r.smallest is None or r.smallest < minimum - 0.5)
    ]


def not_square(rows: list[Row], side: int = MIN_TOUCH) -> list[Row]:
    """Rows below desktop width where an account control is longer than the square it should
    be: a labelled pill that kept its words."""
    return [r for r in rows if r.width < 1200 and r.largest is not None and r.largest > side + 0.5]


def small_tabs(rows: list[Row], minimum: int = MIN_TOUCH) -> list[Row]:
    """Rows where a nav link is under the touch target, at any width."""
    return [r for r in rows if r.tab is not None and r.tab < minimum - 0.5]


def spilling(rows: list[Row]) -> list[Row]:
    """Rows where a nav label is wider than its own tab or pill, or a tab is off screen."""
    return [r for r in rows if r.spills]


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    rows = measure(Path(argv[1]), argv[2:] or ["/"])
    wide, small, spilt = overflowing(rows), undersized(rows), spilling(rows)
    long, tabs = not_square(rows), small_tabs(rows)
    for r in wide:
        print(f"  OVERFLOW {r.path} at {r.width}px: document is {r.scroll}px wide")
    for r in small:
        print(f"  UNDERSIZED {r.path} at {r.width}px: smallest header control {r.smallest}px")
    for r in spilt:
        print(f"  SPILL {r.path} at {r.width}px: {r.spills} nav link(s) spill or sit off screen")
    for r in long:
        print(f"  NOT SQUARE {r.path} at {r.width}px: a header control is {r.largest}px long")
    for r in tabs:
        print(f"  SMALL TAB {r.path} at {r.width}px: smallest nav link {r.tab}px")
    bad = bool(wide or small or spilt or long or tabs)
    if not bad:
        print(f"  header layout holds: {len(rows)} page/width pairs")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
