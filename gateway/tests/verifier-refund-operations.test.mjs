import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { claimSQLiteReplayReference } from '../scripts/verifier-sqlite-replay-store.mjs';
import { refundStore, refundResult, advanceStripeRefund, advanceTempoRefund, hasRefundTransfer } from '../scripts/verifier-refund-operations.mjs';
import { privateKeyToAccount } from 'viem/accounts';
import { keccak256 } from 'viem';
import { tempoModerato } from 'viem/tempo/chains';
import { TxEnvelopeTempo } from 'ox/tempo';

const payment = { rail: 'stripe-card-mpp', currency: 'USD', quote_hash: 'quote', stripe_profile_id: 'profile' };
const binding = { ...payment, provider: 'stripe', amount_cents: 6000, original_transaction_reference: 'pi_test' };
function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'refund-ledger-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const db = path.join(dir, 'ledger.sqlite');
  claimSQLiteReplayReference({ dbPath: db, bucket: 'payments', reference: 'pi_test', metadata: { ...payment, amount_cents: 10000 } });
  return { db, store: refundStore(db) };
}

test('distinct simultaneous refund IDs cannot reserve more than the verified payment', async (t) => {
  const { db, store } = fixture(t);
  const moduleUrl = new URL('../scripts/verifier-refund-operations.mjs', import.meta.url).href;
  const run = (id) => new Promise((resolve, reject) => {
    const script = `import {refundStore} from ${JSON.stringify(moduleUrl)}; try {refundStore(${JSON.stringify(db)}).reserve(${JSON.stringify(id)},${JSON.stringify(binding)},${JSON.stringify(payment)});} catch(e) {process.exitCode=e.status === 409 ? 9 : 1;}`;
    const child = spawn(process.execPath, ['--input-type=module', '-e', script]);
    child.on('error', reject); child.on('close', resolve);
  });
  assert.deepEqual((await Promise.all([run('one'), run('two')])).sort(), [0, 9]);
  assert.throws(() => store.reserve('third', binding, payment), /balance/);
});

test('capacity and recipient bindings come from stored evidence; idempotency survives restart', (t) => {
  const { db, store } = fixture(t);
  const op = store.reserve('one', binding, payment);
  assert.equal(refundStore(db).reserve('one', binding, payment).request_key, op.request_key);
  assert.equal(refundResult(op).requested_reference, 'one');
  assert.throws(() => store.reserve('one', { ...binding, amount_cents: 1 }, payment), /different operation/);
  assert.throws(() => store.reserve('forged', binding, { ...payment, currency: 'EUR' }), /stored payment/);
  assert.throws(() => store.reserve('missing', { ...binding, original_transaction_reference: 'pi_missing' }, payment), /missing/);
});

test('legacy ambiguous requests block fresh refunds for the same payment', (t) => {
  const { store, db } = fixture(t);
  claimSQLiteReplayReference({ dbPath: db, bucket: 'refund_requests', reference: 'old', metadata: { original_transaction_reference: 'pi_test' } });
  assert.throws(() => store.reserve('new', binding, payment), /legacy/);
});

test('Stripe pending is polled by provider ID; only succeeded authorizes a completion claim', async (t) => {
  const { store } = fixture(t);
  let creates = 0; let retrieves = 0;
  const result = { id: 're_1', amount: 6000, currency: 'usd', payment_intent: 'pi_test', status: 'pending' };
  const stripe = { refunds: {
    create: async () => { creates++; return result; },
    retrieve: async (id) => { retrieves++; assert.equal(id, 're_1'); return { ...result, status: 'succeeded' }; },
  } };
  let op = await advanceStripeRefund(store, store.reserve('one', binding, payment), stripe);
  assert.equal(refundResult(op).real_refund_verified, false);
  assert.throws(() => store.reserve('two', binding, payment), /balance/);
  op = await advanceStripeRefund(store, op, stripe);
  assert.equal(refundResult(op).real_refund_verified, true);
  assert.equal(creates, 1); assert.equal(retrieves, 1);
});

for (const status of ['failed', 'canceled', 'requires_action', 'unrecognized']) {
  test(`Stripe ${status} never claims completion`, async (t) => {
    const { store } = fixture(t);
    const stripe = { refunds: { create: async () => ({ id: 're_1', amount: 6000, currency: 'usd', payment_intent: 'pi_test', status }) } };
    const op = await advanceStripeRefund(store, store.reserve('one', binding, payment), stripe);
    assert.equal(refundResult(op).real_refund_verified, false);
    if (['failed', 'canceled'].includes(status)) assert.ok(store.reserve('two', binding, payment));
    else assert.throws(() => store.reserve('two', binding, payment), /balance/);
  });
}

