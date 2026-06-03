/**
 * main.js — The Craic Gazette (schema v3, deep-agent edition)
 *
 * Fetches paper_content.json and renders the daily paper: an AI headliner +
 * subarticles + shorts interleaved with the Marvel-voiced fun stories, per the
 * `layout` order. The "Under the Hood" drawer visualises the deep agent's run
 * (plan → subagent delegations → tool calls) from context.agent_trace.
 *
 * Schema v3:
 * {
 *   "date","generated_at","pipeline_version":"3.0",
 *   "edition": { "approved_by", "approved_at" },
 *   "ai": { "headliner": {...}, "subarticles": [...], "shorts": [...] },
 *   "fun": [ { title, body, source_url, persona, byline, satire_disclaimer,
 *              image_url, kind, _text_model, _image_model } ],
 *   "layout": [ "ai.headliner", "ai.subarticles.0", "ai.shorts.0", "fun.0", ... ],
 *   "context": { "agent_trace": [ {kind,name,detail} ], "files": [...] }
 * }
 */

'use strict';

// Content is served from the SAME origin as the page (the CDN in production, a
// preview server locally / on the LAN), so always fetch it origin-relative —
// this avoids the CORS errors you'd hit pointing at an absolute host.
const CONTENT_PATH = (y, m, d) => `/content/${y}/${m}/${d}/paper_content.json`;
const MAX_FALLBACK_DAYS = 14;

let currentPaperData = null;
const el = id => document.getElementById(id);

