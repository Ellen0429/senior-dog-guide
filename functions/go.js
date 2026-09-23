// Cloudflare Pages Function: GET /go
//
// STEP 7D scaffold -- NOT YET DEPLOYED. Cloudflare configuration itself
// was deliberately left untouched this step (no wrangler.toml, no
// dashboard changes, no D1 database was provisioned): see the STEP 7D
// report for the exact remaining steps and why they need a separate,
// explicit Owner-approved action. Concretely, before this can go live:
//   1. `functions/_data/redirect-map.json` (the REAL verified mapping)
//      must exist -- it does not yet. Generate it from production data
//      with `python -m sales_ai.cli redirect-map-export --out
//      redirect-map.json` (sales_ai_employee, STEP 7D) and place it
//      here. Until then, this file's `require(...)` below points at a
//      path that doesn't exist, and Cloudflare's build would fail on
//      that alone -- a deliberate fail-closed default, not an oversight.
//   2. A real Cloudflare D1 database must be created and bound to this
//      Pages project as `CLICKS_DB` (via the dashboard's Pages ->
//      Settings -> Functions -> D1 database bindings, or a wrangler.toml
//      `[[d1_databases]]` block -- neither exists yet in this repo).
//   3. The D1 database needs a `clicks` table -- see the schema comment
//      near the INSERT below.
//   4. This file's actual behavior against Cloudflare's real Pages
//      Functions runtime has NOT been exercised (no live Cloudflare/
//      Workers environment was available while writing it) -- only the
//      pure logic in _lib/redirect-resolver.js was written to be
//      Node-testable (see that file's own test, also not yet run in
//      this environment -- no Node/Deno/Bun runtime was available
//      either). Run `wrangler pages dev` locally and exercise this
//      route for real before relying on it in production.
//
// Only three query parameters are ever read: content_id, product_id,
// placement. No other request data (headers, IP, cookies, User-Agent)
// is read, stored, or forwarded anywhere -- this handler never touches
// context.request.headers, and nothing here has a code path that could.

const { resolveVerifiedClick, ClickNotAllowedError } = require("./_lib/redirect-resolver.js");
const redirectMap = require("./_data/redirect-map.json");

async function onRequestGet(context) {
  const url = new URL(context.request.url);
  const contentId = url.searchParams.get("content_id");
  const productId = url.searchParams.get("product_id");
  const placement = url.searchParams.get("placement");

  let affiliateUrl;
  try {
    affiliateUrl = resolveVerifiedClick(redirectMap, { contentId, productId, placement });
  } catch (err) {
    if (err instanceof ClickNotAllowedError) {
      // Fail closed: unknown/unpublished/unrelated/ai_hypothesis/no-
      // affiliate-url/invalid-placement all land here. Never echo the
      // rejection reason (err.message) back to the client or into any
      // log -- a plain 404 is all a visitor or a log line ever sees.
      return new Response("Not found", { status: 404 });
    }
    throw err;
  }

  // Best-effort click logging to D1 -- a write failure here must never
  // block or slow the redirect itself (the affiliate link is already
  // verified safe to send the visitor to; losing one click log row is
  // far less harmful than a broken/slow purchase flow).
  //
  // Expected D1 schema (create once, manually, when the real D1
  // database is provisioned -- STEP 7D deliberately does not run this
  // migration against anything, since no real D1 database exists yet):
  //
  //   CREATE TABLE clicks (
  //     id INTEGER PRIMARY KEY AUTOINCREMENT,
  //     content_id TEXT NOT NULL,
  //     product_id TEXT NOT NULL,
  //     placement TEXT NOT NULL,
  //     clicked_at TEXT NOT NULL DEFAULT (datetime('now'))
  //   );
  //
  // Exactly the five columns STEP 7D's requirements list -- no IP, no
  // User-Agent, no cookie/session identifier, nothing else.
  if (context.env && context.env.CLICKS_DB) {
    try {
      await context.env.CLICKS_DB
        .prepare(
          "INSERT INTO clicks (content_id, product_id, placement) VALUES (?, ?, ?)"
        )
        .bind(contentId, productId, placement)
        .run();
    } catch (_err) {
      // Swallow deliberately: never let a click-logging failure break
      // the redirect, and never log the error (it could in principle
      // embed request data) -- same caution as never logging
      // affiliateUrl anywhere in this file.
    }
  }

  return Response.redirect(affiliateUrl, 302);
}

module.exports = { onRequestGet };
