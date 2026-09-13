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
        tagline: 'An Irish daily, minus the doom',
        mastheadPrice: 'FREE (as in speech, not beer)',
        mastheadSubtitle: "All the craic that's fit to hallucinate",
        editionDraft: 'v3 · draft', approved: '✓ approved', draftLabel: '⏳ draft',
        aboutTitle: 'About the Editor', aboutSubtitle: "Who's behind all this craic, anyway?",
        placeholderDateline: 'No recent edition',
        navToday: 'Today', navAi: 'AI Desk', navCraic: 'Craic', navLang: 'Languages', navListen: 'Listen',
        navOlder: '◀ Older', navNewer: 'Newer ▶',
        navOlderAria: 'Go to the previous (older) edition', navNewerAria: 'Go to the next (newer) edition',
        translatedNote: 'This edition was machine-translated from English by {model} — blame the robot, not the editor.',
        readOriginal: 'Read the English original ↗',
        qcLabel: 'Quality control', qcNote: 'Flagged by our automated fact-check — read with a pinch of salt:',
        newsletterThanks: "Thanks! Sign-ups open in a future edition — you're on the list in spirit.",
        placeholderKicker: 'ER, ABOUT TODAY…',
        placeholderHeadline: 'AI EDITOR TAKES THE DAY OFF; EXISTENTIAL CRISIS ENSUES',
        placeholderBody: "No edition was found for the last fortnight. The deep agent may not have run yet, or it's still waiting on a human to approve today's draft." },
  de: { listen: '🎧 Hören', podcast: 'Täglicher Podcast', tldr: '90-Sek-Schlagzeilen',
        transcript: 'Transkript', download: 'Herunterladen:', latest: 'aktuell',
        fetching: 'Heutige Ausgabe wird geladen…', noEdition: 'Keine Ausgabe gefunden für',
        dayOff: 'Die Craic Gazette macht wohl gerade Urlaub.', changeDate: '📅 Datum ändern',
        tagline: 'Eine irische Tageszeitung, ohne den Weltuntergang',
        mastheadPrice: 'GRATIS (wie Freiheit, nicht wie Freibier)',
        mastheadSubtitle: 'Der ganze Craic, der zu halluzinieren lohnt',
        editionDraft: 'v3 · Entwurf', approved: '✓ freigegeben', draftLabel: '⏳ Entwurf',
        aboutTitle: 'Über den Redakteur', aboutSubtitle: 'Wer steckt hinter all dem Craic?',
        placeholderDateline: 'Keine aktuelle Ausgabe',
        navToday: 'Heute', navAi: 'KI-Desk', navCraic: 'Craic', navLang: 'Sprachen', navListen: 'Hören',
        navOlder: '◀ Älter', navNewer: 'Neuer ▶',
        navOlderAria: 'Zur vorherigen (älteren) Ausgabe', navNewerAria: 'Zur nächsten (neueren) Ausgabe',
        translatedNote: 'Diese Ausgabe wurde von {model} maschinell aus dem Englischen übersetzt — schimpft mit dem Roboter, nicht mit der Redaktion.',
        readOriginal: 'Zum englischen Original ↗',
        qcLabel: 'Qualitätskontrolle', qcNote: 'Von unserer automatischen Faktenprüfung markiert — mit Vorsicht zu genießen:',
        newsletterThanks: 'Danke! Anmeldungen öffnen in einer künftigen Ausgabe — im Geiste stehst du schon auf der Liste.',
        placeholderKicker: 'ÄH, WEGEN HEUTE…',
        placeholderHeadline: 'KI-REDAKTEUR MACHT BLAU; EXISTENZKRISE FOLGT',
        placeholderBody: 'Für die letzten zwei Wochen wurde keine Ausgabe gefunden. Vielleicht ist der Deep-Agent noch nicht gelaufen, oder er wartet noch darauf, dass ein Mensch den heutigen Entwurf freigibt.' },
  es: { listen: '🎧 Escuchar', podcast: 'Podcast diario', tldr: 'Titulares en 90 s',
        transcript: 'transcripción', download: 'Descargar', latest: 'última',
        fetching: 'Cargando la edición de hoy…', noEdition: 'No se encontró edición para',
        dayOff: 'La Craic Gazette estaría de vacaciones.', changeDate: '📅 cambiar fecha',
        tagline: 'Un diario irlandés, sin el fatalismo',
        mastheadPrice: 'GRATIS (como en libertad, no como en cerveza)',
        mastheadSubtitle: 'Todo el craic digno de alucinar',
        editionDraft: 'v3 · borrador', approved: '✓ aprobado', draftLabel: '⏳ borrador',
        aboutTitle: 'Sobre el editor', aboutSubtitle: '¿Quién está detrás de todo este craic?',
        placeholderDateline: 'Sin edición reciente',
        navToday: 'Hoy', navAi: 'Mesa IA', navCraic: 'Craic', navLang: 'Idiomas', navListen: 'Escuchar',
        navOlder: '◀ Anterior', navNewer: 'Siguiente ▶',
        navOlderAria: 'Ir a la edición anterior (más antigua)', navNewerAria: 'Ir a la edición siguiente (más reciente)',
        translatedNote: 'Esta edición fue traducida automáticamente del inglés por {model} — la culpa es del robot, no de la redacción.',
        readOriginal: 'Leer el original en inglés ↗',
        qcLabel: 'Control de calidad', qcNote: 'Marcado por nuestra verificación automática — tómalo con cautela:',
        newsletterThanks: '¡Gracias! Las suscripciones se abrirán en una edición futura — ya estás en la lista, en espíritu.',
        placeholderKicker: 'EH, SOBRE LO DE HOY…',
        placeholderHeadline: 'EL EDITOR DE IA SE TOMA EL DÍA LIBRE; SOBREVIENE UNA CRISIS EXISTENCIAL',
        placeholderBody: 'No se encontró ninguna edición en las últimas dos semanas. Puede que el agente profundo aún no se haya ejecutado, o que siga esperando a que un humano apruebe el borrador de hoy.' },
  it: { listen: '🎧 Ascolta', podcast: 'Podcast quotidiano', tldr: 'Titoli in 90 s',
        transcript: 'trascrizione', download: 'Scarica', latest: 'ultima',
        fetching: "Caricamento dell'edizione di oggi…", noEdition: 'Nessuna edizione trovata per',
        dayOff: 'La Craic Gazette sarà in vacanza.', changeDate: '📅 cambia data',
        tagline: 'Un quotidiano irlandese, senza catastrofismo',
        mastheadPrice: 'GRATIS (come libertà, non come birra)',
        mastheadSubtitle: 'Tutto il craic che vale la pena allucinare',
        editionDraft: 'v3 · bozza', approved: '✓ approvato', draftLabel: '⏳ bozza',
        aboutTitle: 'Informazioni sul redattore', aboutSubtitle: 'Chi c’è dietro tutto questo craic?',
        placeholderDateline: 'Nessuna edizione recente',
        navToday: 'Oggi', navAi: 'Desk IA', navCraic: 'Craic', navLang: 'Lingue', navListen: 'Ascolta',
        navOlder: '◀ Precedente', navNewer: 'Successiva ▶',
        navOlderAria: "Vai all'edizione precedente (più vecchia)", navNewerAria: "Vai all'edizione successiva (più recente)",
        translatedNote: "Questa edizione è stata tradotta automaticamente dall'inglese da {model} — prendetevela col robot, non con la redazione.",
        readOriginal: "Leggi l'originale in inglese ↗",
        qcLabel: 'Controllo qualità', qcNote: 'Segnalato dal nostro fact-check automatico — da prendere con le pinze:',
        newsletterThanks: "Grazie! Le iscrizioni apriranno in un'edizione futura — sei già in lista, almeno con lo spirito.",
        placeholderKicker: 'EHM, RIGUARDO A OGGI…',
        placeholderHeadline: "L'EDITORE IA SI PRENDE UN GIORNO LIBERO; NE SEGUE UNA CRISI ESISTENZIALE",
        placeholderBody: "Nessuna edizione trovata nelle ultime due settimane. Forse il deep agent non è ancora stato eseguito, oppure sta ancora aspettando che un umano approvi la bozza di oggi." },
  ja: { listen: '🎧 聴く', podcast: 'デイリーポッドキャスト', tldr: '90秒ヘッドライン',
        transcript: '文字起こし', download: 'ダウンロード', latest: '最新',
        fetching: '本日のエディションを読み込み中…', noEdition: 'エディションが見つかりません：',
        dayOff: 'クレイク・ガゼットはお休みのようです。', changeDate: '📅 日付を変更',
        tagline: 'アイルランドの日刊紙、暗い話題は抜きで',
        mastheadPrice: '無料（自由の意味で、ビールではなく）',
        mastheadSubtitle: '幻覚するに値するすべてのクレイク',
        editionDraft: 'v3 · 下書き', approved: '✓ 承認済み', draftLabel: '⏳ 下書き',
        aboutTitle: '編集長について', aboutSubtitle: 'このクレイクの裏にいるのは誰？',
        placeholderDateline: '最近のエディションなし',
        navToday: '本日', navAi: 'AIデスク', navCraic: 'クレイク', navLang: '言語', navListen: '聴く',
        navOlder: '◀ 前の号', navNewer: '次の号 ▶',
        navOlderAria: '前の（古い）号へ', navNewerAria: '次の（新しい）号へ',
        translatedNote: 'この号は{model}により英語から機械翻訳されています。おかしな点はロボットのせいということで。',
        readOriginal: '英語の原文を読む ↗',
        qcLabel: '品質チェック', qcNote: '自動ファクトチェックがフラグを立てました。話半分でどうぞ：',
        newsletterThanks: 'ありがとう！登録は今後の号で開始します——気持ちのうえではもうリスト入りです。',
        placeholderKicker: 'えっと、本日の件ですが…',
        placeholderHeadline: 'AI編集長、本日休業。実存的危機へ突入',
        placeholderBody: '過去2週間分のエディションが見つかりませんでした。ディープエージェントがまだ実行されていないか、本日の草稿が人間の承認を待っている可能性があります。' },
  fr: { listen: '🎧 Écouter', podcast: 'Podcast quotidien', tldr: 'Titres en 90 s',
        transcript: 'transcription', download: 'Télécharger', latest: 'récente',
        fetching: "Chargement de l'édition du jour…", noEdition: 'Aucune édition trouvée pour',
        dayOff: 'La Craic Gazette est sans doute en vacances.', changeDate: '📅 changer de date',
        tagline: 'Un quotidien irlandais, sans la sinistrose',
        mastheadPrice: 'GRATUIT (comme la liberté, pas comme la bière)',
        mastheadSubtitle: 'Tout le craic digne d’être halluciné',
        editionDraft: 'v3 · brouillon', approved: '✓ approuvé', draftLabel: '⏳ brouillon',
        aboutTitle: 'À propos du rédacteur', aboutSubtitle: 'Qui se cache derrière tout ce craic ?',
        placeholderDateline: 'Aucune édition récente',
        navToday: "Aujourd'hui", navAi: 'Bureau IA', navCraic: 'Craic', navLang: 'Langues', navListen: 'Écouter',
        navOlder: '◀ Précédente', navNewer: 'Suivante ▶',
        navOlderAria: "Aller à l'édition précédente (plus ancienne)", navNewerAria: "Aller à l'édition suivante (plus récente)",
        translatedNote: "Cette édition a été traduite automatiquement de l'anglais par {model} — blâmez le robot, pas la rédaction.",
        readOriginal: "Lire l'original en anglais ↗",
        qcLabel: 'Contrôle qualité', qcNote: 'Signalé par notre vérification automatique — à prendre avec des pincettes :',
        newsletterThanks: "Merci ! Les inscriptions ouvriront dans une prochaine édition — vous êtes déjà sur la liste, en esprit.",
        placeholderKicker: "EUH, À PROPOS D'AUJOURD'HUI…",
        placeholderHeadline: "LE RÉDACTEUR IA PREND SA JOURNÉE ; CRISE EXISTENTIELLE À LA CLÉ",
        placeholderBody: "Aucune édition trouvée pour les deux dernières semaines. L'agent profond n'a peut-être pas encore tourné, ou il attend encore qu'un humain approuve le brouillon du jour." },
};
const t = (key) => ((I18N[LANG] || I18N.en)[key] ?? I18N.en[key] ?? key);

