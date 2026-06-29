#!/usr/bin/env node
import crypto from "node:crypto";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_BUSY_TIMEOUT_MS = 5000;
const BUCKETS = new Set(["payments", "refund_requests", "refunds"]);

function sqlString(value) {
  return `'${String(value ?? "").replaceAll("'", "''")}'`;
}

function requireBucket(bucket) {
  const normalized = String(bucket || "").trim();
  if (!BUCKETS.has(normalized)) {
    throw Object.assign(new Error(`unsupported verifier replay bucket: ${bucket}`), { status: 400 });
  }
  return normalized;
}

function runSqlite(dbPath, sql, { json = false } = {}) {
  if (!dbPath) throw Object.assign(new Error("sqlite replay store path is required"), { status: 500 });
  if (!fs.existsSync(path.dirname(dbPath))) {
    fs.mkdirSync(path.dirname(dbPath), { recursive: true });
  }
  const args = ["-batch"];
  if (json) args.push("-json");
  args.push(dbPath);
  const completed = spawnSync("sqlite3", args, {
    input: sql,
    encoding: "utf8",
    maxBuffer: 1024 * 1024,
  });
  if (completed.error) {
    throw Object.assign(new Error(`sqlite3 unavailable: ${completed.error.message}`), { status: 500 });
  }
  if (completed.status !== 0) {
    const message = (completed.stderr || completed.stdout || "sqlite3 failed").trim();
    throw Object.assign(new Error(message), { status: 500 });
  }
  return completed.stdout || "";
}

function sqliteJsonRows(dbPath, sql) {
  const output = runSqlite(dbPath, sql, { json: true }).trim();
  if (!output) return [];
  return JSON.parse(output);
}

function sqliteLastJsonObject(dbPath, sql) {
  const output = runSqlite(dbPath, sql)
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (!output.length) throw Object.assign(new Error("sqlite replay store returned no result"), { status: 500 });
  return JSON.parse(output[output.length - 1]);
}

export function normalizeReplayMetadata(value) {
  if (Array.isArray(value)) return value.map((entry) => normalizeReplayMetadata(entry));
  if (!value || typeof value !== "object") return value;
  const normalized = {};
  for (const key of Object.keys(value).sort()) {
    const entry = value[key];
    if (entry !== undefined) normalized[key] = normalizeReplayMetadata(entry);
  }
  return normalized;
}

export function replayReferenceHash(reference) {
  return crypto.createHash("sha256").update(String(reference || "").trim()).digest("hex");
}

export function replayRequestHash(bucket, reference, metadata = {}) {
  return crypto
    .createHash("sha256")
    .update(
      JSON.stringify({
        bucket: requireBucket(bucket),
        reference: String(reference || "").trim(),
        metadata: normalizeReplayMetadata(metadata),
      }),
    )
    .digest("hex");
}

export function ensureSQLiteReplayStore(dbPath, { busyTimeoutMs = DEFAULT_BUSY_TIMEOUT_MS } = {}) {
  runSqlite(
    dbPath,
    `
PRAGMA busy_timeout=${Number(busyTimeoutMs) || DEFAULT_BUSY_TIMEOUT_MS};
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS replay_claims (
  bucket TEXT NOT NULL,
  reference_hash TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  replay_count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (bucket, reference_hash)
);
CREATE INDEX IF NOT EXISTS idx_replay_claims_bucket ON replay_claims(bucket);
`,
  );
}

export function sqliteReplayStoreWriteProbe(dbPath, { busyTimeoutMs = DEFAULT_BUSY_TIMEOUT_MS } = {}) {
  if (!dbPath) {
    return {
      ok: false,
      durable: false,
      driver: "sqlite",
      error: "AGENTCART_VERIFIER_REPLAY_STORE_PATH is required for sqlite replay storage",
    };
  }
  try {
    ensureSQLiteReplayStore(dbPath, { busyTimeoutMs });
    runSqlite(
      dbPath,
      `
PRAGMA busy_timeout=${Number(busyTimeoutMs) || DEFAULT_BUSY_TIMEOUT_MS};
CREATE TABLE IF NOT EXISTS replay_store_probe (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  checked_at TEXT NOT NULL
);
INSERT INTO replay_store_probe(id, checked_at)
VALUES (1, ${sqlString(new Date().toISOString())})
ON CONFLICT(id) DO UPDATE SET checked_at = excluded.checked_at;
DROP TABLE replay_store_probe;
`,
    );
    return { ok: true, durable: true, driver: "sqlite" };
  } catch (error) {
    return {
      ok: false,
      durable: true,
      driver: "sqlite",
      error: `Could not write sqlite verifier replay store: ${error.message}`,
    };
  }
}

