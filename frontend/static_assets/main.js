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
 *   // any article may carry an additive _qc:{flag,reason,by} marker — the advisory
 *   // per-article gate stamps a flagged story; the UI renders a quality-control banner.
 *   "layout": [ "ai.headliner", "ai.subarticles.0", "ai.shorts.0", "fun.0", ... ],
 *   "context": { "agent_trace": [ {kind,name,detail} ], "files": [...] }
 * }
 */

'use strict';

// Content is served from the SAME origin as the page (the CDN in production, a
// preview server locally / on the LAN), so always fetch it origin-relative —
// this avoids the CORS errors you'd hit pointing at an absolute host.
// Read live content/ by default, or the preview/ draft when ?edition=preview is in the
// URL — lets Graham review an un-published, audio-enriched edition from his phone.
// ── Internationalisation ────────────────────────────────────────────────────
// The site is served under a language path prefix (/en/, /de/, …). On S3 the English
// content lives at the ROOT (content/…) and /en/* is a CloudFront alias to it, so the
// frontend can treat every language uniformly: it always fetches /<lang>/content/… and
// the CDN maps /en/* → /* for the source language. LANG = the first path segment.
const KNOWN_LANGS = ['en', 'de', 'es', 'it', 'ja', 'fr'];
const SOURCE_LANG = 'en';
const LANG = (() => {
  const seg = location.pathname.split('/').filter(Boolean)[0];
  return KNOWN_LANGS.includes(seg) ? seg : SOURCE_LANG;
})();
const LOCALES = { en: 'en-IE', de: 'de-DE', es: 'es-ES', it: 'it-IT', ja: 'ja-JP', fr: 'fr-FR' };
// Endonyms (each language's own name) + the flag file it shows in the switcher. English maps
// to the Irish tricolour: this is Ireland's paper and English is the source edition.
const LANG_NAMES = { en: 'English', de: 'Deutsch', es: 'Español', it: 'Italiano', ja: '日本語', fr: 'Français' };
const LANG_FLAG  = { en: 'ie', de: 'de', es: 'es', it: 'it', ja: 'jp', fr: 'fr' };

