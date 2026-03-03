/**
 * main.js — The Craic Gazette comparator frontend
 *
 * Fetches paper_content.json from S3 and renders the selected LLM provider's
 * content into the newspaper layout. Handles model switching, Compare All mode,
 * the "Under the Hood" trace drawer, and date navigation.
 *
 * Pipeline v2 JSON schema:
 * {
 *   "date": "YYYY-MM-DD",
 *   "context": { "news_headlines": [], "weather": {}, "research_trace": [] },
 *   "articles": {
 *     "main_article": {
 *       "outputs": {
 *         "claude": { "title": "", "content": "", "_model_id": "", "_latency_ms": 0 },
 *         "gemini": { ... },
 *         "local":  { ... }
 *       }
 *     },
 *     ...
 *   }
 * }
 */

'use strict';

// ── Configuration ─────────────────────────────────────────────────────────────

// Base URL where S3 content is served from (via CloudFront).
const S3_BASE_URL = 'https://craicgpt.ie';

// Content path template: base + /content/YYYY/MM/DD/paper_content.json
const CONTENT_PATH = (y, m, d) =>
  `${S3_BASE_URL}/content/${y}/${m}/${d}/paper_content.json`;

// How many days back to search for the most recent available edition.
const MAX_FALLBACK_DAYS = 14;

// ── State ─────────────────────────────────────────────────────────────────────

let currentPaperData = null;   // The full parsed paper_content.json
let activeProvider   = 'claude'; // 'claude' | 'gemini' | 'local' | 'compare'
let activeCompareArticle = 'main_article';

// ── DOM references ─────────────────────────────────────────────────────────────

const el = id => document.getElementById(id);

const ARTICLE_MAP = {
  // Maps article_id in JSON to DOM elements in index.html
  // format: { titleEl, bodyEl, standfirstEl (optional) }
  main_article: {
    title:      el('main-article-title'),
    standfirst: el('main-article-standfirst'),
    body:       el('main-article-text'),
  },
  comparison_article: {
    title: el('comparison-article-title'),
    body:  el('comparison-article-text'),
  },
  llm_muse: {
    body: el('llm-muse-text'),
  },
  daily_joke: {
    body: el('joke-text'),
  },
  editors_note: {
    body: el('editors-note-text'),
  },
};


// ════════════════════════════════════════════════════════════════════════════
// DATA FETCHING
// ════════════════════════════════════════════════════════════════════════════

/**
 * Fetch paper_content.json for the given Date object.
 * Returns the parsed JSON or null on failure.
 */
