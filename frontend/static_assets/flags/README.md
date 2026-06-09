# Language-switcher flags

Tiny, hand-authored SVG national flags used by the masthead language switcher
(`main.js → renderLangSwitcher`). Each is a plain geometric rendering normalised
to a uniform **3:2** box (`viewBox="0 0 30 20"`) so the dropdown tiles line up.

Language → flag file (note **English → the Irish tricolour** — this is *Ireland's*
Most Artificially Intelligent Newspaper, and English is the source edition):

| lang | file     | flag    |
|------|----------|---------|
| en   | `ie.svg` | Ireland |
| de   | `de.svg` | Germany |
| es   | `es.svg` | Spain   |
| it   | `it.svg` | Italy   |
| ja   | `jp.svg` | Japan   |
| fr   | `fr.svg` | France  |

These are **owned, zero-copyright** — simple national-flag geometry authored here
rather than vendored, matching the project's no-third-party-assets habit (cf. the
jingle). SVG (not emoji) because emoji flags don't render on Windows. Referenced
root-absolute (`/static_assets/flags/<cc>.svg`) so they resolve under any `/<lang>/`.