// UI-chrome strings per language (English is the fallback). Article CONTENT is translated
// server-side and arrives in paper_content.json; this table only covers the shell.
const I18N = {
  en: { listen: '🎧 Listen', podcast: 'Daily podcast', tldr: '90-sec headlines',
        transcript: 'transcript', download: 'Download the', latest: 'latest',
        fetching: "Fetching today's edition…", noEdition: 'No edition found for',
        dayOff: 'The Craic Gazette was probably on holidays.', changeDate: '📅 change date',
        translatedNote: 'This edition was machine-translated from English by {model} — blame the robot, not the editor.',
        readOriginal: 'Read the English original ↗',
        qcLabel: 'Quality control', qcNote: 'Flagged by our automated fact-check — read with a pinch of salt:' },
  de: { listen: '🎧 Hören', podcast: 'Täglicher Podcast', tldr: '90-Sek-Schlagzeilen',
        transcript: 'Transkript', download: 'Herunterladen:', latest: 'aktuell',
        fetching: 'Heutige Ausgabe wird geladen…', noEdition: 'Keine Ausgabe gefunden für',
        dayOff: 'Die Craic Gazette macht wohl gerade Urlaub.', changeDate: '📅 Datum ändern',
        translatedNote: 'Diese Ausgabe wurde von {model} maschinell aus dem Englischen übersetzt — schimpft mit dem Roboter, nicht mit der Redaktion.',
        readOriginal: 'Zum englischen Original ↗',
        qcLabel: 'Qualitätskontrolle', qcNote: 'Von unserer automatischen Faktenprüfung markiert — mit Vorsicht zu genießen:' },
  es: { listen: '🎧 Escuchar', podcast: 'Podcast diario', tldr: 'Titulares en 90 s',
        transcript: 'transcripción', download: 'Descargar', latest: 'última',
        fetching: 'Cargando la edición de hoy…', noEdition: 'No se encontró edición para',
        dayOff: 'La Craic Gazette estaría de vacaciones.', changeDate: '📅 cambiar fecha',
        translatedNote: 'Esta edición fue traducida automáticamente del inglés por {model} — la culpa es del robot, no de la redacción.',
        readOriginal: 'Leer el original en inglés ↗',
        qcLabel: 'Control de calidad', qcNote: 'Marcado por nuestra verificación automática — tómalo con cautela:' },
  it: { listen: '🎧 Ascolta', podcast: 'Podcast quotidiano', tldr: 'Titoli in 90 s',
        transcript: 'trascrizione', download: 'Scarica', latest: 'ultima',
        fetching: "Caricamento dell'edizione di oggi…", noEdition: 'Nessuna edizione trovata per',
        dayOff: 'La Craic Gazette sarà in vacanza.', changeDate: '📅 cambia data',
        translatedNote: "Questa edizione è stata tradotta automaticamente dall'inglese da {model} — prendetevela col robot, non con la redazione.",
        readOriginal: "Leggi l'originale in inglese ↗",
        qcLabel: 'Controllo qualità', qcNote: 'Segnalato dal nostro fact-check automatico — da prendere con le pinze:' },
  ja: { listen: '🎧 聴く', podcast: 'デイリーポッドキャスト', tldr: '90秒ヘッドライン',
        transcript: '文字起こし', download: 'ダウンロード', latest: '最新',
        fetching: '本日のエディションを読み込み中…', noEdition: 'エディションが見つかりません：',
        dayOff: 'クレイク・ガゼットはお休みのようです。', changeDate: '📅 日付を変更',
        translatedNote: 'この号は{model}により英語から機械翻訳されています。おかしな点はロボットのせいということで。',
        readOriginal: '英語の原文を読む ↗',
        qcLabel: '品質チェック', qcNote: '自動ファクトチェックがフラグを立てました。話半分でどうぞ：' },
  fr: { listen: '🎧 Écouter', podcast: 'Podcast quotidien', tldr: 'Titres en 90 s',
        transcript: 'transcription', download: 'Télécharger', latest: 'récente',
        fetching: "Chargement de l'édition du jour…", noEdition: 'Aucune édition trouvée pour',
        dayOff: 'La Craic Gazette est sans doute en vacances.', changeDate: '📅 changer de date',
        translatedNote: "Cette édition a été traduite automatiquement de l'anglais par {model} — blâmez le robot, pas la rédaction.",
        readOriginal: "Lire l'original en anglais ↗",
        qcLabel: 'Contrôle qualité', qcNote: 'Signalé par notre vérification automatique — à prendre avec des pincettes :' },
};
const t = (key) => ((I18N[LANG] || I18N.en)[key] ?? I18N.en[key] ?? key);

const EDITION_PREFIX =
  new URLSearchParams(location.search).get('edition') === 'preview' ? 'preview' : 'content';
const CONTENT_PATH = (y, m, d) => `/${LANG}/${EDITION_PREFIX}/${y}/${m}/${d}/paper_content.json`;
// Edition versioning: the manifest of the day's versions, and a specific snapshot.
const VERSIONS_PATH = (y, m, d) => `/${LANG}/${EDITION_PREFIX}/${y}/${m}/${d}/versions.json`;
const VERSION_PATH = (y, m, d, id) => `/${LANG}/${EDITION_PREFIX}/${y}/${m}/${d}/versions/${id}.json`;
const MAX_FALLBACK_DAYS = 14;

let currentPaperData = null;
let currentDate = null;        // the edition date currently shown (drives the version picker)
const el = id => document.getElementById(id);

/** A language link that preserves the current edition date + preview flag, so switching
 *  language keeps you on the same day's edition. */
function langHref(lang) {
  const qs = new URLSearchParams(location.search);
  if (currentDate) qs.set('date', toISODate(currentDate));
  const q = qs.toString();
  return `/${lang}/${q ? '?' + q : ''}`;
}

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
      currentDate = candidate;
      renderPaper(data);
      renderAbout(data);
      updateDateDisplay(candidate);
      await renderVersions(candidate);
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
    currentDate = date;
    renderPaper(data);
    renderAbout(data);
    updateDateDisplay(date);
    await renderVersions(date);
  } else {
    alert(`${t('noEdition')} ${dateStr}. ${t('dayOff')}`);
  }
}

