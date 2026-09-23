# Verified affiliate click tracking (STEP 7D) — status: NOT DEPLOYED

This directory is a **local-only scaffold**. Nothing here has been
deployed, and no Cloudflare configuration (dashboard settings,
`wrangler.toml`, D1 databases, DNS, CSP, build settings) has been
touched. See the STEP 7D report (sales_ai_employee conversation history)
for the full investigation this design is based on.

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
- Click events are recorded in Cloudflare D1 (once provisioned) —
  entirely separate storage from the production AI DB, so the two never
  contend with each other and a click-logging failure can never corrupt
  or block anything in `sales_ai_employee`.

## Files

- `_lib/redirect-resolver.js` — pure validation/lookup logic (no
  Cloudflare APIs). Unit-tested via `_lib/redirect-resolver.test.js`
  (plain Node, `node functions/_lib/redirect-resolver.test.js`, zero
  dependencies).
- `_data/redirect-map.example.json` — a **fixture-only** example of the
  expected shape (RFC 2606 `example.invalid` URLs). Never contains real
  data.
- `go.js` — the actual Cloudflare Pages Function (`GET /go`). Requires
  `_data/redirect-map.json` (the **real** export, not yet created — see
  below) and, optionally, a D1 binding named `CLICKS_DB`.

## What is NOT yet verified

No Node/Deno/Bun runtime was available in the environment this code was
written in, so **none of the JavaScript here has actually been
executed** — only manually reviewed. Before deploying:

1. Run `node functions/_lib/redirect-resolver.test.js` and confirm every
   case passes.
2. Run `wrangler pages dev` locally and exercise `GET /go?content_id=...
   &product_id=...&placement=cta` against a real (or example) mapping
   file.

## Steps still needed before this can go live (all require explicit Owner approval — none were taken this step)

1. Generate the real mapping: `python -m sales_ai.cli redirect-map-export
   --out redirect-map.json` against the production DB snapshot, then
   place it at `functions/_data/redirect-map.json` in this repo.
2. Provision a Cloudflare D1 database and bind it to this Pages project
   as `CLICKS_DB` (dashboard: Pages → this project → Settings →
   Functions → D1 database bindings, or a `wrangler.toml`
   `[[d1_databases]]` block — this repo has neither yet).
3. Create the `clicks` table in that D1 database (schema in `go.js`'s own
   comment: `id`, `content_id`, `product_id`, `placement`, `clicked_at`
   only — no IP/User-Agent/cookie columns).
4. Update the site's article templates (`articles/*/index.html`) to point
   the image/product-name/cta links at `/go?content_id=...&product_id=...
   &placement=...` instead of the affiliate URL directly.
5. Periodically (manually, batch — never per-click) export D1's click log
   and import confirmed conversions back into `sales_ai_employee` via the
   existing STEP 7A/7C tooling.
6. Redeploy via the normal Cloudflare Pages GitHub integration (a normal
   `git push`, still not done as part of STEP 7D).