const EDITION_PREFIX =
  new URLSearchParams(location.search).get('edition') === 'preview' ? 'preview' : 'content';
const CONTENT_PATH = (y, m, d) => `/${LANG}/${EDITION_PREFIX}/${y}/${m}/${d}/paper_content.json`;
// Edition versioning: the manifest of the day's versions, and a specific snapshot.
const VERSIONS_PATH = (y, m, d) => `/${LANG}/${EDITION_PREFIX}/${y}/${m}/${d}/versions.json`;
const VERSION_PATH = (y, m, d, id) => `/${LANG}/${EDITION_PREFIX}/${y}/${m}/${d}/versions/${id}.json`;
const MAX_FALLBACK_DAYS = 14;
// How far prev/next paging will step over "day off" gaps before giving up (#134).
const MAX_ADJACENT_PROBE_DAYS = 30;

let currentPaperData = null;
let currentDate = null;        // the edition date currently shown (drives the version picker)
// The nearest older/newer editions found by the last probe, cached so a click jumps
// straight there without re-probing; recomputed by refreshEditionNav after every load.
let navTargets = { older: null, newer: null };
let navBusy = false;           // guards against overlapping prev/next clicks
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
      await refreshEditionNav();
      return;
    }
  }
  renderPlaceholder();
  await refreshEditionNav();   // no edition shown → both directions disabled
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
    await refreshEditionNav();
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

