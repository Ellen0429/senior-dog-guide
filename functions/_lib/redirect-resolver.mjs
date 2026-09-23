// Pure, framework-agnostic verified-click resolution logic (STEP 7D,
// converted to ES Modules in STEP 7F).
//
// STEP 7F root-cause note: Cloudflare Pages Functions' own documentation
// (developers.cloudflare.com/pages/functions/module-support/) lists
// exactly four supported module types -- ES Modules, WebAssembly, Text
// Modules, and Binary Modules. CommonJS (require()/module.exports, this
// file's STEP 7D/7E form) is not among them, which is why
// functions/go.js was never registered as a route in production (STEP
// 7E's 404) -- Cloudflare's build could not parse it as a Function at
// all. This file (and go.js) now use ES Modules (import/export) only.
//
// The .mjs extension here (rather than .js) is solely so plain Node can
// run redirect-resolver.test.mjs directly, with zero package.json
// anywhere in this repo -- adding a package.json at the repo root would
// make Cloudflare Pages auto-detect a Node build step (npm clean-install
// + a build command) for this otherwise build-less static site, which
// STEP 7F deliberately avoids. Cloudflare's own Functions bundler
// resolves a relative ".mjs" import (see go.js) the same way it would a
// ".js" one -- both are ES Modules to it.
//
// Security model (mirrors sales_ai_employee's services.click_service /
// services.redirect_export_service) -- UNCHANGED from STEP 7D/7E, only
// the module syntax changed:
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
//     caller supplies it (go.js imports it from ./_data/redirect-map.js,
//     the ES-module default export sales_ai_employee's
//     services.redirect_export_service produced). That artifact contains
//     ONLY verified, published, non-ai_hypothesis, usable-affiliate_url
//     (content_id, product_id) -> affiliate_url pairs -- nothing else
//     about the production AI database is ever included there, and this
//     module has no way to reach that database even if it wanted to.
//   - No IP address, User-Agent, cookie, or any other visitor-
//     identifying value is read, returned, or referenced anywhere in
//     this module.

export const ALLOWED_PLACEMENTS = Object.freeze(["image", "product_name", "cta"]);

const ID_RE = /^[0-9]+$/;

export class ClickNotAllowedError extends Error {}

/**
 * @param {object} redirectMap - shape: {"<contentId>": {"<productId>": "<affiliateUrl>"}}
 * @param {{contentId: string, productId: string, placement: string}} params
 * @returns {string} the verified affiliate_url to redirect to
 * @throws {ClickNotAllowedError} if any check fails -- fail closed, never
 *   a best-guess fallback.
 */
export function resolveVerifiedClick(redirectMap, { contentId, productId, placement }) {
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