async function fetchPaperContent(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  const url = CONTENT_PATH(y, m, d);

  try {
    const resp = await fetch(url, { cache: 'no-cache' });
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

/**
 * Walk backwards from today to find the most recent available edition.
 * Updates the date picker and current-date display.
 */
async function loadMostRecentEdition() {
  const today = new Date();
  for (let i = 0; i < MAX_FALLBACK_DAYS; i++) {
    const candidate = new Date(today);
    candidate.setDate(today.getDate() - i);

    const data = await fetchPaperContent(candidate);
    if (data) {
      currentPaperData = data;
      renderPaper(data, activeProvider);
      updateDateDisplay(candidate);
      return;
    }
  }
  // Nothing found — render placeholders
  renderPlaceholders();
}

/**
 * Load content for a specific date (from the date picker).
 */
async function loadEditionForDate(dateStr) {
  const [y, m, d] = dateStr.split('-').map(Number);
  const date = new Date(y, m - 1, d);

  const data = await fetchPaperContent(date);
  if (data) {
    currentPaperData = data;
    renderPaper(data, activeProvider);
    updateDateDisplay(date);
  } else {
    alert(`No edition found for ${dateStr}. The Craic Gazette was probably on holidays.`);
  }
}


// ════════════════════════════════════════════════════════════════════════════
// RENDERING
// ════════════════════════════════════════════════════════════════════════════

/**
 * Main render entry point. Called whenever provider changes or new data loads.
 */
function renderPaper(data, provider) {
  if (provider === 'compare') {
    renderCompareMode(data);
    return;
  }
  renderSingleProvider(data, provider);
  updateModelBadge(data, provider);
  renderHoodContext(data);
}

/**
 * Render all articles for a single provider into the newspaper grid.
 */
function renderSingleProvider(data, provider) {
  const articles = data.articles || {};

  for (const [articleId, domRefs] of Object.entries(ARTICLE_MAP)) {
    const articleData = articles[articleId];
    if (!articleData) continue;

    const output = articleData.outputs?.[provider] || {};

    if (domRefs.title) {
      domRefs.title.textContent = output.title || `[No title from ${provider}]`;
    }
    if (domRefs.standfirst && output.standfirst) {
      domRefs.standfirst.textContent = output.standfirst;
    }
    if (domRefs.body) {
      // Split content on double newline into paragraphs
      const content = output.content || output.error || `Content unavailable from ${provider}.`;
      domRefs.body.innerHTML = contentToParagraphs(content);

      // Tag the element with prompt data for the tooltip
      domRefs.body.dataset.promptText = formatPromptTooltip(articleId, data);
      domRefs.body.dataset.modelId = output._model_id || '';
      domRefs.body.dataset.latencyMs = output._latency_ms || '';
    }
  }

  // Render model stats in the editor cell
  renderModelStats(data);

  // Special: daily joke needs split setup/punchline rendering
  renderJoke(data, provider);
}

/**
 * Convert a content string to HTML paragraphs.
 * Splits on double-newline or newline-newline.
 */
function contentToParagraphs(text) {
  if (!text) return '<p></p>';
  const paras = text.split(/\n\n+/).map(p => p.trim()).filter(Boolean);
  if (paras.length === 0) return `<p>${escapeHtml(text)}</p>`;
  return paras.map(p => `<p>${escapeHtml(p)}</p>`).join('');
}

/**
 * Render the daily joke with separate setup / punchline elements.
 */
function renderJoke(data, provider) {
  const jokeCell = el('joke-text');
  if (!jokeCell) return;

  const jokeOutput = data.articles?.daily_joke?.outputs?.[provider] || {};
  const setup = jokeOutput.setup || '';
  const punchline = jokeOutput.punchline || '';
  const content = jokeOutput.content || jokeOutput.error || '';

  if (setup && punchline) {
    jokeCell.innerHTML = `
      <p class="joke-setup">${escapeHtml(setup)}</p>
      <p class="joke-punchline">${escapeHtml(punchline)}</p>
    `;
  } else if (content) {
    jokeCell.innerHTML = contentToParagraphs(content);
  }
}

/**
 * Render the model performance stats card in the editor sidebar.
 */
function renderModelStats(data) {
  const grid = el('model-stats-grid');
  if (!grid || !data.articles) return;

  // Aggregate average latency per provider across all articles.
  const latencies = { claude: [], gemini: [], local: [] };

  for (const article of Object.values(data.articles)) {
    for (const [prov, output] of Object.entries(article.outputs || {})) {
      if (output._latency_ms && latencies[prov]) {
        latencies[prov].push(output._latency_ms);
      }
    }
  }

  const avg = arr => arr.length ? Math.round(arr.reduce((a, b) => a + b, 0) / arr.length) : null;

  const providers = [
    { key: 'claude', label: '🟣 Claude', cls: 'claude' },
    { key: 'gemini', label: '🔵 Gemini', cls: 'gemini' },
    { key: 'local',  label: '🟢 Local',  cls: 'local'  },
  ];

  grid.innerHTML = providers.map(({ key, label, cls }) => {
    const ms = avg(latencies[key]);
    const val = ms !== null ? `${(ms / 1000).toFixed(1)}s` : 'n/a';
    return `
      <div class="model-stat-card model-stat-card--${cls}">
        <div class="stat-label">${label}</div>
        <div class="stat-value">${val}</div>
      </div>`;
  }).join('');
}

/**
 * Update the model badge in the sticky nav bar with the active model ID.
 */
function updateModelBadge(data, provider) {
  const idEl = el('active-model-id');
  const latEl = el('active-model-latency');
  if (!idEl || !latEl) return;

  // Get model_id from the first article that has this provider.
  const firstArticle = Object.values(data.articles || {})[0];
  const output = firstArticle?.outputs?.[provider] || {};

  idEl.textContent  = output._model_id || provider;
  latEl.textContent = output._latency_ms ? `avg ~${output._latency_ms}ms` : '';
}

/**
 * Render the "Compare All" three-column panel.
 */
function renderCompareMode(data) {
  renderCompareArticle(data, activeCompareArticle);
}

function renderCompareArticle(data, articleId) {
  const article = data.articles?.[articleId] || {};
  const outputs = article.outputs || {};

  const providers = ['claude', 'gemini', 'local'];
  const colMeta = {
    claude: { metaEl: el('compare-claude-meta'), bodyEl: el('compare-claude-body') },
    gemini: { metaEl: el('compare-gemini-meta'), bodyEl: el('compare-gemini-body') },
    local:  { metaEl: el('compare-local-meta'),  bodyEl: el('compare-local-body')  },
  };

  for (const provider of providers) {
    const output = outputs[provider] || {};
    const { metaEl, bodyEl } = colMeta[provider];

    if (metaEl) {
      const modelId = output._model_id || 'unavailable';
      const latency = output._latency_ms ? ` · ${(output._latency_ms / 1000).toFixed(1)}s` : '';
      metaEl.textContent = `${modelId}${latency}`;
    }

    if (bodyEl) {
      let html = '';
      if (output.title) {
        html += `<h4 style="font-family:var(--font-headline);margin-bottom:.5rem">${escapeHtml(output.title)}</h4>`;
      }
      if (output.standfirst) {
        html += `<p style="font-style:italic;opacity:.75;margin-bottom:.5rem">${escapeHtml(output.standfirst)}</p>`;
      }
      if (output.setup) {
        html += `<p><strong>${escapeHtml(output.setup)}</strong></p>`;
        html += `<p style="font-style:italic;color:var(--red)">${escapeHtml(output.punchline || '')}</p>`;
      } else {
        html += contentToParagraphs(output.content || output.error || 'No content available.');
      }
      if (output._latency_ms) {
        html += `<p style="margin-top:.75rem;font-size:.7rem;opacity:.5">Generated in ${output._latency_ms}ms</p>`;
      }
      bodyEl.innerHTML = html;
    }
  }
}

/**
 * Populate the "Under the Hood" drawer with research context.
 */
function renderHoodContext(data) {
  const contextEl = el('hood-context');
  const traceEl   = el('hood-trace');
  if (!data?.context) return;

  const ctx = data.context;

  // Weather + headlines
  if (contextEl) {
    const weather = ctx.weather || {};
    const headlines = ctx.news_headlines || [];
    let html = '<dl>';
    if (weather.location) {
      html += `<dt>Weather</dt><dd>${weather.temp_c}°C — ${weather.conditions} in ${weather.location}</dd>`;
    }
    if (headlines.length) {
      html += `<dt>Headlines (${headlines.length})</dt>`;
      headlines.forEach(h => { html += `<dd>• ${escapeHtml(h.slice(0, 100))}</dd>`; });
    }
    if (ctx.ai_trends) {
      html += `<dt>AI Trends</dt><dd>${escapeHtml(ctx.ai_trends.slice(0, 200))}…</dd>`;
    }
    html += '</dl>';
    contextEl.innerHTML = html;
  }

  // Agent trace
  if (traceEl && ctx.research_trace?.length) {
    traceEl.innerHTML = ctx.research_trace.map(entry => `
      <div class="trace-entry">
        <span class="trace-entry-role">${escapeHtml(entry.role || '')}</span>
        <div class="trace-entry-content">${escapeHtml(String(entry.content || '').slice(0, 400))}</div>
      </div>
    `).join('');
  }
}

/**
 * Format a tooltip string showing the prompt for a given article.
 */
function formatPromptTooltip(articleId, data) {
  const article = data.articles?.[articleId];
  if (!article) return '';
  return [
    `Article: ${articleId}`,
    `LangChain node: ${article.langchain_node || 'generate/RunnableParallel'}`,
    article.prompt_text ? `\nPrompt:\n${article.prompt_text.slice(0, 500)}` : '',
  ].filter(Boolean).join('\n');
}

/**
 * Show placeholder text when no edition is available.
 */
function renderPlaceholders() {
  el('main-article-title').textContent = 'AI JOURNALIST TAKES DAY OFF; EXISTENTIAL CRISIS ENSUES';
  el('main-article-standfirst').textContent =
    'Sources close to the language model confirm it simply "needed a moment."';
  el('main-article-text').innerHTML =
    '<p>No content was found for today. The pipeline may not have run yet, ' +
    'or your AWS credentials need updating. Check the GitHub Actions logs for clues.</p>';
}


// ════════════════════════════════════════════════════════════════════════════
// UI — MODEL TABS
// ════════════════════════════════════════════════════════════════════════════

function initModelTabs() {
  document.querySelectorAll('.model-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const provider = tab.dataset.provider;
      setActiveProvider(provider);
    });
  });
}

