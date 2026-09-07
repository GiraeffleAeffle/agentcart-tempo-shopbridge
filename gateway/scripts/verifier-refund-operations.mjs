// The ledger is the authority for refund capacity and broadcast identity.
// Provider calls happen only after reservation. Never release an unknown outcome.
import crypto from "node:crypto";
import { ensureSQLiteReplayStore, normalizeReplayMetadata, replayReferenceHash, runSqlite, sqlString as q } from "./verifier-sqlite-replay-store.mjs";

function fail(message, status = 409) { throw Object.assign(new Error(message), { status }); }
function rows(db, sql) {
  return JSON.parse(runSqlite(db, `.timeout 5000\n${sql}`, { json: true }).trim() || "[]");
}
function operation(row) {
  return row && { ...row, binding: JSON.parse(row.binding_json), result: JSON.parse(row.result_json) };
}
export function refundStore(db) {
  ensureSQLiteReplayStore(db);
  runSqlite(db, `PRAGMA busy_timeout=5000;
    CREATE TABLE IF NOT EXISTS refund_operations (
      request_key TEXT PRIMARY KEY, binding_hash TEXT NOT NULL, binding_json TEXT NOT NULL,
      payment_key TEXT NOT NULL, amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
      state TEXT NOT NULL, provider_reference TEXT NOT NULL DEFAULT '',
      signed_transaction TEXT NOT NULL DEFAULT '', result_json TEXT NOT NULL DEFAULT '{}',
      version INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
    CREATE INDEX IF NOT EXISTS refund_payment_key ON refund_operations(payment_key);
    CREATE TABLE IF NOT EXISTS refund_events (
      request_key TEXT NOT NULL, version INTEGER NOT NULL, state TEXT NOT NULL,
      provider_reference TEXT NOT NULL, created_at INTEGER NOT NULL,
      PRIMARY KEY(request_key,version));`);
  const get = (key) => operation(rows(db, `SELECT * FROM refund_operations WHERE request_key=${q(key)};`)[0]);
  return {
    get,
    diagnostics() {
      const counts = rows(db, "SELECT state,COUNT(*) AS count FROM refund_operations GROUP BY state;");
      const unresolved = rows(db, "SELECT MIN(created_at) AS oldest FROM refund_operations WHERE state NOT IN ('succeeded','failed','canceled');")[0];
      return { counts: Object.fromEntries(counts.map(row => [row.state, row.count])),
        oldest_unresolved_age_seconds: unresolved?.oldest ? Math.max(0, Math.floor((Date.now() - unresolved.oldest) / 1000)) : 0 };
    },
    reserve(reference, binding, paymentBinding) {
      if (!reference || reference.length > 255) fail("Refund request reference must contain 1 to 255 characters.", 400);
      binding = { ...binding, requested_reference: reference };
      const requestKey = replayReferenceHash(reference);
      const paymentKey = replayReferenceHash(binding.original_transaction_reference);
      const paymentRow = rows(db, `SELECT metadata_json FROM replay_claims WHERE bucket='payments' AND reference_hash=${q(paymentKey)};`)[0];
      if (!paymentRow) fail("Original verified payment is missing from the durable ledger; reconcile it before refunding.");
      const payment = JSON.parse(paymentRow.metadata_json);
      for (const [key, value] of Object.entries(paymentBinding)) {
        if (payment[key] !== value) fail(`Refund does not match stored payment ${key}.`, 400);
      }
      const cap = payment.amount_cents;
      if (!Number.isSafeInteger(cap) || cap <= 0 || !Number.isSafeInteger(binding.amount_cents) || binding.amount_cents <= 0) fail("Invalid stored payment or refund amount.", 400);
      const bindingJson = JSON.stringify(normalizeReplayMetadata(binding));
      const bindingHash = crypto.createHash("sha256").update(bindingJson).digest("hex");
      const now = Date.now();
      // BEGIN IMMEDIATE serializes distinct request IDs against the same balance.
      // Old replay-only refunds have unknown capacity: require migration/reconciliation.
      runSqlite(db, `PRAGMA busy_timeout=5000;
        BEGIN IMMEDIATE;
        INSERT OR IGNORE INTO refund_operations(request_key,binding_hash,binding_json,payment_key,amount_cents,state,created_at,updated_at)
        SELECT ${q(requestKey)},${q(bindingHash)},${q(bindingJson)},${q(paymentKey)},${binding.amount_cents},'reserved',${now},${now}
        WHERE ${binding.amount_cents} <= ${cap} - COALESCE((SELECT SUM(amount_cents) FROM refund_operations WHERE payment_key=${q(paymentKey)} AND state NOT IN ('failed','canceled')),0)
        AND NOT EXISTS (SELECT 1 FROM replay_claims r WHERE r.bucket IN ('refunds','refund_requests')
          AND json_extract(r.metadata_json,'$.original_transaction_reference')=${q(binding.original_transaction_reference)}
          AND NOT EXISTS (SELECT 1 FROM refund_operations o WHERE o.request_key=r.reference_hash
            OR o.provider_reference=json_extract(r.metadata_json,'$.refund_reference')
            OR o.provider_reference=json_extract(r.metadata_json,'$.requested_reference')));
        INSERT OR IGNORE INTO refund_events(request_key,version,state,provider_reference,created_at)
        SELECT request_key,0,'reserved','',created_at FROM refund_operations WHERE request_key=${q(requestKey)};
        COMMIT;`);
      const result = get(requestKey);
      if (!result) fail("Refund exceeds unreserved payment balance or a legacy refund needs reconciliation.");
      if (result.binding_hash !== bindingHash) fail("Refund request reference is already bound to a different operation.");
      return result;
    },
    update(op, patch) {
      const allowed = new Set(["state", "provider_reference", "signed_transaction", "result_json"]);
      for (const key of Object.keys(patch)) if (!allowed.has(key)) fail("Invalid refund ledger update.", 500);
      const updates = Object.entries(patch).map(([key, value]) => `${key}=${q(value)}`).join(",");
      runSqlite(db, `PRAGMA busy_timeout=5000; BEGIN IMMEDIATE;
        UPDATE refund_operations SET ${updates}, version=version+1,updated_at=${Date.now()}
        WHERE request_key=${q(op.request_key)} AND version=${op.version};
        INSERT OR IGNORE INTO refund_events(request_key,version,state,provider_reference,created_at)
        SELECT request_key,version,state,provider_reference,updated_at FROM refund_operations
        WHERE request_key=${q(op.request_key)} AND version=${op.version + 1};
        COMMIT;`);
      return get(op.request_key); // A losing worker uses the winner's persisted identity.
    },
  };
}