test('an unknown Stripe submission beyond its safe idempotency window requires reconciliation', async (t) => {
  const { store } = fixture(t);
  const op = store.reserve('one', binding, payment);
  await assert.rejects(advanceStripeRefund(store, op, {}, { now: op.created_at + 86400000 }), /reconciliation/);
});

test('crash before or after Tempo RPC acknowledgement resends identical persisted bytes', async (t) => {
  const { store, db } = fixture(t);
  let prepares = 0; const broadcasts = []; let succeeded = false;
  const effects = {
    prepare: async (nonce) => { prepares++; assert.ok(nonce > 0n); return { raw: '0xsigned', hash: '0xtx' }; },
    broadcast: async (raw) => { broadcasts.push(raw); throw new Error('lost acknowledgement'); },
    receipt: async () => succeeded ? { status: 'success', blockNumber: 123n, blockHash: '0xblock' } : null,
  };
  let op = await advanceTempoRefund(store, store.reserve('one', binding, payment), effects);
  assert.equal(op.state, 'prepared'); assert.equal(refundResult(op).real_refund_verified, false);
  const restarted = refundStore(db);
  op = await advanceTempoRefund(restarted, restarted.get(op.request_key), effects);
  assert.deepEqual(broadcasts, ['0xsigned', '0xsigned']); assert.equal(prepares, 1);
  succeeded = true;
  op = await advanceTempoRefund(restarted, op, effects);
  assert.equal(refundResult(op).real_refund_verified, true);
  assert.equal(broadcasts.length, 2);
});

test('concurrent Tempo preparation broadcasts only the persisted winner', async (t) => {
  const { store } = fixture(t);
  const op = store.reserve('one', binding, payment);
  const sent = [];
  const run = (raw) => advanceTempoRefund(store, op, {
    prepare: async () => ({ raw, hash: `hash-${raw}` }),
    broadcast: async (raw) => sent.push(raw), receipt: async () => null,
  });
  await Promise.all([run('first'), run('second')]);
  assert.equal(new Set(sent).size, 1);
  assert.equal(sent[0], store.get(op.request_key).signed_transaction);
});

test('a confirmed reverted Tempo transaction releases capacity without creating another transfer', async (t) => {
  const { store } = fixture(t);
  const op = await advanceTempoRefund(store, store.reserve('one', binding, payment), {
    prepare: async () => ({ raw: 'signed', hash: 'hash' }), broadcast: async () => {},
    receipt: async () => ({ status: 'reverted' }),
  });
  assert.equal(op.state, 'failed'); assert.equal(refundResult(op).real_refund_verified, false);
  assert.ok(store.reserve('two', binding, payment));
});

test('pinned viem signer serializes a permanent 2D nonce and reproducible broadcast hash', async () => {
  // Public deterministic fixture key; signing is offline and never broadcast.
  const account = privateKeyToAccount('0x' + '1'.padStart(64, '0'));
  const raw = await account.signTransaction({ chainId: 42431,
    to: '0x20c0000000000000000000000000000000000000', data: '0xa9059cbb',
    nonce: 0, nonceKey: 123n, gas: 100000n, maxFeePerGas: 1000000000n, maxPriorityFeePerGas: 1000000000n,
  }, { serializer: tempoModerato.serializers.transaction });
  const decoded = TxEnvelopeTempo.deserialize(raw);
  assert.equal(decoded.nonceKey, 123n); assert.equal(decoded.nonce, 0n);
  assert.equal(decoded.validBefore, undefined);
  assert.equal(TxEnvelopeTempo.hash(decoded), keccak256(raw));
});

test('a successful receipt must contain the exact token transfer', () => {
  const token = '0x' + 'a'.repeat(40), from = '0x' + 'b'.repeat(40), to = '0x' + 'c'.repeat(40);
  const expected = { token, from, to, amount: 60000000n };
  const log = { address: token, topics: ['0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef',
    '0x' + '0'.repeat(24) + from.slice(2), '0x' + '0'.repeat(24) + to.slice(2)], data: '0x' + expected.amount.toString(16).padStart(64, '0') };
  assert.equal(hasRefundTransfer({ logs: [log] }, expected), true);
  assert.equal(hasRefundTransfer({ logs: [] }, expected), false);
  assert.equal(hasRefundTransfer({ logs: [log] }, { ...expected, amount: 1n }), false);
  assert.equal(hasRefundTransfer({ logs: [log] }, { ...expected, to: from }), false);
});
