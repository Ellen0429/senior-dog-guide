// Cloudflare Pages Function: GET /go
//
// STEP 7F fix: STEP 7E's deployment of this file (then written in
// CommonJS -- require()/module.exports) resulted in a production 404 on
// every /go request, indistinguishable from "route does not exist".
// Root cause, confirmed against Cloudflare's own documentation
// (developers.cloudflare.com/pages/functions/module-support/): Pages
// Functions support exactly four module types -- ES Modules,
// WebAssembly, Text Modules, Binary Modules. CommonJS is not one of
// them, so Cloudflare's build could not parse this file as a Function
// at all, and it was never registered as a route. This file (and its
// _lib/_data dependencies) now use ES Modules (import/export) only --
// the one module format Cloudflare's own docs confirm is supported, not
// a guess.
//
// D1 database "senior-dog-clicks" and its `clicks` table already exist
// (STEP 7E) and remain unchanged; the Owner-configured CLICKS_DB binding
// on this Pages project is reused as-is -- no new D1 database was
// created this step.
//
// Only three query parameters are ever read: content_id, product_id,
// placement. No other request data (headers, IP, cookies, User-Agent)
// is read, stored, or forwarded anywhere -- this handler never touches
// context.request.headers, and nothing here has a code path that could.
//
// TWO DELIBERATELY DIFFERENT FAILURE BEHAVIORS -- do not conflate them:
//   1. SECURITY VALIDATION failure (resolveVerifiedClick throws
//      ClickNotAllowedError: invalid placement, unknown/unpublished
//      content, unrelated/ai_hypothesis product, no affiliate_url) ->
//      the function returns 404 immediately. NO redirect happens. This
//      is the fail-closed path STEP 7A-7D's whole design exists for.
//   2. CLICK-LOGGING (D1 write) failure, AFTER validation already
//      succeeded -> the redirect still happens. A measurement outage
//      must never turn into a broken purchase flow for a real visitor
//      who already has a verified, safe affiliate_url waiting -- losing
//      one click-log row is far less harmful than that. This path is
//      wrapped in its own try/catch, entirely separate from validation.

import { resolveVerifiedClick, ClickNotAllowedError } from "./_lib/redirect-resolver.mjs";
import redirectMap from "./_data/redirect-map.js";

function generateClickId() {
  // A random, non-guessable opaque id for this one click event -- not a
  // session/visitor identifier (nothing links two different clicks to
  // the same person), just a unique row key. crypto.randomUUID() is a
  // standard Web Crypto API available in the Workers/Pages Functions
  // runtime.
  return crypto.randomUUID();
}

export async function onRequestGet(context) {
  const url = new URL(context.request.url);
  const contentId = url.searchParams.get("content_id");
  const productId = url.searchParams.get("product_id");
  const placement = url.searchParams.get("placement");

  // -- 1. Security validation: fail closed, no redirect on failure. --
  let affiliateUrl;
  try {
    affiliateUrl = resolveVerifiedClick(redirectMap, { contentId, productId, placement });
  } catch (err) {
    if (err instanceof ClickNotAllowedError) {
      // Never echo the rejection reason (err.message) back to the
      // client or into any log -- a plain 404 is all a visitor or a
      // log line ever sees.
      return new Response("Not found", { status: 404 });
    }
    throw err;
  }

  // -- 2. Click logging: best-effort, fail OPEN (redirect still happens). --
  //
  // clicks table (already exists in D1 -- see STEP 7E):
  //   CREATE TABLE clicks (
  //     id INTEGER PRIMARY KEY AUTOINCREMENT,
  //     click_id TEXT NOT NULL UNIQUE,
  //     content_id TEXT NOT NULL,
  //     product_id TEXT NOT NULL,
  //     placement TEXT NOT NULL CHECK (placement IN ('image','product_name','cta')),
  //     clicked_at TEXT NOT NULL DEFAULT (datetime('now'))
  //   );
  // Exactly these six columns -- no IP, no User-Agent, no cookie/session
  // identifier, nothing else. affiliate_url is NEVER written to D1.
  if (context.env && context.env.CLICKS_DB) {
    try {
      await context.env.CLICKS_DB
        .prepare(
          "INSERT INTO clicks (click_id, content_id, product_id, placement) " +
          "VALUES (?, ?, ?, ?)"
        )
        .bind(generateClickId(), contentId, productId, placement)
        .run();
    } catch (_err) {
      // Swallow deliberately: never let a click-logging failure break
      // the redirect (see the module docstring's two-failure-paths
      // note), and never log the error or affiliateUrl anywhere.
    }
  }

  return Response.redirect(affiliateUrl, 302);
}
