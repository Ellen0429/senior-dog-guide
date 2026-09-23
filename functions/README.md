# Verified affiliate click tracking — status: `/go` endpoint fixed & standalone-verified, article links NOT yet switched over

D1 database `senior-dog-clicks` and its `CLICKS_DB` binding on this Pages
project were created in STEP 7E and are unchanged/reused here. STEP 7E's
first deployment of `functions/go.js` (then written in CommonJS) resulted
in a production 404 on every `/go` request — Cloudflare Pages Functions
does not support CommonJS (confirmed against
[developers.cloudflare.com/pages/functions/module-support/](https://developers.cloudflare.com/pages/functions/module-support/),
which lists exactly four supported module types: ES Modules, WebAssembly,
Text Modules, Binary Modules). That deployment was reverted immediately;
the `care-bed` article's three links have been back on the direct
Rakuten affiliate URL since then.

STEP 7F rewrote `go.js` and its dependencies in ES Modules and verified
`/go` standalone (both locally via `wrangler pages dev` and in
production) — see that step's report for the exact verification
performed. **The article's affiliate links are deliberately still the
direct Rakuten URL** — switching them to `/go?...` is a separate,
explicitly-approved future step, once `/go` has proven itself live.

## Why this design

- Downloading/updating/uploading the whole `sales_ai_employee` GCS
  SQLite snapshot on every visitor click was rejected as dangerous
  (lost-update risk under concurrent clicks) and inefficient.
- The production AI database is never queried directly by this public
  endpoint. Instead, `sales_ai_employee` exports a tiny, public-safe
  mapping — `{content_id: {product_id: affiliate_url}}` — containing
  **only** verified, published, non-`ai_hypothesis`,
  usable-`affiliate_url` pairs (see `services.redirect_export_service`
  and `python -m sales_ai.cli redirect-map-export --out <path>`). That
  file, not the production database, is what this endpoint reads.
- Click events are recorded in Cloudflare D1 — entirely separate storage
  from the production AI DB, so the two never contend with each other
  and a click-logging failure can never corrupt or block anything in
  `sales_ai_employee`.

## Files

- `_lib/redirect-resolver.mjs` — pure validation/lookup logic (no
  Cloudflare APIs). ES Modules; the `.mjs` extension lets plain Node run
  its test without any `package.json` anywhere in this repo (adding one
  at the repo root would make Cloudflare Pages auto-detect a Node build
  step for this otherwise build-less static site).
- `_lib/redirect-resolver.test.mjs` — `node functions/_lib/redirect-resolver.test.mjs`,
  zero dependencies, 14/14 passing.
- `_data/redirect-map.example.js` — a **fixture-only** example of the
  expected shape (RFC 2606 `example.invalid` URLs, ES module default
  export). Never contains real data.
- `_data/redirect-map.js` — the **real** verified mapping (ES module
  default export), generated from production `sales_ai_employee` data.
  Currently one entry: content_id 6 → product_id 10. Regenerate and
  replace this whole file (never hand-edit it) whenever a new content id
  is published or an existing one's linked product changes. A `.js`
  module, not a `.json` import, since Cloudflare's documented supported
  module types don't explicitly list JSON.
- `go.js` — the Cloudflare Pages Function (`GET /go`), ES Modules. Reads
  `content_id`/`product_id`/`placement` only, resolves against the
  mapping above, logs a click row to D1 (best-effort, never blocks the
  redirect), and 302-redirects to the verified affiliate_url.

## Updating the mapping after publishing new content

1. `python -m sales_ai.cli redirect-map-export --out redirect-map.json`
   against the production DB snapshot (read-only against GCS).
2. Convert it to `functions/_data/redirect-map.js` as an ES module
   default export (see that file's own header for the exact shape).
3. Once article links are switched to `/go` (not yet done — see above),
   update the newly-published article's affiliate links to
   `/go?content_id=<id>&product_id=<id>&placement=image|product_name|cta`.
4. Commit and push as usual.

## Batch conversion import (unchanged from STEP 7C's design)

D1's click log is exported and reconciled against Rakuten's own
affiliate report **manually, periodically, in batch** — never per-click
— and confirmed conversions are recorded in `sales_ai_employee` via the
existing `conversion-add` CLI (STEP 7C). This directory has no
automation for that; it remains a deliberate Owner action.