// ── Prev/next edition paging (#134) ──────────────────────────────────────────
// There is NO manifest of which days have an edition — days are PROBED. To page
// back/forward we step one day at a time from the shown date, fetching each candidate,
// and stop at the FIRST that loads (so a "day off" gap is simply skipped). Forward
// paging never probes past today (there can be no future edition). Nothing older/newer
// within the window → that direction's button is disabled, not fruitlessly clickable.

/** Step ±1 day from `fromDate` up to MAX_ADJACENT_PROBE_DAYS times, returning the first
 *  edition found as {data, date}, or null. dir = -1 (older) / +1 (newer). */
async function probeAdjacentEdition(fromDate, dir) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const probe = new Date(fromDate); probe.setHours(0, 0, 0, 0);
  for (let i = 0; i < MAX_ADJACENT_PROBE_DAYS; i++) {
    probe.setDate(probe.getDate() + dir);
    if (dir > 0 && probe > today) return null;   // never page into the future
    const data = await fetchPaperContent(probe);
    if (data) return { data, date: new Date(probe) };
  }
  return null;
}

/** Load the nearest edition in `dir` (-1 older / +1 newer). Uses the cached target from
 *  the last refreshEditionNav when present (so the click doesn't re-probe), else probes
 *  live. On success: swap the shown edition, re-render, update the dateline + version
 *  picker, then recompute the button states. If none is found, the current edition stays
 *  put and that direction is disabled. */
