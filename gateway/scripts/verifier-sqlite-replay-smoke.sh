#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"

if ! command -v sqlite3 >/dev/null 2>&1; then
  printf 'sqlite3 unavailable; skipping verifier sqlite replay smoke\n'
  exit 0
fi

tmpdir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmpdir"
}
trap cleanup EXIT

node - "$ROOT_DIR" "$tmpdir/replay.sqlite" <<'JS'
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import path from "node:path";

const root = process.argv[2];
const db = process.argv[3];
const tool = path.join(root, "gateway/scripts/verifier-sqlite-replay-store.mjs");

function claim(bucket, reference, metadata) {
  return new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        tool,
        "claim",
        "--db",
        db,
        "--bucket",
        bucket,
        "--reference",
        reference,
        "--metadata-json",
        JSON.stringify(metadata),
      ],
      { stdio: ["ignore", "pipe", "pipe"] },
    );
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(`claim exited ${code}: ${stderr || stdout}`));
        return;
      }
      resolve(JSON.parse(stdout));
    });
  });
}

function diagnostics() {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [tool, "diagnostics", "--db", db], {
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(`diagnostics exited ${code}: ${stderr || stdout}`));
        return;
      }
      resolve(JSON.parse(stdout));
    });
  });
}

function metadata(bucket, variant) {
  return {
    provider: "stripe",
    rail: "stripe-card-mpp",
    amount_cents: variant === "base" ? 1840 : 1940,
    currency: "EUR",
    quote_hash: `${bucket}_${variant}`.padEnd(64, "0").slice(0, 64),
    payment_contract_hash: `${variant === "base" ? "a" : "b"}`.repeat(64),
    original_transaction_reference: bucket === "payments" ? undefined : "pi_original_001",
    requested_reference: bucket === "refunds" ? "refund-request-001" : undefined,
  };
}

for (const bucket of ["payments", "refund_requests", "refunds"]) {
  const replayReference = `${bucket}_reference_001`;
  const first = await claim(bucket, replayReference, metadata(bucket, "base"));
  assert.equal(first.ok, true, first);
  assert.equal(first.status, "accepted", first);

  const conflicts = await Promise.all(
    Array.from({ length: 8 }, () => claim(bucket, replayReference, metadata(bucket, "conflict"))),
  );
  assert.equal(conflicts.length, 8);
  for (const result of conflicts) {
    assert.equal(result.ok, false, result);
    assert.equal(result.status, "conflict", result);
    assert.equal(result.existingRequestHash, first.requestHash, result);
  }

  const idempotent = await claim(bucket, replayReference, metadata(bucket, "base"));
  assert.equal(idempotent.ok, true, idempotent);
  assert.equal(idempotent.idempotentReplay, true, idempotent);

  const raceReference = `${bucket}_race_reference`;
  const race = await Promise.all([
    claim(bucket, raceReference, { ...metadata(bucket, "base"), race: "a" }),
    claim(bucket, raceReference, { ...metadata(bucket, "conflict"), race: "b" }),
    claim(bucket, raceReference, { ...metadata(bucket, "conflict"), race: "c" }),
    claim(bucket, raceReference, { ...metadata(bucket, "conflict"), race: "d" }),
  ]);
  assert.equal(race.filter((result) => result.ok && result.status === "accepted").length, 1, race);
  assert.equal(race.filter((result) => !result.ok && result.status === "conflict").length, 3, race);
}

const status = await diagnostics();
assert.equal(status.kind, "sqlite", status);
assert.equal(status.durable, true, status);
assert.equal(status.locking, "sqlite-immediate-transaction", status);
assert.equal(status.writable, true, status);
assert.deepEqual(status.counts, { payments: 2, refund_requests: 2, refunds: 2 }, status);

console.log("verifier sqlite replay smoke ok");
JS
