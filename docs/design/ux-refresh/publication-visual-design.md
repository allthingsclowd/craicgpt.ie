# How modern digital publications look on phone, iPad and desktop

> **Research doc — feeds the #116 "pick the look" decision.** AFK survey of how
> current daily-brief and digital-publication sites present across device sizes,
> and what each finding implies for The Craic Gazette's front end. Nothing here is
> built or decided — this is the grounding for the human pick-the-look call.
>
> Repo: `craicgpt.ie` · Branch: `research/ux-refresh` · Ticket: #120 · Part of #116

---

## 0. Where The Craic Gazette is today (the baseline we're refreshing)

So the survey lands against something concrete, here is the current front end
(`frontend/index.html` + `static_assets/style.css` + `style-v3.css` + `main.js`):

- **Reading shell:** a **3-column front page** — the Editor's Brief spans the top,
  the AI desk fills a 2-fr block split into two columns (headliner + shorts span
  both, two subarticles take one each), the fun desk is the 1-fr third column. It
  **collapses to a single column at `max-width: 900px`** — one breakpoint, phone
  and tablet treated the same.
- **Masthead:** top strip (price / tagline / edition), an SVG wordmark, a dateline
  with a date-picker + version `<select>`. The **language switcher is rendered into
  the masthead by `main.js`** and uses **country flags** (`LANG_FLAG`; English → the
  Irish tricolour).
- **Audio:** a `.podcast-strip` below the masthead (hidden until audio exists) with
  inline pills — Listen / play / download / transcript — plus **per-article
  `.audio-btn`** buttons.
- **Type:** Archivo (UI/sans) + Source Serif 4 (headline + body serif); headlines
  already **fluid via `clamp()`**.
- **Palette:** a single **light "newsprint" theme** (`--paper`, `--ink`,
  `--accent` muted red). **No dark mode** — no `prefers-color-scheme` block, no
  theme tokens.
- **Extras:** an "Under the Hood" drawer (the tutorial trace) and a newsletter band.

The three gaps this survey keeps returning to: **one breakpoint** (no tablet
tier), **flags standing in for languages**, and **no dark mode**.

---

## 1. The reading shell, per size

Modern publications do **not** ship one layout that fluidly stretches; they ship
**two or three discrete shells** at agreed breakpoints. The one boundary nobody
disputes is **768px** (tablet); the common tiers are ~640 (small tablet), 768
(tablet), 1024 (laptop), 1280+ (desktop). The reason 768 matters for a text paper:
it is where a single reading column can still hold the ideal **66–75 character
measure** while a second column becomes possible.

| Size | Shell modern publications use | Implication for Craic Gazette |
|------|-------------------------------|-------------------------------|
| **Phone** (<640) | Single scrolling column; **primary nav in a bottom tab bar** (thumb-zone) or a sticky top bar; sections as chips. | Keep the 1-column collapse, but move the day's controls (date, language, listen) out of the tall masthead into a reachable bar. |
| **iPad / tablet** (768–1024) | **Two columns**, not three; sidebars collapse below or into a **nav rail**. Portrait ≈ 2-col, landscape can approach desktop. | **New middle tier.** Today the site jumps 3-col → 1-col at 900. Add a 2-col shell (e.g. AI desk + fun desk side by side, brief full-width) between ~720 and ~1024. |
| **Desktop** (1024+) | Hero-plus-grid; a fixed masthead; **Axios rarely shows >10 stories** at once. | The current 3-column grid is right here. Cap visible density; let "shorts" be the long tail. |

**Bottom navigation** is the single biggest phone-era shift: Material and Apple's
HIG both put primary destinations at the **bottom edge** because that is where the
thumb rests. Tab bars work for **3–5 equal destinations**. The Craic Gazette
doesn't have app-like sections, but the day's *actions* (Today / Change date /
Listen / Language) are exactly a 3–5-item set that belongs in a thumb-reachable
bar on the phone rather than stacked in a 4-row masthead.

---

## 2. Sequencing the front page on a phone

A phone reader gets **one column and a scroll**, so order is everything. The
dominant pattern is **hero-plus-grid**: one large featured story, then a
card-based stack of secondary headlines, newest/most-important first. The Guardian's
2026 redesign is explicitly **"mobile-first UX with print-inspired art direction"**;
Axios leads **top-left with the lead story and a square photo**, no rotating cover,
and uses **pill-rounded section chips** as its structural signature.

Implication for the Craic Gazette's phone stack (it currently just linearises the
desktop grid via `layout`):