// ── Edition versioning: a subtle picker for prior versions of the day ────────
// The day's edition can be revised (re-generated) several times; each publish is
// retained as an immutable version and the latest is shown by default. The picker
// only appears when there's more than one version — otherwise it stays hidden.
async function renderVersions(date) {
  const sel = el('version-select');
  if (!sel) return;
  sel.hidden = true;
  sel.innerHTML = '';
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  let versions = [];
  try {
    const resp = await fetch(VERSIONS_PATH(y, m, d), { cache: 'no-cache' });
    if (resp.ok) {
      const man = await resp.json();
      versions = Array.isArray(man.versions) ? man.versions : [];
    }
  } catch { /* no manifest → single-version day; leave the picker hidden */ }
  if (versions.length < 2) return;          // subtle: only shown when there's a real choice
  versions.forEach((v, i) => {              // manifest is newest-first; [0] is the latest
    const opt = node('option', '', i === 0 ? `${v.label} (${t('latest')})` : v.label);
    opt.value = v.id;
    sel.append(opt);
  });
  sel.value = versions[0].id;
  sel.hidden = false;
}

async function loadVersion(date, id) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  try {
    const resp = await fetch(VERSION_PATH(y, m, d, id), { cache: 'no-cache' });
    if (!resp.ok) return;
    const data = await resp.json();
    currentPaperData = data;
    renderPaper(data);
    renderAbout(data);
  } catch { /* keep the current view on error */ }
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
function renderStyleFooter(data) {
  // Every picture in an edition shares one cartoon style, cycling daily across four looks.
  // Saying so in the footer is the point of rotating at all: a returning reader sees the
  // range, and a tutorial reader sees a deterministic choice the model did NOT make.
  const p = el('footer-style');
  if (!p) return;
  const style = data?.edition?.cartoon_style;
  if (!style?.label) { p.hidden = true; return; }
  p.textContent = `Today's cartoons are drawn as a ${style.label}, one of four looks the paper rotates through daily. `
    + 'Each one illustrates a visual gag written for its own story.';
  p.hidden = false;
}

function renderPaper(data) {
  const grid = el('edition');
  if (!grid) return;
  renderStyleFooter(data);
  resetStickyPlayer();                          // stop audio from a previous version/date
  const oldTx = el('podcast-transcript-panel'); if (oldTx) oldTx.remove();

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

  renderPodcast(data);
  renderAttribution(data);
  renderHood(data);
  renderTranslationNote(data);
}

/** The subtle, light-hearted 'this page was machine-translated' note at the foot of a
 *  translated edition, naming the model and linking back to the English original. Shown
 *  only when the edition's language isn't the source (English shows nothing). */
function renderTranslationNote(data) {
  const old = el('translation-note'); if (old) old.remove();
  const ed = (data && data.edition) || {};
  const lang = ed.language || SOURCE_LANG;
  if (lang === SOURCE_LANG) return;
  const model = ed.translated_by || 'a local model';
  const note = node('div', 'translation-note'); note.id = 'translation-note';
  note.append(node('span', '', t('translatedNote').replace('{model}', model) + ' '));
  const a = document.createElement('a');
  a.className = 'translation-note-link';
  a.href = '/en/' + (location.search || '');     // the English original, same query (date/preview)
  a.textContent = t('readOriginal');
  note.append(a);
  const footer = document.querySelector('.site-footer');
  if (footer && footer.parentNode) footer.parentNode.insertBefore(note, footer);
  else document.body.append(note);
}

/** A small HD flag (SVG) for a language — decorative: the adjacent code/name is the real label. */
function flagImg(lang) {
  const img = document.createElement('img');
  img.className = 'lang-flag';
  img.src = `/static_assets/flags/${LANG_FLAG[lang] || 'ie'}.svg`;
  img.alt = ''; img.setAttribute('aria-hidden', 'true');
  img.width = 21; img.height = 14; img.loading = 'lazy';
  return img;
}

