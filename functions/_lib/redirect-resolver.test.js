// Plain Node test for redirect-resolver.js -- zero dependencies (uses
// only Node's built-in `assert`), so it can run with just `node
// redirect-resolver.test.js`, no npm install, no test framework.
//
// IMPORTANT: this file was written but NOT executed in the environment
// it was authored in (no Node/Deno/Bun runtime was available there --
// see STEP 7D's report). Run it yourself (`node functions/_lib/redirect-
// resolver.test.js`) and confirm it prints "ALL TESTS PASSED" before
// relying on redirect-resolver.js in production.
//
// Every affiliate_url used here is a fixture (https://example.invalid/...
// -- RFC 2606 reserved), never a real value.

const assert = require("assert");
const {
  ALLOWED_PLACEMENTS,
  ClickNotAllowedError,
  resolveVerifiedClick,
} = require("./redirect-resolver.js");

const FIXTURE_URL = "https://example.invalid/fixture-affiliate-link";

const MAP = Object.freeze({
  "6": Object.freeze({ "10": FIXTURE_URL }),
});

function assertThrowsClickNotAllowed(fn, messageContains) {
  assert.throws(fn, (err) => {
    assert.ok(err instanceof ClickNotAllowedError, `expected ClickNotAllowedError, got ${err}`);
    if (messageContains) {
      assert.ok(
        err.message.includes(messageContains),
        `expected error message to include ${JSON.stringify(messageContains)}, got ${JSON.stringify(err.message)}`
      );
    }
    return true;
  });
}

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`ok - ${name}`);
}

test("valid click on cta resolves the verified affiliate url", () => {
  const url = resolveVerifiedClick(MAP, { contentId: "6", productId: "10", placement: "cta" });
  assert.strictEqual(url, FIXTURE_URL);
});

test("valid click on image resolves the same verified affiliate url", () => {
  const url = resolveVerifiedClick(MAP, { contentId: "6", productId: "10", placement: "image" });
  assert.strictEqual(url, FIXTURE_URL);
});

test("valid click on product_name resolves the same verified affiliate url", () => {
  const url = resolveVerifiedClick(
    MAP, { contentId: "6", productId: "10", placement: "product_name" }
  );
  assert.strictEqual(url, FIXTURE_URL);
});

test("ALLOWED_PLACEMENTS matches the three article elements exactly", () => {
  assert.deepStrictEqual([...ALLOWED_PLACEMENTS].sort(), ["cta", "image", "product_name"]);
});

test("invalid placement is rejected", () => {
  assertThrowsClickNotAllowed(
    () => resolveVerifiedClick(MAP, { contentId: "6", productId: "10", placement: "banner" }),
    "invalid placement",
  );
});

test("empty placement is rejected", () => {
  assertThrowsClickNotAllowed(
    () => resolveVerifiedClick(MAP, { contentId: "6", productId: "10", placement: "" }),
  );
});

test("unknown content id is rejected", () => {
  assertThrowsClickNotAllowed(
    () => resolveVerifiedClick(MAP, { contentId: "999", productId: "10", placement: "cta" }),
    "no verified redirect mapping",
  );
});

test("unknown product id under a known content is rejected", () => {
  assertThrowsClickNotAllowed(
    () => resolveVerifiedClick(MAP, { contentId: "6", productId: "999", placement: "cta" }),
    "not a verified redirect target",
  );
});

test("unrelated product id (exists elsewhere, not under this content) is rejected", () => {
  const map = { "6": { "10": FIXTURE_URL }, "7": { "11": FIXTURE_URL } };
  assertThrowsClickNotAllowed(
    () => resolveVerifiedClick(map, { contentId: "6", productId: "11", placement: "cta" }),
  );
});

test("a content entry with a blank affiliate url is rejected", () => {
  const map = { "6": { "10": "" } };
  assertThrowsClickNotAllowed(
    () => resolveVerifiedClick(map, { contentId: "6", productId: "10", placement: "cta" }),
    "no usable affiliate URL",
  );
});

test("non-numeric content id cannot be used to probe the prototype chain", () => {
  assertThrowsClickNotAllowed(
    () => resolveVerifiedClick(MAP, { contentId: "__proto__", productId: "10", placement: "cta" }),
    "invalid content id",
  );
});

test("non-numeric product id cannot be used to probe the prototype chain", () => {
  assertThrowsClickNotAllowed(
    () => resolveVerifiedClick(
      MAP, { contentId: "6", productId: "constructor", placement: "cta" }
    ),
    "invalid product id",
  );
});

test("no arbitrary redirect url can ever be injected -- there is no such parameter", () => {
  const params = { contentId: "6", productId: "10", placement: "cta" };
  assert.strictEqual(Object.prototype.hasOwnProperty.call(params, "url"), false);
  // Even if a caller tried to smuggle one in, resolveVerifiedClick's
  // destructuring signature only ever reads contentId/productId/placement.
  const url = resolveVerifiedClick(MAP, { ...params, url: "https://evil.example/phish" });
  assert.strictEqual(url, FIXTURE_URL);
});

test("resolveVerifiedClick never returns anything other than a redirectMap value", () => {
  // Structural: the return value must always be traceable to a
  // redirectMap[contentId][productId] entry, never derived from the
  // input params themselves.
  const url = resolveVerifiedClick(MAP, { contentId: "6", productId: "10", placement: "cta" });
  assert.strictEqual(url, MAP["6"]["10"]);
});

console.log(`\nALL TESTS PASSED (${passed})`);