export function sqliteReplayStoreDiagnostics(dbPath, { busyTimeoutMs = DEFAULT_BUSY_TIMEOUT_MS } = {}) {
  const diagnostics = {
    label: dbPath || "sqlite-unconfigured",
    kind: "sqlite",
    durable: Boolean(dbPath),
    locking: "sqlite-immediate-transaction",
    counts: null,
    error: null,
    writable: false,
    schema: "agentcart.verifierReplay.sqlite.v1",
  };
  if (!dbPath) {
    diagnostics.error = "AGENTCART_VERIFIER_REPLAY_STORE_PATH is required for sqlite replay storage";
    return diagnostics;
  }
  try {
    const writeProbe = sqliteReplayStoreWriteProbe(dbPath, { busyTimeoutMs });
    diagnostics.writable = Boolean(writeProbe.ok);
    if (!writeProbe.ok) diagnostics.error = writeProbe.error;
    const rows = sqliteJsonRows(
      dbPath,
      `
SELECT bucket, COUNT(*) AS count
FROM replay_claims
GROUP BY bucket
ORDER BY bucket;
`,
    );
    const counts = { payments: 0, refund_requests: 0, refunds: 0 };
    for (const row of rows) {
      if (BUCKETS.has(row.bucket)) counts[row.bucket] = Number(row.count || 0);
    }
    diagnostics.counts = counts;
  } catch (error) {
    diagnostics.error = error.message;
  }
  return diagnostics;
}

