// Pure, framework-agnostic verified-click resolution logic (STEP 7D).
//
// This module has NO Cloudflare-specific dependencies (no `env`, no D1
// bindings, no Workers-only globals) so it can be unit-tested with plain
// Node, independently of any live Cloudflare deployment. See
// redirect-resolver.test.js (plain Node, zero dependencies) and that
// file's own header comment for the important caveat: these tests were
// NOT executed in the environment this code was written in (no Node/
// Deno/Bun runtime was available there) -- run `node redirect-resolver.test.js`
// yourself before relying on this in production.
//
// functions/go.js is the thin Cloudflare Pages Function adapter that
// wires this to an actual HTTP request and a D1 click-log write -- see
// that file's own comments for what is, and is not, verified to work
// against real Cloudflare infrastructure yet.
//
// Security model (mirrors sales_ai_employee's services.click_service /
// services.redirect_export_service):
//   - resolveVerifiedClick()'s only inputs are contentId, productId, and
//     placement -- never a URL. There is no parameter here that accepts
//     an arbitrary redirect target from a query string or any other
//     caller-controlled source. Open redirect is structurally
//     impossible, not just filtered.
//   - placement must be exactly one of ALLOWED_PLACEMENTS.
//   - contentId/productId must each match /^[0-9]+$/ before they are
//     ever used to index into `redirectMap` -- this rejects, up front,
//     any attempt to use a non-numeric-id string (e.g. "__proto__" or
//     "constructor") as a lookup key, and every lookup additionally uses
//     Object.prototype.hasOwnProperty.call(...) rather than `in` or a
//     bare property read, so prototype-chain properties can never be
//     mistaken for a real mapping entry.
//   - the (contentId, productId) pair must exist in `redirectMap`, a
//     mapping this module never mutates and never fetches itself -- the
//     caller supplies it, already loaded from the small JSON artifact
//     sales_ai_employee's services.redirect_export_service produced.
//     That artifact contains ONLY verified, published, non-ai_hypothesis,
//     usable-affiliate_url (content_id, product_id) -> affiliate_url
//     pairs -- nothing else about the production AI database is ever
//     included there, and this module has no way to reach that database
//     even if it wanted to.
//   - No IP address, User-Agent, cookie, or any other visitor-
//     identifying value is read, returned, or referenced anywhere in
//     this module.

const ALLOWED_PLACEMENTS = Object.freeze(["image", "product_name", "cta"]);

const ID_RE = /^[0-9]+$/;

class ClickNotAllowedError extends Error {}

/**
 * @param {object} redirectMap - parsed JSON, shape:
 *   {"<contentId>": {"<productId>": "<affiliateUrl>"}}
 * @param {{contentId: string, productId: string, placement: string}} params
 * @returns {string} the verified affiliate_url to redirect to
 * @throws {ClickNotAllowedError} if any check fails -- fail closed, never
 *   a best-guess fallback.
 */
function resolveVerifiedClick(redirectMap, { contentId, productId, placement }) {
  if (!ALLOWED_PLACEMENTS.includes(placement)) {
    throw new ClickNotAllowedError(`invalid placement: ${JSON.stringify(placement)}`);
  }
  if (typeof contentId !== "string" || !ID_RE.test(contentId)) {
    throw new ClickNotAllowedError("invalid content id");
  }
  if (typeof productId !== "string" || !ID_RE.test(productId)) {
    throw new ClickNotAllowedError("invalid product id");
  }
  if (redirectMap === null || typeof redirectMap !== "object") {
    throw new ClickNotAllowedError("redirect map is not an object");
  }
  if (!Object.prototype.hasOwnProperty.call(redirectMap, contentId)) {
    throw new ClickNotAllowedError(`content ${contentId} has no verified redirect mapping`);
  }
  const contentEntry = redirectMap[contentId];
  if (
    contentEntry === null || typeof contentEntry !== "object" ||
    !Object.prototype.hasOwnProperty.call(contentEntry, productId)
  ) {
    throw new ClickNotAllowedError(
      `product ${productId} is not a verified redirect target for content ${contentId}`
    );
  }
  const affiliateUrl = contentEntry[productId];
  if (typeof affiliateUrl !== "string" || affiliateUrl.length === 0) {
    throw new ClickNotAllowedError(
      `content ${contentId}/product ${productId} has no usable affiliate URL`
    );
  }
  return affiliateUrl;
}

module.exports = { ALLOWED_PLACEMENTS, ClickNotAllowedError, resolveVerifiedClick };