function setActiveProvider(provider) {
  activeProvider = provider;

  // Update tab active states
  document.querySelectorAll('.model-tab').forEach(t => {
    const isActive = t.dataset.provider === provider;
    t.classList.toggle('active', isActive);
    t.setAttribute('aria-selected', isActive ? 'true' : 'false');
  });

  // Toggle body class for CSS provider colours
  document.body.classList.remove('provider-claude', 'provider-gemini', 'provider-local');
  if (['claude', 'gemini', 'local'].includes(provider)) {
    document.body.classList.add(`provider-${provider}`);
    document.body.classList.remove('compare-mode');
  } else if (provider === 'compare') {
    document.body.classList.add('compare-mode');
  }

  if (currentPaperData) {
    renderPaper(currentPaperData, provider);
  }
}

// ── Compare article tabs ──────────────────────────────────────────────────────

function initCompareArticleTabs() {
  document.querySelectorAll('.compare-article-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.compare-article-tab')
        .forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      activeCompareArticle = tab.dataset.article;
      if (currentPaperData) {
        renderCompareArticle(currentPaperData, activeCompareArticle);
      }
    });
  });
}


// ════════════════════════════════════════════════════════════════════════════
// UI — DATE PICKER
// ════════════════════════════════════════════════════════════════════════════