/** The masthead language switcher — a compact flag dropdown: the current language's flag + code,
 *  opening a menu of the rest. Each choice preserves the edition date/preview flag (langHref) and
 *  sets the cg_lang cookie so the CloudFront edge detector honours the override. Smaller than the
 *  old "EN DE ES…" text row and instantly recognisable; SVG flags (emoji flags fail on Windows). */
function renderLangSwitcher() {
  const strip = document.querySelector('.masthead-top-strip');
  if (!strip || el('lang-switcher')) return;
  const wrap = node('div', 'lang-switcher'); wrap.id = 'lang-switcher';

  // Trigger: current flag + code + caret.
  const btn = node('button', 'lang-trigger'); btn.type = 'button';
  btn.setAttribute('aria-haspopup', 'true');
  btn.setAttribute('aria-expanded', 'false');
  btn.setAttribute('aria-label', `Language: ${LANG_NAMES[LANG] || LANG.toUpperCase()}. Change language`);
  btn.append(flagImg(LANG), node('span', 'lang-code', LANG.toUpperCase()), node('span', 'lang-caret', '▾'));

  // Menu: every language (the current one marked), each a link to /<lang>/ on the same edition.
  const menu = node('nav', 'lang-menu'); menu.setAttribute('aria-label', 'Language'); menu.hidden = true;
  KNOWN_LANGS.forEach(lang => {
    const a = document.createElement('a');
    a.className = 'lang-option' + (lang === LANG ? ' is-current' : '');
    a.href = langHref(lang);
    a.setAttribute('lang', lang); a.setAttribute('hreflang', lang);
    if (lang === LANG) a.setAttribute('aria-current', 'true');
    a.append(flagImg(lang), node('span', 'lang-code', lang.toUpperCase()),
             node('span', 'lang-name', LANG_NAMES[lang] || ''));
    a.addEventListener('click', () => {
      document.cookie = `cg_lang=${lang}; path=/; max-age=31536000; samesite=lax`;
    });
    menu.append(a);
  });

  const setOpen = (open) => {
    menu.hidden = !open;
    btn.setAttribute('aria-expanded', String(open));
    wrap.classList.toggle('is-open', open);
    if (open) (menu.querySelector('.lang-option.is-current') || menu.querySelector('.lang-option'))?.focus();
  };
  btn.addEventListener('click', (e) => { e.stopPropagation(); setOpen(menu.hidden); });
  document.addEventListener('click', (e) => { if (!wrap.contains(e.target)) setOpen(false); });
  wrap.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { setOpen(false); btn.focus(); return; }
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    e.preventDefault();
    const links = Array.from(menu.querySelectorAll('.lang-option'));
    const i = links.indexOf(document.activeElement);
    (e.key === 'ArrowDown' ? (links[i + 1] || links[0]) : (links[i - 1] || links[links.length - 1])).focus();
  });

  wrap.append(btn, menu);
  strip.append(wrap);
}

/** The full-width Editor's Brief band: portrait byline + Graham's whole-edition synthesis. */
function briefCard(brief) {
  if (!brief || !brief.body) return null;
  const art = node('article', 'card editors-brief');
  art.append(kicker("THE EDITOR'S BRIEF", 'red'));
  const head = node('div', 'brief-head');
  const img = document.createElement('img');
  img.className = 'brief-portrait';
  img.src = '/static_assets/images/GeekwiththePeak.png';
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
  img.src = '/static_assets/images/GeekwiththePeak.png';
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
  renderTranslationNote(data);
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
  const qc = qcStamp(item); if (qc) art.append(qc);
  art.append(headline(item.title, lead));
  if (item.standfirst) art.append(node('p', 'standfirst', item.standfirst));
  const img = imageEl(item);            // every AI article carries a cartoon; shorts get a spot thumbnail
  if (img) art.append(img);
  art.append(body(item.body));
  art.append(meta(item, false));
  return art;
}

