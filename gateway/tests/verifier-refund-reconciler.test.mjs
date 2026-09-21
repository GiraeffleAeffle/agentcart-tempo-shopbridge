import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { claimSQLiteReplayReference, runSqlite } from '../scripts/verifier-sqlite-replay-store.mjs';
import { refundStore, advanceStripeRefund } from '../scripts/verifier-refund-operations.mjs';
import { reconciliationQueue, reconcileRefunds } from '../scripts/verifier-refund-reconciler.mjs';
const payment = { rail: 'stripe-card-mpp', currency: 'USD', quote_hash: 'quote', stripe_profile_id: 'profile' };
const binding = { ...payment, provider: 'stripe', amount_cents: 100, original_transaction_reference: 'pi_test' };
function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'refund-worker-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const db = path.join(dir, 'ledger.sqlite');
  claimSQLiteReplayReference({ dbPath: db, bucket: 'payments', reference: 'pi_test', metadata: { ...payment, amount_cents: 10000 } });
  return { db, store: refundStore(db), queue: reconciliationQueue(db) };
}
test('empty ledger never creates a refund; terminal operations are excluded', async t => {
  const { store, queue } = fixture(t);
  let calls = 0;
  assert.equal((await reconcileRefunds({ store, queue, advance: () => { calls++; } })).attempted, 0);
  const op = store.reserve('authorized', binding, payment);
  const stripe = { refunds: { create: async () => ({ id: 're_1', amount: 100, currency: 'usd', payment_intent: 'pi_test', status: 'succeeded' }) } };
  await advanceStripeRefund(store, op, stripe);
  assert.equal(queue.claim(), null);
  assert.equal(calls, 0);
  assert.deepEqual(store.verifiedPayment(op).stripe_profile_id, 'profile');
});
test('failed attempts survive restart, back off, stop at eight and do not starve newer work', async t => {
  const { db, store, queue } = fixture(t);
  store.reserve('old', binding, payment);
  let now = Date.now();
  for (let i = 0; i < 8; i++) {
    const result = await reconcileRefunds({ store: refundStore(db), queue: reconciliationQueue(db), now: () => now,
      advance: async () => { throw Error('SECRET provider/customer details'); } });
    assert.equal(result.errors, 1);
    assert.equal(queue.claim(now), null);
    now += 3600001;
  }
  assert.equal(queue.diagnostics(now).exhausted, 1);
  const fresh = store.reserve('fresh', binding, payment);
  assert.equal(queue.claim(now).request_key, fresh.request_key);
  assert.ok(!fs.readFileSync(db).includes(Buffer.from('SECRET')));
});
test('expired crash lease can be reclaimed; stale completion cannot release replacement lease', t => {
  const { store, queue } = fixture(t);
  store.reserve('one', binding, payment);
  const old = queue.claim(1000);
  assert.equal(queue.claim(1001), null);
  const replacement = queue.claim(301001);
  assert.notEqual(old.lease_token, replacement.lease_token);
  queue.finish(old, false, 301002);
  assert.equal(queue.claim(301003), null);
  assert.equal(queue.diagnostics(301003).leased, 1);
});
test('separate processes cannot lease the same operation concurrently', async t => {
  const { db, store } = fixture(t);
  store.reserve('one', binding, payment);
  const url = new URL('../scripts/verifier-refund-reconciler.mjs', import.meta.url).href;
  const run = () => new Promise((resolve, reject) => {
    const child = spawn(process.execPath, ['--input-type=module', '-e', `import {reconciliationQueue} from ${JSON.stringify(url)};process.exitCode=reconciliationQueue(${JSON.stringify(db)}).claim()?0:9;`]);
    child.on('error', reject); child.on('close', resolve);
  });
  assert.deepEqual((await Promise.all([run(), run()])).sort(), [0, 9]);
});
test('SQLite backup after lost Stripe acknowledgement resumes with the original provider idempotency key', async t => {
  const { db, store, queue } = fixture(t);
  const op = store.reserve('approved', binding, payment);
  const keys = [];
  const stripe = { refunds: { create: async (_body, options) => {
    keys.push(options.idempotencyKey);
    if (keys.length === 1) throw Error('acknowledgement lost after provider accepted');
    return { id: 're_original', amount: 100, currency: 'usd', payment_intent: 'pi_test', status: 'succeeded' };
  } } };
  const now = Date.now();
  await reconcileRefunds({ store, queue, now: () => now, advance: x => advanceStripeRefund(store, x, stripe) });
  const backup = path.join(path.dirname(db), 'restored.sqlite');
  runSqlite(db, `.backup '${backup}'`);
  const restored = refundStore(backup);
  const result = await reconcileRefunds({ store: restored, queue: reconciliationQueue(backup), now: () => now + 60001,
    advance: x => advanceStripeRefund(restored, x, stripe) });
  assert.equal(result.succeeded, 1);
  assert.equal(keys.length, 2); assert.equal(keys[0], keys[1]);
  assert.equal(restored.get(op.request_key).provider_reference, 're_original');
});