function initDatePicker() {
  const input = el('date-picker');
  if (!input) return;

  // Use the js-datepicker vendor library if available, else a plain input.
  if (typeof datepicker === 'function') {
    datepicker('#date-picker', {
      onSelect: (inst, date) => {
        if (!date) return;
        const iso = toISODate(date);
        loadEditionForDate(iso);
      },
      maxDate: new Date(),
      startDay: 1, // Monday start
    });
  } else {
    // Fallback: plain date input
    input.type = 'date';
    input.max  = toISODate(new Date());
    input.addEventListener('change', e => {
      if (e.target.value) loadEditionForDate(e.target.value);
    });
  }
}

function updateDateDisplay(date) {
  const dateEl = el('current-date');
  if (dateEl) {
    dateEl.textContent = date.toLocaleDateString('en-IE', {
      weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
    });
  }
}


// ════════════════════════════════════════════════════════════════════════════
// UI — "UNDER THE HOOD" DRAWER
// ════════════════════════════════════════════════════════════════════════════

function initHoodDrawer() {
  const toggle  = el('hood-toggle');
  const content = el('hood-content');
  if (!toggle || !content) return;

  toggle.addEventListener('click', () => {
    const expanded = toggle.getAttribute('aria-expanded') === 'true';
    toggle.setAttribute('aria-expanded', String(!expanded));
    if (expanded) {
      content.hidden = true;
    } else {
      content.hidden = false;
    }
  });
}