async function loadAdjacentEdition(dir) {
  if (!currentDate || navBusy) return;
  navBusy = true;
  setEditionNavDisabled(true, true);                       // freeze both while we work
  const found = (dir < 0 ? navTargets.older : navTargets.newer)
    || await probeAdjacentEdition(currentDate, dir);
  if (found) {
    currentPaperData = found.data;
    currentDate = found.date;
    renderPaper(found.data);
    renderAbout(found.data);
    updateDateDisplay(found.date);
    await renderVersions(found.date);
  }
  navBusy = false;
  await refreshEditionNav();                               // recompute enabled/disabled
}

/** Toggle both paging buttons' disabled state (native `disabled` also drops them from the
 *  tab order + triggers the :disabled styling). */
function setEditionNavDisabled(olderDisabled, newerDisabled) {
  const older = el('nav-older'); if (older) older.disabled = olderDisabled;
  const newer = el('nav-newer'); if (newer) newer.disabled = newerDisabled;
}

/** Probe both directions from the shown date, cache the results, and enable/disable each
 *  button accordingly (disabled when there's nothing that way within the window). Runs
 *  after every edition load; a no-op on a page without the buttons (e.g. About). */
async function refreshEditionNav() {
  if (!el('nav-older') && !el('nav-newer')) return;
  if (!currentDate) { navTargets = { older: null, newer: null }; setEditionNavDisabled(true, true); return; }
  navTargets.older = await probeAdjacentEdition(currentDate, -1);
  navTargets.newer = await probeAdjacentEdition(currentDate, +1);
  setEditionNavDisabled(!navTargets.older, !navTargets.newer);
}

/** Wire the paging buttons' clicks + their localised aria-labels (the visible text is set
 *  from data-i18n by applyNavLabels; the aria-label is an attribute, so set here). */