function funCard(item) {
  const art = document.createElement('article');
  const isAd = item.kind === 'ad';
  art.className = `card card--fun ${isAd ? 'card--ad' : ''}`;
  // Credited Irish-creator digest → show the creator; legacy parody → show the persona.
  const funCredit = item.source || item.persona || '';
  art.append(kicker(isAd ? 'A WORD FROM OUR (PRETEND) SPONSOR' : `CRAIC & THROTTLE · ${funCredit}`, 'gold'));
  const qc = qcStamp(item); if (qc) art.append(qc);
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

// QUALITY-CONTROL STAMP — the advisory per-article gate (2026-06-19) flags a fabricated
// or dead-link story with a `_qc` marker instead of dropping it; we publish it WITH this
// visible warning banner so readers see the caveat. Returns null when the item is clean.
function qcStamp(item) {
  const qc = item && item._qc;
  if (!qc || typeof qc !== 'object') return null;
  const wrap = node('div', 'qc-stamp');
  wrap.setAttribute('role', 'note');
  wrap.append(node('span', 'qc-stamp__badge', `⚠ ${t('qcLabel')}`));
  const reason = qc.reason ? `${t('qcNote')} ${qc.reason}` : t('qcNote');
  wrap.append(node('span', 'qc-stamp__text', reason));
  return wrap;
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
  // Accessibility: a subtle "Listen" button plays this article's narration in the one
  // shared sticky player (so only one reading plays at a time).
  if (item.audio_url) {
    const btn = node('button', 'audio-btn', '🔊 Listen');
    btn.type = 'button';
    btn.setAttribute('aria-label', `Listen to a narration of: ${item.title || 'this article'}`);
    btn.addEventListener('click', () => playArticle(item.audio_url, item.title || 'this article'));
    wrap.append(btn);
  }
  if (item.source_url) {
    const a = document.createElement('a');
    a.className = 'source-link';
    a.href = item.source_url;
    a.target = '_blank';
    a.rel = 'noopener';
    // Credit the creator by name on the link back to their own video/page.
    a.textContent = (isFun && item.source) ? `↗ watch on ${item.source}` : '↗ source';
    a.setAttribute('aria-label', (isFun && item.source)
      ? `Watch on ${item.source} (opens in a new tab)`
      : 'Read the original source (opens in a new tab)');
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

// ── Audio: per-article narration + the daily podcast (accessibility) ─────────
// One shared sticky player drives every per-article "Listen" button, so only one
// reading plays at a time. The daily dad↔son podcast gets its own player in the masthead.
function stickyPlayer() {
  let bar = el('sticky-player');
  if (!bar) {
    bar = node('div'); bar.id = 'sticky-player'; bar.className = 'sticky-player'; bar.hidden = true;
    bar.setAttribute('role', 'region');
    bar.setAttribute('aria-label', 'Article audio player');
    const label = node('span', 'np-label'); label.id = 'np-label';
    const audio = document.createElement('audio'); audio.id = 'np-audio';
    audio.controls = true; audio.preload = 'none';
    const close = node('button', 'np-close', '✕'); close.type = 'button';
    close.setAttribute('aria-label', 'Close the audio player');
    close.addEventListener('click', () => { audio.pause(); bar.hidden = true; });
    bar.append(label, audio, close);
    document.body.append(bar);
  }
  return bar;
}

function playArticle(url, title) {
  stickyPlayer();
  el('np-label').textContent = '🔊 ' + title;
  const audio = el('np-audio');
  audio.src = url;
  el('sticky-player').hidden = false;
  audio.play().catch(() => { /* autoplay blocked → the visible controls still work */ });
}

/** A subtle one-row audio strip: each show is a small play (into the shared sticky
 *  player, so only one thing plays at a time) + a download + a transcript toggle —
 *  replacing the old full-width <audio> bars that ate a row each. */
function renderPodcast(data) {
  const strip = el('podcast-strip');
  if (!strip) return;
  strip.innerHTML = '';
  const date = (data && data.date) || '';
  const shows = [
    { pod: data && data.podcast, label: t('podcast'), dl: 'craicgpt-podcast' },
    { pod: data && data.podcast_tldr, label: t('tldr'), dl: 'craicgpt-tldr' },
  ].filter(s => s.pod && s.pod.audio_url);
  if (!shows.length) { strip.hidden = true; return; }   // no audio (e.g. an older version)
  strip.hidden = false;
  strip.append(node('span', 'ps-lead', t('listen')));
  shows.forEach((s, i) => {
    if (i) strip.append(node('span', 'ps-sep', '·'));
    const item = node('span', 'ps-item');
    const play = node('button', 'ps-play', '▶ ' + s.label);
    play.type = 'button';
    play.addEventListener('click', () => playArticle(s.pod.audio_url, s.label));
    item.append(play);
    const dl = document.createElement('a');
    dl.className = 'ps-dl'; dl.href = s.pod.audio_url;
    dl.download = s.dl + (date ? '-' + date : '') + '.mp3';
    dl.title = t('download') + ' ' + s.label;
    dl.setAttribute('aria-label', t('download') + ' ' + s.label);
    dl.textContent = '⤓';
    item.append(dl);
    if (s.pod.transcript) {
      const tx = node('button', 'ps-tx', t('transcript')); tx.type = 'button';
      tx.addEventListener('click', () => toggleTranscript(s.label, s.pod.transcript));
      item.append(tx);
    }
    strip.append(item);
  });
}

/** Toggle a small transcript panel under the strip (deaf/blind readers + skimmers). */
function toggleTranscript(label, text) {
  const existing = el('podcast-transcript-panel');
  if (existing) { const same = existing.dataset.label === label; existing.remove(); if (same) return; }
  const panel = node('div', 'podcast-transcript-panel');
  panel.id = 'podcast-transcript-panel'; panel.dataset.label = label;
  panel.append(node('strong', 'ptp-title', label + ' — transcript'));
  panel.append(node('pre', 'transcript-text', text));
  el('podcast-strip').after(panel);
}

/** Stop + hide the shared sticky player (e.g. when switching edition version/date), so
 *  audio from the previous view never lingers. */
function resetStickyPlayer() {
  const bar = el('sticky-player');
  if (!bar) return;
  const a = el('np-audio'); if (a) a.pause();
  bar.hidden = true;
}

// ── Under the Hood: deep-agent visualiser ──────────────────────────────────
const TRACE_ICON = {
  plan: '🗒️', subagent: '🤝', tool: '🔧', vfs: '🗂️',
  structured: '📦', model: '🧠', fallback: '↩️', rubric: '⚖️',
  audio: '🎧', podcast: '🎙️', note: '•',
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
  rubric: 'deepagents Rubrics: a separate judge model grades the finished edition against a checklist before it can publish.',
  audio: 'Deterministic narration — each article is chunked, synthesised on the M3 voice clone, stitched and uploaded. No LLM in this leg.',
  podcast: 'The dad↔son show: verbatim readings (deterministic) wrapped in LLM-written banter — voiced as written; the edition itself passed the rubric upstream.',
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
      stat('⚖️', counts.rubric, 'rubric review'),
      stat('🎧', counts.audio, 'audio'),
      stat('🎙️', counts.podcast, 'podcast'),
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
  if (dateEl) dateEl.textContent = date.toLocaleDateString(LOCALES[LANG] || 'en-IE',
    { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
}

function initDatePicker() {
  const input = el('date-picker');
  if (!input) return;
  input.type = 'date';
  if (input.placeholder) input.placeholder = t('changeDate');
  input.max = toISODate(new Date());
  input.addEventListener('change', e => { if (e.target.value) loadEditionForDate(e.target.value); });
}

function initVersionSelect() {
  const sel = el('version-select');
  if (!sel) return;
  sel.addEventListener('change', e => {
    if (currentDate && e.target.value) loadVersion(currentDate, e.target.value);
  });
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
  document.documentElement.lang = LANG;          // crawlers + a11y: the page's real language
  const fy = el('footer-year');
  if (fy) fy.textContent = new Date().getFullYear();
  renderLangSwitcher();
  initDatePicker();
  initVersionSelect();
  initHoodDrawer();
  initNewsletter();
  // A ?date=YYYY-MM-DD (carried by the language switcher) keeps you on the same edition.
  const qDate = new URLSearchParams(location.search).get('date');
  if (qDate && /^\d{4}-\d{2}-\d{2}$/.test(qDate)) await loadEditionForDate(qDate);
  else await loadMostRecentEdition();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
