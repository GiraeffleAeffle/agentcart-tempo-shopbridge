import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { canonicalJson } from "../scripts/onchain-registry-indexer.mjs";
import { sha256Canonical } from "../scripts/onchain-registry-indexer-loop.mjs";

const fixture = JSON.parse(
  await readFile(new URL("../../docs/fixtures/canonical-json/vectors.json", import.meta.url), "utf8"),
);

for (const vector of fixture.cases) {
  test(`indexer canonical JSON: ${vector.name}`, () => {
    const canonical = canonicalJson(vector.value);
    assert.equal(canonical, vector.canonical);
    assert.equal(createHash("sha256").update(canonical, "utf8").digest("hex"), vector.sha256);
  });
  test(`independent indexer history hash: ${vector.name}`, () => {
    assert.equal(sha256Canonical(vector.value), vector.sha256);
  });
}
