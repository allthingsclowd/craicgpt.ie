// infra/cloudfront/router.js
// ============================================================================
// CraicGPT.ie edge router — a CloudFront Function (viewer-request) that gives the
// static site clean per-language URLs without moving any S3 objects.
//
// Three jobs:
//   1. AUTO-DETECT: a request with NO /<lang>/ prefix (a first visit to "/") is
//      302-redirected to /<lang>/, choosing the language from the cg_lang cookie
//      (a remembered manual choice) or the Accept-Language header (fallback "en").
//   2. EN ALIAS: English content lives at the S3 ROOT (content/…, /index.html, …),
//      so /en/* is rewritten to /*  — the source language needs no duplicate tree.
//   3. SUBFOLDER INDEX: with an OAC→S3 REST origin the distribution default-root-
//      object only covers "/", so /<lang>/ (and any dir/) is rewritten to
//      …/index.html for the real translation trees (/de/, /fr/, …).
//
// Attach ONLY to the default cache behavior (page navigations). Give /static_assets/*,
// */content/* and /favicon.ico their own behaviors WITHOUT this function so it never
// runs on asset/JSON/audio fetches (keeps invocations — and cost — to page loads).
// No loop: after a "/" → "/en/" redirect, the next request already has a known prefix
// and only ever gets rewritten, never redirected again.
// ============================================================================

var KNOWN = ['en', 'de', 'es', 'it', 'ja', 'fr'];
var DEFAULT_LANG = 'en';

function pickLanguage(acceptLanguage) {
  // "de-DE,de;q=0.9,en;q=0.8" → the first base code we actually publish, else default.
  var parts = acceptLanguage.split(',');
  for (var i = 0; i < parts.length; i++) {
    var code = parts[i].split(';')[0].trim().toLowerCase().split('-')[0];
    if (KNOWN.indexOf(code) !== -1) return code;
  }
  return DEFAULT_LANG;
}

function withIndex(uri) {
  // A bare directory ("" or ".../") → its index.html; otherwise leave it.
  if (uri === '') return '/index.html';
  if (uri.charAt(uri.length - 1) === '/') return uri + 'index.html';
  return uri;
}

function handler(event) {
  var request = event.request;
  var uri = request.uri;
  var seg = uri.split('/')[1]; // '' for '/', else the first path segment

  // Never redirect non-page paths (root-absolute assets, content/preview JSON+media,
  // favicon/robots/sitemap) — pass them straight through. This keeps the function safe
  // even if it's attached to a broad behavior; dedicated asset behaviors are then just a
  // cost optimisation (fewer invocations), not a correctness requirement.
  if (seg === 'static_assets' || seg === 'content' || seg === 'preview' ||
      uri === '/favicon.ico' || uri === '/robots.txt' || uri === '/sitemap.xml') {
    return request;
  }

  if (KNOWN.indexOf(seg) !== -1) {
    if (seg === DEFAULT_LANG) {
      // EN alias: strip "/en" so the English tree is served from the S3 root.
      request.uri = withIndex(uri.substring(('/' + DEFAULT_LANG).length));
    } else {
      // A real translation tree: only a bare dir needs the index.html rewrite.
      request.uri = withIndex(uri);
    }
    return request;
  }

  // No language prefix → first-visit detection + 302 to the chosen language.
  var lang = DEFAULT_LANG;
  if (request.cookies && request.cookies.cg_lang &&
      KNOWN.indexOf(request.cookies.cg_lang.value) !== -1) {
    lang = request.cookies.cg_lang.value;
  } else if (request.headers['accept-language']) {
    lang = pickLanguage(request.headers['accept-language'].value);
  }

  var target = '/' + lang + (uri === '/' ? '/' : uri);
  return {
    statusCode: 302,
    statusDescription: 'Found',
    headers: {
      'location': { value: target },
      // Remember the choice so we don't re-evaluate on every subsequent visit.
      'set-cookie': { value: 'cg_lang=' + lang + '; Path=/; Max-Age=31536000; SameSite=Lax' },
      'cache-control': { value: 'no-cache' }
    }
  };
}
