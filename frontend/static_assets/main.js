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
  const layout = Array.isArray(data.layout) && data.layout.length
    ? data.layout
    : defaultLayout(data);

  grid.innerHTML = '';
  for (const ref of layout) {
    const resolved = resolveRef(data, ref);
    if (!resolved || !resolved.item) continue;
    grid.appendChild(resolved.type === 'fun'
      ? funCard(resolved.item)
      : aiCard(resolved.item, resolved.kind));
  }

  renderAttribution(data);
  renderHood(data);
}

function defaultLayout(data) {
  const refs = ['ai.headliner'];
  (data.ai?.subarticles || []).forEach((_, i) => refs.push(`ai.subarticles.${i}`));
  (data.ai?.shorts || []).forEach((_, i) => refs.push(`ai.shorts.${i}`));
  (data.fun || []).forEach((_, i) => refs.push(`fun.${i}`));
  return refs;
}

function aiCard(item, kind) {
  const lead = kind === 'headliner';
  const art = document.createElement('article');
  art.className = `card card--ai ${lead ? 'card--lead' : kind === 'sub' ? 'card--sub' : 'card--short'}`;
  art.append(kicker(lead ? 'HEADLINE' : kind === 'sub' ? 'AI DESK' : 'IN BRIEF', 'red'));
  art.append(headline(item.title, lead));
  if (item.standfirst) art.append(node('p', 'standfirst', item.standfirst));
  art.append(body(item.body));
  art.append(meta(item, false));
  return art;
}

function funCard(item) {
  const art = document.createElement('article');
  const isAd = item.kind === 'ad';
  art.className = `card card--fun ${isAd ? 'card--ad' : ''}`;
  art.append(kicker(isAd ? 'A WORD FROM OUR (PRETEND) SPONSOR' : `FUN DESK · ${item.persona || ''}`, 'gold'));
  if (item.image_url) {
    const img = document.createElement('img');
    img.className = 'card-img';
    img.src = item.image_url;
    img.alt = item.image_alt || item.title || '';
    img.loading = 'lazy';
    art.append(img);
  }
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
const TRACE_ICON = { plan: '🗒️', subagent: '🤝', tool: '🔧', fallback: '↩️', note: '•' };

function renderHood(data) {
  const trace = data.context?.agent_trace || [];
  const traceEl = el('hood-trace');
  if (traceEl) {
    if (!trace.length) {
      traceEl.innerHTML = '<p class="hood-placeholder">No agent trace recorded for this edition.</p>';
    } else {
      traceEl.innerHTML = trace.map(ev => {
        const icon = TRACE_ICON[ev.kind] || '•';
        let detail = '';
        if (ev.kind === 'plan') detail = (ev.detail?.todos || []).map(t => `<li>${escapeHtml(t)}</li>`).join('');
        else if (ev.kind === 'subagent') detail = `<div class="trace-detail">${escapeHtml(ev.detail?.task || '')}</div>`;
        else if (ev.kind === 'fallback') detail = `<div class="trace-detail">${escapeHtml(ev.detail?.local || '')} → ${escapeHtml(ev.detail?.to || '')} (${escapeHtml(ev.detail?.reason || '')})</div>`;
        else detail = `<div class="trace-detail">${escapeHtml(ev.detail?.info || '')}</div>`;
        return `<div class="trace-row trace-row--${ev.kind}">
          <span class="trace-icon">${icon}</span>
          <div class="trace-main"><span class="trace-name">${escapeHtml(ev.name || ev.kind)}</span>
          ${ev.kind === 'plan' ? `<ul class="trace-todos">${detail}</ul>` : detail}</div>
        </div>`;
      }).join('');
    }
  }

  const counts = trace.reduce((acc, e) => { acc[e.kind] = (acc[e.kind] || 0) + 1; return acc; }, {});
  const statEl = el('hood-stats');
  if (statEl) {
    statEl.innerHTML = `
      <span class="hood-stat">🗒️ ${counts.plan || 0} plans</span>
      <span class="hood-stat">🤝 ${counts.subagent || 0} delegations</span>
      <span class="hood-stat">🔧 ${counts.tool || 0} tool calls</span>
      <span class="hood-stat">↩️ ${counts.fallback || 0} fallbacks</span>`;
  }
}

function renderPlaceholder() {
  const grid = el('edition');
  if (grid) grid.innerHTML =
    `<article class="card card--lead"><div class="kicker kicker--red">ER, ABOUT TODAY…</div>
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