export function refundResult(op) {
  return {
    ...op.binding, ...op.result,
    ok: true, refund_reference: op.provider_reference,
    requested_reference: op.binding.requested_reference,
    replay_reference: op.provider_reference || op.request_key,
    replay_request_hash: op.binding_hash,
    refund_status: op.state,
    real_refund_verified: op.state === "succeeded",
    retryable: ["reserved", "prepared", "pending"].includes(op.state),
    operator_review_required: ["review_required", "requires_action"].includes(op.state),
  };
}

export function hasRefundTransfer(receipt, { token, from, to, amount }) {
  const topic = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef';
  const addressTopic = address => `0x${'0'.repeat(24)}${address.slice(2).toLowerCase()}`;
  return (receipt.logs || []).some(log => {
    try {
      return String(log.address).toLowerCase() === token.toLowerCase()
        && log.topics?.length === 3 && String(log.topics[0]).toLowerCase() === topic
        && String(log.topics[1]).toLowerCase() === addressTopic(from)
        && String(log.topics[2]).toLowerCase() === addressTopic(to)
        && /^0x[0-9a-fA-F]{64}$/.test(log.data) && BigInt(log.data) === amount;
    } catch { return false; }
  });
}

export async function advanceStripeRefund(store, op, stripe, { now = Date.now() } = {}) {
  if (["failed", "canceled"].includes(op.state)) return op;
  let result;
  if (op.provider_reference) {
    result = await stripe.refunds.retrieve(op.provider_reference);
  } else {
    // Stripe may prune idempotency keys after 24h. Unknown old submissions must
    // be reconciled with the provider, never resubmitted as a new refund.
    if (now - op.created_at >= 23 * 60 * 60 * 1000) fail("Unresolved Stripe submission requires provider reconciliation; do not change its request reference.");
    result = await stripe.refunds.create({
      amount: op.amount_cents, payment_intent: op.binding.original_transaction_reference,
      reason: "requested_by_customer",
      metadata: { agentcart_quote_hash: op.binding.quote_hash, agentcart_refund_request: op.request_key },
    }, { idempotencyKey: `shopbridge-refund-${op.request_key}` });
  }
  if (!result.id || result.amount !== op.amount_cents || String(result.currency).toUpperCase() !== op.binding.currency
    || (result.payment_intent?.id || result.payment_intent) !== op.binding.original_transaction_reference) fail("Stripe refund evidence does not match the reserved operation.", 502);
  const state = ["pending", "requires_action", "succeeded", "failed", "canceled"].includes(result.status) ? result.status : "pending";
  return store.update(op, { state, provider_reference: result.id, result_json: JSON.stringify({ provider_status: result.status }) });
}

export async function advanceTempoRefund(store, op, { prepare, broadcast, receipt }) {
  if (["succeeded", "failed", "review_required"].includes(op.state)) return op;
  if (!op.signed_transaction) {
    // Each operation gets a permanent 2D nonce lane at nonce 0, not an expiring
    // nonce. A concurrent loser must discard its signed bytes without sending.
    const prepared = await prepare(BigInt(`0x${op.request_key.slice(0, 62)}`) + 1n);
    op = store.update(op, { state: "prepared", provider_reference: prepared.hash, signed_transaction: prepared.raw });
  }
  // Recover by persisted hash first. A lost RPC acknowledgement is not failure.
  let confirmed = await receipt(op.provider_reference).catch(() => null);
  if (!confirmed) {
    await broadcast(op.signed_transaction).catch(() => null);
    confirmed = await receipt(op.provider_reference).catch(() => null);
  }
  if (!confirmed) return op;
  if (!['success', 'reverted', 'review_required'].includes(confirmed.status)) return op;
  return store.update(op, {
    state: confirmed.status === "success" ? "succeeded" : confirmed.status === "reverted" ? "failed" : "review_required",
    result_json: JSON.stringify({ block_hash: confirmed.blockHash, block_number: confirmed.blockNumber?.toString() }),
  });
}