export function claimSQLiteReplayReference({
  dbPath,
  bucket,
  reference,
  metadata = {},
  requestHash = "",
  busyTimeoutMs = DEFAULT_BUSY_TIMEOUT_MS,
  now = new Date().toISOString(),
}) {
  const safeBucket = requireBucket(bucket);
  const key = String(reference || "").trim();
  if (!key) throw Object.assign(new Error("replay reference is required"), { status: 400 });
  const normalizedMetadata = normalizeReplayMetadata(metadata);
  const referenceHash = replayReferenceHash(key);
  const safeRequestHash = requestHash || replayRequestHash(safeBucket, key, normalizedMetadata);
  const metadataJson = JSON.stringify(normalizedMetadata);
  ensureSQLiteReplayStore(dbPath, { busyTimeoutMs });
  const result = sqliteLastJsonObject(
    dbPath,
    `
PRAGMA busy_timeout=${Number(busyTimeoutMs) || DEFAULT_BUSY_TIMEOUT_MS};
BEGIN IMMEDIATE;
CREATE TEMP TABLE claim_input (
  bucket TEXT NOT NULL,
  reference_hash TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  now TEXT NOT NULL
);
INSERT INTO claim_input(bucket, reference_hash, request_hash, metadata_json, now)
VALUES (
  ${sqlString(safeBucket)},
  ${sqlString(referenceHash)},
  ${sqlString(safeRequestHash)},
  ${sqlString(metadataJson)},
  ${sqlString(now)}
);
INSERT OR IGNORE INTO replay_claims(
  bucket,
  reference_hash,
  request_hash,
  metadata_json,
  first_seen_at,
  last_seen_at,
  replay_count
)
SELECT bucket, reference_hash, request_hash, metadata_json, now, now, 0
FROM claim_input;
CREATE TEMP TABLE claim_inserted AS SELECT changes() AS inserted;
CREATE TEMP TABLE claim_result AS
SELECT
  CASE
    WHEN (SELECT inserted FROM claim_inserted) = 1 THEN 'accepted'
    WHEN replay_claims.request_hash = claim_input.request_hash THEN 'idempotent'
    ELSE 'conflict'
  END AS status,
  replay_claims.request_hash AS existing_request_hash,
  replay_claims.metadata_json AS existing_metadata_json,
  replay_claims.first_seen_at AS first_seen_at,
  replay_claims.replay_count AS replay_count
FROM replay_claims, claim_input
WHERE replay_claims.bucket = claim_input.bucket
  AND replay_claims.reference_hash = claim_input.reference_hash;
UPDATE replay_claims
SET replay_count = replay_count + 1,
    last_seen_at = (SELECT now FROM claim_input)
WHERE bucket = (SELECT bucket FROM claim_input)
  AND reference_hash = (SELECT reference_hash FROM claim_input)
  AND (SELECT status FROM claim_result) = 'idempotent';
UPDATE claim_result
SET replay_count = (
  SELECT replay_count
  FROM replay_claims
  WHERE bucket = (SELECT bucket FROM claim_input)
    AND reference_hash = (SELECT reference_hash FROM claim_input)
)
WHERE status = 'idempotent';
COMMIT;
SELECT json_object(
  'status', status,
  'existing_request_hash', existing_request_hash,
  'existing_metadata_json', existing_metadata_json,
  'first_seen_at', first_seen_at,
  'replay_count', replay_count
) FROM claim_result;
`,
  );
  const existingMetadata = result.existing_metadata_json ? JSON.parse(result.existing_metadata_json) : {};
  if (result.status === "conflict") {
    return {
      ok: false,
      status: "conflict",
      requestHash: safeRequestHash,
      existingRequestHash: result.existing_request_hash,
      referenceHash,
      existing: {
        first_seen_at: result.first_seen_at,
        replay_count: Number(result.replay_count || 0),
        request_hash: result.existing_request_hash,
        metadata: existingMetadata,
      },
    };
  }
  return {
    ok: true,
    status: result.status,
    idempotentReplay: result.status === "idempotent",
    requestHash: safeRequestHash,
    referenceHash,
    existing: {
      first_seen_at: result.first_seen_at,
      replay_count: Number(result.replay_count || 0),
      request_hash: result.existing_request_hash,
      metadata: existingMetadata,
    },
  };
}

function parseArgs(argv) {
  const args = { _: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (!value.startsWith("--")) {
      args._.push(value);
      continue;
    }
    const key = value.slice(2);
    const next = argv[index + 1];
    if (!next || next.startsWith("--")) {
      args[key] = "true";
      continue;
    }
    args[key] = next;
    index += 1;
  }
  return args;
}

function cli() {
  const args = parseArgs(process.argv.slice(2));
  const command = args._[0] || "";
  try {
    if (command === "claim") {
      const metadata = args["metadata-json"] ? JSON.parse(args["metadata-json"]) : {};
      const result = claimSQLiteReplayReference({
        dbPath: args.db || "",
        bucket: args.bucket || "",
        reference: args.reference || "",
        metadata,
        requestHash: args["request-hash"] || "",
        busyTimeoutMs: Number(args["busy-timeout-ms"] || DEFAULT_BUSY_TIMEOUT_MS),
      });
      console.log(JSON.stringify(result, null, 2));
      return 0;
    }
    if (command === "diagnostics") {
      console.log(
        JSON.stringify(
          sqliteReplayStoreDiagnostics(args.db || "", {
            busyTimeoutMs: Number(args["busy-timeout-ms"] || DEFAULT_BUSY_TIMEOUT_MS),
          }),
          null,
          2,
        ),
      );
      return 0;
    }
    console.error("usage: verifier-sqlite-replay-store.mjs <claim|diagnostics> --db PATH [options]");
    return 2;
  } catch (error) {
    console.error(
      JSON.stringify(
        {
          ok: false,
          error: error instanceof Error ? error.message : String(error),
        },
        null,
        2,
      ),
    );
    return Number.isInteger(error?.status) ? error.status : 1;
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exitCode = cli();
}