function initEditionNav() {
  const older = el('nav-older');
  const newer = el('nav-newer');
  if (older) {
    older.setAttribute('aria-label', t('navOlderAria'));
    older.addEventListener('click', () => loadAdjacentEdition(-1));
  }
  if (newer) {
    newer.setAttribute('aria-label', t('navNewerAria'));
    newer.addEventListener('click', () => loadAdjacentEdition(+1));
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
  // Anchor targets for the shell nav's "AI Desk" / "Craic" links.
  aiRegion.id = 'ai-desk';
  funRegion.id = 'craic-desk';
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
  updateNavVisibility();   // reveal AI/Craic/Listen anchors now their targets exist (#132)
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
    const approved = data.edition?.approved_by ? t('approved') : t('draftLabel');
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
    `<article class="card card--lead card--placeholder" style="grid-column:1/-1"><div class="kicker kicker--red">${escapeHtml(t('placeholderKicker'))}</div>
     <h2 class="headline headline--lead">${escapeHtml(t('placeholderHeadline'))}</h2>
     <div class="body"><p>${escapeHtml(t('placeholderBody'))}</p></div></article>`;
  // The dateline is seeded with "Loading edition…" and only replaced by updateDateDisplay()
  // when an edition loads — on the placeholder it would stay stuck (and English). (#130)
  const dateEl = el('current-date');
  if (dateEl) dateEl.textContent = t('placeholderDateline');
  updateNavVisibility();   // no AI/Craic desks or podcast strip to scroll to (#132)
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
  input.type = 'date';   // native date inputs ignore placeholder — the visible
                         // .dateline-change-label (data-i18n) is the affordance now (#132)
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
    if (msg) msg.textContent = t('newsletterThanks');
    form.reset();
  });
}

/** Localise every static [data-i18n] chrome element from the i18n table — the shell-nav
 *  labels plus the masthead strip (price/subtitle/tagline/edition), the change-date label
 *  and the About title band (the English root keeps English; the generated per-language
 *  shells are also localised statically by i18n_html.py). #edition-attribution gets a
 *  localised pre-load value here; renderAttribution() overwrites it once an edition loads. */
function applyNavLabels() {
  document.querySelectorAll('[data-i18n]').forEach(elm => {
    const key = elm.getAttribute('data-i18n');
    if (key) elm.textContent = t(key);
  });
}

/** Hide the in-page section-nav anchors whose target isn't rendered (a placeholder has no
 *  AI/Craic desks; an audio-less edition keeps #podcast-strip hidden), so "Listen"/section
 *  links never scroll nowhere (#132). #top and #lang-switcher are always present. */
function updateNavVisibility() {
  document.querySelectorAll('.shell-nav a[href^="#"]').forEach(a => {
    const target = document.getElementById(a.getAttribute('href').slice(1));
    a.hidden = !(target && !target.hidden);
  });
}

/** Dark-mode toggle. The before-paint <head> script already restored a saved theme
 *  (data-theme = "dark"|"light", or unset = follow the OS). A click flips to the
 *  opposite of what's shown NOW and persists it; storage is wrapped in try/catch. */
function initThemeToggle() {
  const btn = el('theme-toggle');
  if (!btn) return;
  btn.addEventListener('click', () => {
    const cur = document.documentElement.dataset.theme;   // '', 'dark' or 'light'
    let next;
    if (cur === 'dark') next = 'light';
    else if (cur === 'light') next = 'dark';
    else {   // unset → currently following the OS; flip away from it
      const sysDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      next = sysDark ? 'light' : 'dark';
    }
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('craic_theme', next); } catch (e) {}
  });
}

/** The "Languages" shell-nav item opens the existing masthead language switcher
 *  (rendered by renderLangSwitcher into .masthead-top-strip). The href scrolls the
 *  switcher into view; this then pops its menu open. */
function initNavLanguages() {
  const link = el('nav-languages');
  if (!link) return;
  link.addEventListener('click', () => {
    setTimeout(() => {
      const trigger = document.querySelector('#lang-switcher .lang-trigger');
      if (trigger && trigger.getAttribute('aria-expanded') !== 'true') trigger.click();
    }, 60);
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
  applyNavLabels();
  initThemeToggle();
  initNavLanguages();
  renderLangSwitcher();
  initDatePicker();
  initVersionSelect();
  initEditionNav();
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
