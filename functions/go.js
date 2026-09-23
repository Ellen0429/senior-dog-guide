// Cloudflare Pages Function: GET /go
//
// STEP 7E: production wiring complete. D1 database "senior-dog-clicks"
// exists with a `clicks` table already created (schema below matches
// exactly), and the Owner has bound it to this Pages project as
// `CLICKS_DB` via the Cloudflare dashboard (Pages Functions bindings for
// a GitHub-integrated project are a dashboard action, not something this
// session's tooling could set via API/CLI -- it deliberately never
// extracts/reuses the stored Cloudflare OAuth token for raw API calls).
// The binding takes effect from the next deployment onward. The
// `context.env && context.env.CLICKS_DB` guard below is still kept
// deliberately defensive -- if a binding is ever removed or misconfigured
// in the future, click-logging simply goes inert again rather than
// throwing; the redirect itself is entirely unaffected either way (see
// the two distinct failure-handling paths below).
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

const { resolveVerifiedClick, ClickNotAllowedError } = require("./_lib/redirect-resolver.js");
const redirectMap = require("./_data/redirect-map.json");

function generateClickId() {
  // A random, non-guessable opaque id for this one click event -- not a
  // session/visitor identifier (nothing links two different clicks to
  // the same person), just a unique row key. crypto.randomUUID() is a
  // standard Web API available in the Workers/Pages Functions runtime
  // (and in Node 19+, which is how _lib/redirect-resolver.test.js could
  // exercise the same global if it ever needed to -- it doesn't).
  return crypto.randomUUID();
}

async function onRequestGet(context) {
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
  // clicks table (already created in D1 -- see STEP 7E):
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

module.exports = { onRequestGet };