1. **Hero = the AI headliner** with its cartoon, full-bleed width.
2. **A section chip** ("AI DESK" / "CRAIC & THROTTLE") before each run, so the
   two desks stay legible once stacked — the desktop columns are what separate
   them today, and that separation vanishes on a phone.
3. **Interleave, don't segregate:** a fun story after every 2–3 AI items keeps the
   "no doom" promise visible in the scroll rather than parked at the bottom.
4. **Shorts are the tail:** compact spot-illustration cards last, as they already
   render (`.card--ai.card--short`).

---

## 3. Type and tokens

The 2026 consensus is **fluid typography driven by tokens**: size (and sometimes
weight and optical size) expressed as a function of viewport width against a
**modular scale** (Major Third / Golden Ratio). Tokenise the **ratio**, not each
size, so the scale stays harmonious across wrist-to-ultrawide. Editorial design
still rewards a **strong display/body contrast** and a disciplined measure.

The Craic Gazette already uses `clamp()` for headlines and has a sane serif/sans
pairing — it is most of the way there. What a refresh should add:

- **A named token scale** (`--step--1 … --step-6`) built from one ratio, replacing
  ad-hoc `clamp()` and `rem` values scattered through `style-v3.css`. This is also
  what makes a later theme/skin swap a token edit, not a CSS rewrite.
- **A measure cap** (`max-width: ~66ch`) on body copy so the desktop 2-column lead
  and the phone single column both stay in the 66–75-char band.
- **Spacing tokens** on the same footing as type (the current CSS mixes `rem`
  literals); a `--space-*` ramp keeps rhythm consistent when the shell reflows.

---

## 4. Dark mode

Dark mode is now table stakes, and the 2026 guidance is specific: **never pure
black on pure white** — halation makes it shimmer. Use **off-black / off-white**,
mathematically balanced; consider **slightly heavier body weight** and marginally
looser leading in the dark theme for legibility.

The Craic Gazette has **no dark mode at all**. Recommendation:

- Add a `@media (prefers-color-scheme: dark)` theme by **redefining the existing
  `:root` tokens only** (`--paper`, `--ink`, `--ink-soft`, `--hairline`,
  `--accent`) — the whole point of moving to tokens (§3). "Newsprint" becomes an
  **off-charcoal** (~`#16150f`) with **off-white ink** (~`#ece7dc`), the muted red
  accent nudged brighter so it survives on dark.
- Keep the **cartoon images** as-is (they carry their own white grounds); just make
  sure card surfaces and hairlines have dark values so images don't float on a void.
- Offer a **manual toggle** that overrides the system preference and remembers via
  `localStorage` — same mechanism the language cookie already uses.

---

## 5. Language-switcher placement

Two firm findings, one of which flags a current anti-pattern:

- **Don't use flags for languages.** Flags represent **countries, not languages**,
  and can confuse or alienate. The Craic Gazette currently shows **country flags**
  (English = Irish tricolour). The playful tricolour is on-brand, but the *other*
  five should lead with **endonyms** (Deutsch, Español, Italiano, 日本語, Français),
  optionally with a subtle flag, never a flag alone.
- **Placement:** top-right of the header on desktop / inside the menu on mobile is
  the convention; **footer-only placement loses people** on long scroll pages;
  make it easy to spot but not shouty, and **consistent on every page**. **Remember
  the choice** in a cookie / local storage.

The Craic Gazette already remembers the choice (`cg_lang` cookie, edge-detected by
`infra/cloudfront/router.js`) and puts the switcher in the masthead — both correct.
The refresh is mostly **flags → endonyms**, and on the phone folding it into the
same thumb-reachable actions bar as §1 rather than the crowded masthead.

---

## 6. Fitting the audio in without clutter

The Craic Gazette is unusually audio-rich (per-article readings + a dad↔son podcast
+ a TL;DR bulletin, in every language). The pattern that keeps that from cluttering
the page is the **sticky mini-player**: an unintrusive **bar fixed to the bottom (or
top)** that persists across navigation so playback continues while the reader moves
around, with the full controls living in the bar rather than repeated on every card.

Implications:

- Promote the current **`.podcast-strip`** (a static band below the masthead) to a
  **sticky bottom mini-player** that appears once playback starts and survives a
  date/version/language change — this also merges naturally with the phone
  **bottom actions bar** (§1): Listen is one of the thumb-zone actions.
- Keep **per-article `.audio-btn`** as the *entry* points (tap to play this piece),
  but route them through the one persistent player rather than spawning inline
  `<audio>` elements — one transport, many triggers.
