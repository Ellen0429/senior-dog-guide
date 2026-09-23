# Verified affiliate click tracking (STEP 7E) — status: LIVE

D1 database `senior-dog-clicks` is created, its `clicks` table exists,
it is bound to this Pages project as `CLICKS_DB`, `functions/_data/
redirect-map.json` holds the real verified mapping, and the `care-bed`
article's three affiliate links now route through `GET /go`. See STEP
7E's report (sales_ai_employee conversation history) for the exact
verification performed (test click, D1 row check, production smoke
tests) before this was committed.

## Why this design

- Downloading/updating/uploading the whole `sales_ai_employee` GCS
  SQLite snapshot on every visitor click was rejected as dangerous
  (lost-update risk under concurrent clicks) and inefficient.
- The production AI database is never queried directly by this public
  endpoint. Instead, `sales_ai_employee` exports a tiny, public-safe
  JSON mapping — `{content_id: {product_id: affiliate_url}}` — containing
  **only** verified, published, non-`ai_hypothesis`,
  usable-`affiliate_url` pairs (see `services.redirect_export_service`
  and `python -m sales_ai.cli redirect-map-export --out <path>`). That
  file, not the production database, is what this endpoint reads.
- Click events are recorded in Cloudflare D1 — entirely separate storage
  from the production AI DB, so the two never contend with each other
  and a click-logging failure can never corrupt or block anything in
  `sales_ai_employee`.

## Files

- `_lib/redirect-resolver.js` — pure validation/lookup logic (no
  Cloudflare APIs). Unit-tested via `_lib/redirect-resolver.test.js`
  (plain Node, `node functions/_lib/redirect-resolver.test.js`, zero
  dependencies, 14/14 passing).
- `_data/redirect-map.example.json` — a **fixture-only** example of the
  expected shape (RFC 2606 `example.invalid` URLs). Never contains real
  data.
- `_data/redirect-map.json` — the **real** verified mapping, generated
  from production `sales_ai_employee` data via `redirect-map-export`.
  Currently one entry: content_id 6 → product_id 10. Regenerate and
  replace this file (never hand-edit it) whenever a new content id is
  published or an existing one's linked product changes.
- `go.js` — the Cloudflare Pages Function (`GET /go`). Reads
  `content_id`/`product_id`/`placement` only, resolves against the
  mapping above, logs a click row to D1 (best-effort, never blocks the
  redirect), and 302-redirects to the verified affiliate_url.

## Updating the mapping after publishing new content

1. `python -m sales_ai.cli redirect-map-export --out redirect-map.json`
   against the production DB snapshot (read-only against GCS).
2. Replace `functions/_data/redirect-map.json` with the new file.
3. Update the newly-published article's affiliate links to
   `/go?content_id=<id>&product_id=<id>&placement=image|product_name|cta`.
4. Commit and push as usual.

## Batch conversion import (unchanged from STEP 7C's design)

D1's click log is exported and reconciled against Rakuten's own
affiliate report **manually, periodically, in batch** — never per-click
— and confirmed conversions are recorded in `sales_ai_employee` via the
existing `conversion-add` CLI (STEP 7C). This directory has no
automation for that; it remains a deliberate Owner action.