// ════════════════════════════════════════════════════════════════════════════
// DATA FETCHING
// ════════════════════════════════════════════════════════════════════════════
async function fetchPaperContent(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  try {
    const resp = await fetch(CONTENT_PATH(y, m, d), { cache: 'no-cache' });
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

async function loadMostRecentEdition() {
  const today = new Date();
  for (let i = 0; i < MAX_FALLBACK_DAYS; i++) {
    const candidate = new Date(today);
    candidate.setDate(today.getDate() - i);
    const data = await fetchPaperContent(candidate);
    if (data) {
      currentPaperData = data;
      renderPaper(data);
      renderAbout(data);
      updateDateDisplay(candidate);
      return;
    }
  }
  renderPlaceholder();
}

async function loadEditionForDate(dateStr) {
  const [y, m, d] = dateStr.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  const data = await fetchPaperContent(date);
  if (data) {
    currentPaperData = data;
    renderPaper(data);
    renderAbout(data);
    updateDateDisplay(date);
  } else {
    alert(`No edition found for ${dateStr}. The Craic Gazette was probably on holidays.`);
  }
}

// ════════════════════════════════════════════════════════════════════════════
// SCHEMA HELPERS
// ════════════════════════════════════════════════════════════════════════════
function resolveRef(data, ref) {
  const parts = ref.split('.');
  try {
    if (ref === 'ai.headliner') return { type: 'ai', kind: 'headliner', item: data.ai.headliner };
    if (parts[0] === 'ai' && parts[1] === 'subarticles') return { type: 'ai', kind: 'sub', item: data.ai.subarticles[+parts[2]] };
    if (parts[0] === 'ai' && parts[1] === 'shorts') return { type: 'ai', kind: 'short', item: data.ai.shorts[+parts[2]] };
    if (parts[0] === 'fun') return { type: 'fun', kind: 'fun', item: data.fun[+parts[1]] };
  } catch { return null; }
  return null;
}

// ════════════════════════════════════════════════════════════════════════════
// RENDERING
// ════════════════════════════════════════════════════════════════════════════
function renderPaper(data) {
  const grid = el('edition');
  if (!grid) return;

  // Build the three front-page regions: a full-width Editor's Brief, the AI
  // analysis columns (1+2), and the fun desk (column 3). Cards are placed by their
  // resolved TYPE — not woven together — so each desk stays in its column. The
  // schema's layout[] is still honoured for ordering within a desk.
  grid.innerHTML = '';
  const briefRegion = node('section', 'edition-brief');
  const aiRegion = node('section', 'edition-ai');
  const funRegion = node('aside', 'edition-fun');
  grid.append(briefRegion, aiRegion, funRegion);

  const brief = briefCard(data.editors_brief);
  if (brief) briefRegion.append(brief);

  const layout = Array.isArray(data.layout) && data.layout.length
    ? data.layout
    : defaultLayout(data);
  for (const ref of layout) {
    const resolved = resolveRef(data, ref);
    if (!resolved || !resolved.item) continue;
    if (resolved.type === 'fun') funRegion.append(funCard(resolved.item));
    else aiRegion.append(aiCard(resolved.item, resolved.kind));
  }
  // Safety net: if layout omitted the fun pieces, fall back to the fun array.
  if (!funRegion.childElementCount) {
    (data.fun || []).forEach(item => item && funRegion.append(funCard(item)));
  }

  renderAttribution(data);
  renderHood(data);
}

/** The full-width Editor's Brief band: portrait byline + Graham's whole-edition synthesis. */
function briefCard(brief) {
  if (!brief || !brief.body) return null;
  const art = node('article', 'card editors-brief');
  art.append(kicker("THE EDITOR'S BRIEF", 'red'));
  const head = node('div', 'brief-head');
  const img = document.createElement('img');
  img.className = 'brief-portrait';
  img.src = 'static_assets/images/GeekwiththePeak.png';
  img.alt = 'Graham — Editor-in-Chief';
  img.loading = 'lazy';
  head.append(img, node('div', 'brief-byline', 'Graham · Editor-in-Chief'));
  art.append(head);
  if (brief.title) art.append(headline(brief.title, false));
  art.append(body(brief.body));
  art.append(meta(brief, false));
  return art;
}

/** The About page (about.html): the editor's portrait + the daily Father-Ted bio. */
function renderAbout(data) {
  const root = el('about');
  if (!root) return;                       // not on the About page — no-op
  const about = (data && data.about) || {};
  root.innerHTML = '';
  const art = node('article', 'card about-card');
  art.append(kicker('MEET THE EDITOR-IN-CHIEF', 'red'));
  const img = document.createElement('img');
  img.className = 'about-portrait';
  img.src = 'static_assets/images/GeekwiththePeak.png';
  img.alt = 'Graham — Editor-in-Chief';
  img.loading = 'lazy';
  art.append(img);
  art.append(headline(about.title || 'About the Editor', false));
  if (about.body) {
    art.append(body(about.body));
    art.append(meta(about, false));
  } else {
    art.append(body('The editor is still writing his memoirs — check back after the next edition.'));
  }
  root.append(art);
}

function defaultLayout(data) {
  const refs = ['ai.headliner'];
  (data.ai?.subarticles || []).forEach((_, i) => refs.push(`ai.subarticles.${i}`));
  (data.ai?.shorts || []).forEach((_, i) => refs.push(`ai.shorts.${i}`));
  (data.fun || []).forEach((_, i) => refs.push(`fun.${i}`));
  return refs;
}

function imageEl(item) {
  if (!item.image_url) return null;
  const img = document.createElement('img');
  img.className = 'card-img';
  img.src = item.image_url;
  img.alt = item.image_alt || item.title || '';
  img.loading = 'lazy';
  return img;
}

function aiCard(item, kind) {
  const lead = kind === 'headliner';
  const art = document.createElement('article');
  art.className = `card card--ai ${lead ? 'card--lead' : kind === 'sub' ? 'card--sub' : 'card--short'}`;
  art.append(kicker(lead ? 'HEADLINE' : kind === 'sub' ? 'AI DESK' : 'IN BRIEF', 'red'));
  art.append(headline(item.title, lead));
  if (item.standfirst) art.append(node('p', 'standfirst', item.standfirst));
  const img = imageEl(item);            // headliner + subarticles carry a photo
  if (img) art.append(img);
  art.append(body(item.body));
  art.append(meta(item, false));
  return art;
}

function funCard(item) {
  const art = document.createElement('article');
  const isAd = item.kind === 'ad';
  art.className = `card card--fun ${isAd ? 'card--ad' : ''}`;
  art.append(kicker(isAd ? 'A WORD FROM OUR (PRETEND) SPONSOR' : `FUN DESK · ${item.persona || ''}`, 'gold'));
  const img = imageEl(item);
  if (img) art.append(img);
  art.append(headline(item.title, false));
  if (item.byline) art.append(node('p', 'byline', item.byline));
  art.append(body(item.body));
  art.append(meta(item, true));
  return art;
}

function kicker(text, tone) {
  return node('div', `kicker kicker--${tone}`, text);
}

function headline(text, lead) {
  return node(lead ? 'h2' : 'h3', `headline ${lead ? 'headline--lead' : ''}`, text || '');
}

function body(text) {
  const div = document.createElement('div');
  div.className = 'body';
  const paras = String(text || '').split(/\n\n+/).map(p => p.trim()).filter(Boolean);
  (paras.length ? paras : [String(text || '')]).forEach(p => div.append(node('p', '', p)));
  return div;
}

/** The per-article footer: source link + the subtle "generated by" note + disclaimer. */
function meta(item, isFun) {
  const wrap = document.createElement('div');
  wrap.className = 'card-meta';
  if (item.source_url) {
    const a = document.createElement('a');
    a.className = 'source-link';
    a.href = item.source_url;
    a.target = '_blank';
    a.rel = 'noopener';
    a.textContent = '↗ source';
    wrap.append(a);
  }
  const models = [item._text_model, item._image_model].filter(Boolean).join(' · ');
  if (models) wrap.append(node('span', 'model-note', `✨ generated by ${models}`));
  if (isFun && item.satire_disclaimer) wrap.append(node('p', 'disclaimer', item.satire_disclaimer));
  return wrap;
}

function renderAttribution(data) {
  const note = el('edition-attribution');
  if (note) {
    const approved = data.edition?.approved_by ? '✓ approved' : '⏳ draft';
    note.textContent = `${data.pipeline_version ? 'v' + data.pipeline_version : ''} · ${approved}`;
  }
}

// ── Under the Hood: deep-agent visualiser ──────────────────────────────────
const TRACE_ICON = {
  plan: '🗒️', subagent: '🤝', tool: '🔧', vfs: '🗂️',
  structured: '📦', model: '🧠', fallback: '↩️', note: '•',
};
// One line per LangChain primitive — the "what am I looking at?" teaching note.
const TRACE_BLURB = {
  plan: 'Deep agents plan first — write_todos lays out the steps before acting.',
  subagent: 'The task tool spins up a focused sub-agent with its own context window.',
  tool: 'Tool-calling: the model invokes a Python @tool (search, fetch, validate).',
  vfs: "The deep agent's virtual filesystem persists research between steps.",
  structured: 'Structured output — a plain chat→JSON call the newsroom parses deterministically.',
  model: 'LiteLLM routes each model name to the right fleet box — no engine URLs in code.',
  fallback: 'A resilient fallback from the local model to a frontier safety net.',
  note: 'A milestone the harness recorded.',
};

function traceDetail(ev) {
  const d = ev.detail || {};
  if (ev.kind === 'plan') return `<ul class="trace-todos">${(d.todos || []).map(t => `<li>${escapeHtml(t)}</li>`).join('')}</ul>`;
  if (ev.kind === 'subagent') return `<div class="trace-detail">${escapeHtml(d.task || '')}</div>`;
  if (ev.kind === 'fallback') return `<div class="trace-detail">${escapeHtml(d.local || '')} → ${escapeHtml(d.to || '')} (${escapeHtml(d.reason || '')})</div>`;
  if (ev.kind === 'model') return `<div class="trace-detail"><code>${escapeHtml(d.model || '')}</code></div>`;
  if (ev.kind === 'vfs') return `<div class="trace-detail"><code>${escapeHtml(d.path || '')}</code></div>`;
  let html = d.info ? `<div class="trace-detail">${escapeHtml(d.info)}</div>` : '';
  if (d.result) html += `<div class="trace-result">↳ ${escapeHtml(d.result)}</div>`;  // a glimpse of the tool's output
  return html;
}

function renderHood(data) {
  const trace = data.context?.agent_trace || [];
  const traceEl = el('hood-trace');
  if (traceEl) {
    traceEl.innerHTML = trace.length
      ? trace.map(ev => `<div class="trace-row trace-row--${ev.kind}">
          <span class="trace-icon">${TRACE_ICON[ev.kind] || '•'}</span>
          <div class="trace-main">
            <span class="trace-name">${escapeHtml(ev.name || ev.kind)}</span>
            <span class="trace-blurb">${escapeHtml(TRACE_BLURB[ev.kind] || '')}</span>
            ${traceDetail(ev)}
          </div>
        </div>`).join('')
      : '<p class="hood-placeholder">No agent trace recorded for this edition.</p>';
  }

  const counts = trace.reduce((acc, e) => { acc[e.kind] = (acc[e.kind] || 0) + 1; return acc; }, {});
  const statEl = el('hood-stats');
  if (statEl) {
    const stat = (icon, n, label) => `<span class="hood-stat">${icon} ${n || 0} ${label}</span>`;
    statEl.innerHTML = [
      stat('🗒️', counts.plan, 'plans'),
      stat('🤝', counts.subagent, 'delegations'),
      stat('🔧', counts.tool, 'tool calls'),
      stat('🧠', counts.model, 'model routes'),
      stat('📦', counts.structured, 'JSON writes'),
      stat('🗂️', counts.vfs, 'file ops'),
      stat('↩️', counts.fallback, 'fallbacks'),
    ].join('');
  }
}

function renderPlaceholder() {
  const grid = el('edition');
  if (grid) grid.innerHTML =
    `<article class="card card--lead" style="grid-column:1/-1"><div class="kicker kicker--red">ER, ABOUT TODAY…</div>
     <h2 class="headline headline--lead">AI EDITOR TAKES THE DAY OFF; EXISTENTIAL CRISIS ENSUES</h2>
     <div class="body"><p>No edition was found for the last fortnight. The deep agent may not
     have run yet, or it's still waiting on a human to approve today's draft.</p></div></article>`;
}

// ════════════════════════════════════════════════════════════════════════════
// UI plumbing
// ════════════════════════════════════════════════════════════════════════════
function updateDateDisplay(date) {
  const dateEl = el('current-date');
  if (dateEl) dateEl.textContent = date.toLocaleDateString('en-IE',
    { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
}

function initDatePicker() {
  const input = el('date-picker');
  if (!input) return;
  input.type = 'date';
  input.max = toISODate(new Date());
  input.addEventListener('change', e => { if (e.target.value) loadEditionForDate(e.target.value); });
}

function initHoodDrawer() {
  const toggle = el('hood-toggle');
  const content = el('hood-content');
  if (!toggle || !content) return;
  toggle.addEventListener('click', () => {
    const expanded = toggle.getAttribute('aria-expanded') === 'true';
    toggle.setAttribute('aria-expanded', String(!expanded));
    content.hidden = expanded;
  });
}

function initNewsletter() {
  const form = el('newsletter-form');
  if (!form) return;
  form.addEventListener('submit', e => {
    e.preventDefault();
    const msg = el('newsletter-msg');
    if (msg) msg.textContent = "Thanks! Sign-ups open in a future edition — you're on the list in spirit.";
    form.reset();
  });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = String(str ?? '');
  return div.innerHTML;
}
function node(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}
function toISODate(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

// ════════════════════════════════════════════════════════════════════════════
// BOOT
// ════════════════════════════════════════════════════════════════════════════
async function init() {
  const fy = el('footer-year');
  if (fy) fy.textContent = new Date().getFullYear();
  initDatePicker();
  initHoodDrawer();
  initNewsletter();
  await loadMostRecentEdition();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