- A **"Listen mode"** (play the whole edition top-to-bottom, screen-lock-friendly)
  is a natural extension and matches the academy's Listen-mode pattern already in
  the wider estate.

---

## 7. Summary — what this implies for the pick-the-look (#116)

The look-and-feel decision is downstream of a handful of structural moves this
survey keeps surfacing. In rough priority:

1. **Add a tablet tier.** One 900px breakpoint is the biggest gap; introduce a
   ~720–1024 **2-column** shell (§1).
2. **Tokenise type + spacing + colour** on one modular scale (§3) — the enabler for
   everything below.
3. **Ship dark mode** by redefining those tokens under `prefers-color-scheme`, with
   a remembered manual toggle (§4).
4. **Phone actions bar** in the thumb zone (Today / date / Listen / language),
   pulling weight out of the 4-row masthead (§1, §5, §6).
5. **Sticky mini-player** that persists across navigation; per-article buttons feed
   it (§6).
6. **Endonyms, not flags**, for the non-English languages (§5).
7. **Explicit phone sequencing:** hero headliner → section chips → interleaved
   desks → shorts tail (§2).

None of these dictate the *aesthetic* (Beano-tabloid vs clean-editorial vs
newsprint-classic) — that is the human pick. They are the **shell** the chosen skin
will sit in, and every one of them is a token/CSS/`main.js` change, not a pipeline
change.

---

## Sources

- [Mobile Navigation Design: 8 Types, Examples & Best Practices (2026) — UXPin](https://www.uxpin.com/studio/blog/mobile-navigation-examples/)
- [Mobile App Navigation Design: 2026 UX Best Practices — Medium](https://medium.com/ui-ux-designing-trends/mobile-app-navigation-design-2026-ux-best-practices-5b2db901790d)
- [Bottom Navigation Bar on Mobile Websites: Should You Use It? — The Hangline](https://www.thehangline.com/bottom-navigation-bar-on-mobile-websites-should-you-use-it/)
- [Breakpoints in responsive web design: 2026 guide — Framer](https://www.framer.com/blog/responsive-breakpoints/)
- [Responsive Design Breakpoints in 2025 — BrowserStack](https://www.browserstack.com/guide/responsive-design-breakpoints)
- [Common Screen Sizes for Responsive Web Design in 2026 — Altamira](https://www.altamira.ai/blog/common-screen-sizes-for-responsive-web-design/)
- [16 Best Newspaper Website Designs 2026 — Colorlib](https://colorlib.com/wp/newspaper-website-design/)
- [The Guardian unveils redesigned app and homepage — Design Week](https://www.designweek.co.uk/the-guardian-unveils-redesigned-app-and-homepage/)
- [Axios Design System — shadcn.io](https://www.shadcn.io/design/axios)
- [Card UI Design: Best Practices and Examples — Mockplus](https://www.mockplus.com/blog/post/card-ui-design)
- [Responsive Typography Mastery (2026) — Tim Graf](https://timgraf.com/ui/responsive-typography-mastery-fluid-scaling-hierarchy-and-readability-strategies-for-multi-device-ux-ui-in-2026/)
- [Mastering typography in design systems with semantic tokens — UX Collective](https://uxdesign.cc/mastering-typography-in-design-systems-with-semantic-tokens-and-responsive-scaling-6ccd598d9f21)
- [Design Token Architecture 2026 — Tim Graf](https://timgraf.com/ui/design-token-architecture-2026-the-strategic-blueprint-for-scalable-design-systems/)
- [Dark Mode Design Best Practices in 2026 — Tech-RZ](https://www.tech-rz.com/blog/dark-mode-design-best-practices-in-2026/)
- [Editorial design principles that still matter in 2026 — Toast Design](https://www.toastdesign.co.uk/design-resources/editorial-design-principles-2026/)
- [Language selector best practices — SimpleLocalize](https://simplelocalize.io/blog/posts/language-selector-best-practices/)
- [Language Selector Design: Best Practices for Great UX — Linguise](https://www.linguise.com/blog/guide/best-practices-designing-language-selector/)
- [Website Language Selector: Examples & Best Practices — Centus](https://centus.com/blog/language-selector-guide)
- [Sticky audio player & native audio embeds — Beamly](https://beamly.com/platform-update-sticky-audio-player-native-audio-embeds-from-19-hosts-and-more/)
- [Sticky Player — Fusebox](https://fusebox.fm/features/sticky-player/)
- [fixed-podcast-player (sticky audio Web Component) — GitHub](https://github.com/nonsalant/fixed-podcast-player/)