// ════════════════════════════════════════════════════════════════════════════
// UI — PROMPT TOOLTIP
// ════════════════════════════════════════════════════════════════════════════

function initPromptTooltips() {
  const tooltip = el('prompt-tooltip');
  const header  = el('tooltip-header');
  const body    = el('tooltip-body');
  if (!tooltip) return;

  let hideTimer;

  document.addEventListener('mouseover', e => {
    const target = e.target.closest('[data-prompt-type]');
    if (!target) return;

    clearTimeout(hideTimer);
    const promptText = target.dataset.promptText || target.dataset.promptFile || '';
    const type = target.dataset.promptType || 'prompt';

    if (!promptText) return;

    header.textContent = `Prompt — ${type}`;
    body.textContent   = promptText;
    tooltip.hidden     = false;
    tooltip.classList.add('visible');
    positionTooltip(tooltip, e);
  });

  document.addEventListener('mousemove', e => {
    if (!tooltip.hidden) positionTooltip(tooltip, e);
  });

  document.addEventListener('mouseout', e => {
    if (!e.target.closest('[data-prompt-type]')) return;
    hideTimer = setTimeout(() => {
      tooltip.classList.remove('visible');
      setTimeout(() => { tooltip.hidden = true; }, 150);
    }, 200);
  });
}

function positionTooltip(tooltip, e) {
  const margin = 16;
  const tw = tooltip.offsetWidth  || 340;
  const th = tooltip.offsetHeight || 100;
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  let x = e.clientX + margin;
  let y = e.clientY + margin;

  if (x + tw > vw) x = e.clientX - tw - margin;
  if (y + th > vh) y = e.clientY - th - margin;

  tooltip.style.left = `${Math.max(4, x)}px`;
  tooltip.style.top  = `${Math.max(4, y)}px`;
}


// ════════════════════════════════════════════════════════════════════════════
// UI — WEATHER LINE IN MASTHEAD
// ════════════════════════════════════════════════════════════════════════════

function updateWeatherLine(data) {
  const weatherEl = el('weather-line');
  if (!weatherEl || !data?.context?.weather) return;

  const w = data.context.weather;
  const icon = weatherIcon(w.conditions || '');
  weatherEl.textContent =
    `${icon} ${w.location}: ${w.temp_c}°C — ${w.conditions}`;
}

function weatherIcon(conditions) {
  const c = (conditions || '').toLowerCase();
  if (c.includes('sun') || c.includes('clear')) return '☀️';
  if (c.includes('rain') || c.includes('shower')) return '🌧️';
  if (c.includes('cloud') || c.includes('overcast')) return '☁️';
  if (c.includes('snow')) return '❄️';
  if (c.includes('fog') || c.includes('mist')) return '🌫️';
  if (c.includes('thunder') || c.includes('storm')) return '⛈️';
  if (c.includes('drizzle')) return '🌦️';
  return '🌤️';
}


// ════════════════════════════════════════════════════════════════════════════
// UTILITIES
// ════════════════════════════════════════════════════════════════════════════

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}

function toISODate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}


// ════════════════════════════════════════════════════════════════════════════
// BOOT
// ════════════════════════════════════════════════════════════════════════════

async function init() {
  // Set footer year
  const fyEl = el('footer-year');
  if (fyEl) fyEl.textContent = new Date().getFullYear();

  // Wire up UI
  initModelTabs();
  initCompareArticleTabs();
  initDatePicker();
  initHoodDrawer();
  initPromptTooltips();

  // Load content — most recent available edition
  await loadMostRecentEdition();

  // Update weather line from loaded data
  if (currentPaperData) {
    updateWeatherLine(currentPaperData);
  }
}

// Start when the DOM is ready.
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
