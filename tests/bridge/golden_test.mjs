// Cross-language golden digest verification (AC02 TS side).
// Run with: node --test tests/bridge/golden_test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { canonicalize } from "../../bridge/protocol/canonicalize.mjs";

function sha256Hex(value) {
  return createHash("sha256").update(canonicalize(value), "utf8").digest("hex");
}

const golden = JSON.parse(
  readFileSync(new URL("../../contracts/v1/golden-digests.json", import.meta.url), "utf8"),
);

for (const vec of golden.vectors) {
  test(`golden vector ${vec.id}`, () => {
    assert.equal(sha256Hex(vec.value), vec.sha256);
  });
}

test("snapshot body digest excludes shell", () => {
  const body = JSON.parse(
    readFileSync(new URL("../../contracts/v1/examples.json", import.meta.url), "utf8"),
  ).valid_snapshot_body;
  const d1 = sha256Hex(body);
  const withShell = { ...body, approval: "pending" };
  // shell is outside the body; canonicalize of body must be stable
  assert.equal(sha256Hex(body), d1);
  assert.notEqual(sha256Hex(withShell), d1);
});
