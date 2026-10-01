import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { keccak256, toBytes } from 'viem';
import {
  createX402Verifier, x402Config, x402MissingConfig, x402Fetch, x402Store,
  x402AuthorizationNonce, X402_ASSET, X402_NETWORK, AUTHORIZATION_USED_TOPIC,
} from '../scripts/verifier-x402.mjs';
import { runSqlite } from '../scripts/verifier-sqlite-replay-store.mjs';
import { fakeX402, PAYER, PAY_TO, TX, NONCE } from './helpers/fake-x402.mjs';

const RESOURCE = 'https://shop.example/wp-json/agentcart/v1/orders';
function input() {
  const accepted = {
    scheme: 'exact', network: X402_NETWORK, amount: '1000000', asset: X402_ASSET,
    payTo: PAY_TO, maxTimeoutSeconds: 300, extra: { name: 'USDC', version: '2' },
  };
  const payment = {
    x402Version: 2, accepted, resource: { url: RESOURCE },
    payload: {
      signature: `0x${'11'.repeat(65)}`,
      authorization: {
        from: PAYER, to: PAY_TO, value: '1000000', validAfter: '0',
        validBefore: String(Math.floor(Date.now() / 1000) + 300), nonce: NONCE,
      },
    },
  };
  const expected = {
    amountCents: 100, currency: 'USD', quoteHash: 'a'.repeat(64),
    paymentContractHash: 'b'.repeat(64), merchantId: 'test-shop', rail: 'x402-compatible',
  };
  const payload = {
    quote: { payment_requirements: { checkout_endpoint: RESOURCE } },
    expected: {
      x402_network: X402_NETWORK, x402_asset: X402_ASSET, x402_pay_to: PAY_TO,
      x402_payment_requirements: structuredClone(accepted),
    },
    payment_receipt: {
      method: 'x402-compatible', status: 'authorized', x402_version: 2,
      rail: 'x402-compatible', network: X402_NETWORK, asset: X402_ASSET,
      pay_to: PAY_TO, amount: '1000000', currency: 'USD', amount_cents: 100,
      quote_hash: expected.quoteHash, payment_contract_hash: expected.paymentContractHash,
      x402_payment_signature: Buffer.from(JSON.stringify(payment)).toString('base64'),
    },
  };
  return { payload, expected, payment };
}
function encode(i) {
  i.payload.payment_receipt.x402_payment_signature = Buffer.from(JSON.stringify(i.payment)).toString('base64');
}
function authorizationKey(i) {
  return `${X402_NETWORK}:${X402_ASSET.toLowerCase()}:${PAYER}:${i.payment.payload.authorization.nonce}`;
}
async function setup(t) {
  const fake = await fakeX402();
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'x402-'));
  const config = {
    ...x402Config({}), mode: 'settle', allowPrivate: true,
    facilitator: fake.facilitator, rpc: fake.rpc, driver: 'sqlite', db: path.join(dir, 'replay.db'),
  };
  t.after(async () => {
    await fake.close();
    fs.rmSync(dir, { recursive: true, force: true });
  });
  const verifier = createX402Verifier(config);
  return { fake, config, verifier, run: i => verifier.payment(i.payload, i.expected) };
}
const retryable = e => e.code === 'x402_settlement_unconfirmed' && e.status === 502 && e.retryable === true;

test('AuthorizationUsed topic is pinned', () => {
  assert.equal(AUTHORIZATION_USED_TOPIC, '0x98de503528ee59b575ef0c0a2576a82497bfc029a5685b209e9ec333479b10a5');
  assert.equal(keccak256(toBytes('AuthorizationUsed(address,bytes32)')), AUTHORIZATION_USED_TOPIC);
});
test('nonce commitment matches the shared protocol vector', () => {
  assert.equal(x402AuthorizationNonce('a'.repeat(64), 'b'.repeat(64), RESOURCE), NONCE);
});
test('happy path emits PAYMENT-RESPONSE; settled retry has no outbound calls', async t => {
  const s = await setup(t);
  const i = input();
  const result = await s.run(i);
  assert.equal(result.real_settlement_verified, true);
  assert.equal(result.transaction_reference, TX);
  assert.deepEqual(JSON.parse(Buffer.from(result.payment_response_header_value, 'base64')), result.x402_settle_response);
  const before = [s.fake.state.calls.length, s.fake.state.rpcCalls.length];
  assert.deepEqual(await s.run(i), result);
  assert.deepEqual([s.fake.state.calls.length, s.fake.state.rpcCalls.length], before);
  assert.equal(x402Store(s.config.db).get(authorizationKey(i)).transaction_hash, TX);
});
test('concurrent identical requests settle exactly once', async t => {
  const s = await setup(t);
  const i = input();
  const result = await Promise.all([s.run(i), s.run(i)]);
  assert.deepEqual(result[0], result[1]);
  assert.equal(s.fake.state.calls.filter(x => x === '/settle').length, 1);
});
for (const field of ['amount', 'payTo', 'asset', 'network']) {
  test(`accepted ${field} mismatch rejected before verify`, async t => {
    const s = await setup(t);
    const i = input();
    i.payment.accepted[field] = 'wrong';
    encode(i);
    await assert.rejects(s.run(i), e => e.code === 'x402_accepted_mismatch');
    assert.deepEqual(s.fake.state.calls, []);
  });
}
for (const field of ['amount', 'pay_to', 'asset', 'network', 'quote_hash', 'payment_contract_hash']) {
  test(`receipt ${field} mismatch rejected before verify`, async t => {
    const s = await setup(t);
    const i = input();
    i.payload.payment_receipt[field] = 'wrong';
    await assert.rejects(s.run(i));
    assert.deepEqual(s.fake.state.calls, []);
  });
}
test('merchant and receipt outbound URLs are ignored', async t => {
  const s = await setup(t);
  const i = input();
  Object.assign(i.payload.expected, { x402_facilitator_url: 'http://127.0.0.1:1', x402_rpc_url: 'http://127.0.0.1:1' });
  Object.assign(i.payload.payment_receipt, { facilitator_url: 'http://127.0.0.1:1', rpc_url: 'http://127.0.0.1:1' });
  assert.equal((await s.run(i)).real_settlement_verified, true);
  assert.deepEqual(s.fake.state.calls, ['/verify', '/settle']);
});
test('private hosts, HTTP and redirects fail without following', async t => {
  const s = await setup(t);
  await assert.rejects(x402Fetch('https://127.0.0.1'));
  await assert.rejects(x402Fetch(s.fake.facilitator));
  s.fake.state.redirect = true;
  await assert.rejects(x402Fetch(s.fake.facilitator, { allowPrivate: true }));
  assert.equal(s.fake.state.calls.length, 1);
});
test('invalid verify before submission rejects without settling', async t => {
  const s = await setup(t);
  s.fake.state.invalid = true;
  await assert.rejects(s.run(input()), e => e.code === 'x402_verify_invalid');
  assert.deepEqual(s.fake.state.calls, ['/verify']);
});
for (const field of ['missingTransfer', 'wrongAmount']) {
  test(`settlement ${field} never reports real`, async t => {
    const s = await setup(t);
    s.fake.state[field] = true;
    await assert.rejects(s.run(input()), e => e.code === 'x402_settlement_transfer_missing');
  });
}
test('missing AuthorizationUsed remains recoverable while nonce is used', async t => {
  const s = await setup(t);
  const i = input();
  s.fake.state.missingAuthorization = true;
  await assert.rejects(s.run(i), retryable);
  assert.equal(x402Store(s.config.db).get(authorizationKey(i)).state, 'settling');
  s.fake.state.missingAuthorization = false;
  assert.equal((await s.run(i)).real_settlement_verified, true);
});
test('ambiguous settle reconciles AuthorizationUsed on chain', async t => {
  const s = await setup(t);
  s.fake.state.ambiguous = true;
  assert.equal((await s.run(input())).real_settlement_verified, true);
  assert.ok(s.fake.state.rpcCalls.includes('eth_getLogs'));
});
test('unresolved ambiguous settle returns retryable 502', async t => {
  const s = await setup(t);
  s.fake.state.ambiguous = true;
  s.fake.state.unresolved = true;
  await assert.rejects(s.run(input()), retryable);
});
test('different quote binding rejects before any facilitator call', async t => {
  const s = await setup(t);
  const i = input();
  await s.run(i);
  const before = s.fake.state.calls.length;
  i.expected.quoteHash = 'c'.repeat(64);
  i.payload.payment_receipt.quote_hash = i.expected.quoteHash;
  await assert.rejects(s.run(i), e => e.code === 'x402_authorization_nonce_mismatch');
  assert.equal(s.fake.state.calls.length, before);
});
test('transaction hash cannot bind another authorization', async t => {
  const s = await setup(t);
  await s.run(input());
  const i = input();
  i.expected.quoteHash = 'c'.repeat(64);
  i.payload.payment_receipt.quote_hash = i.expected.quoteHash;
  i.payment.payload.authorization.nonce = x402AuthorizationNonce(i.expected.quoteHash, i.expected.paymentContractHash, RESOURCE);
  encode(i);
  await assert.rejects(s.run(i), e => e.code === 'x402_transaction_replay_conflict');
});
test('crashed settling reservation reconciles without second settle', async t => {
  const s = await setup(t);
  const i = input();
  const binding = {
    quote_hash: i.expected.quoteHash, payment_contract_hash: i.expected.paymentContractHash,
    amount: '1000000', pay_to: PAY_TO, network: X402_NETWORK, asset: X402_ASSET.toLowerCase(),
    amount_cents: 100, currency: 'USD',
  };
  const store = x402Store(s.config.db);
  store.reserve(authorizationKey(i), binding, Number(i.payment.payload.authorization.validBefore), 101n);
  store.acquire(authorizationKey(i), 'crashed');
  s.fake.state.settled = true;
  s.fake.state.authorization = i.payment.payload.authorization;
  const restarted = createX402Verifier(s.config);
  assert.equal((await restarted.payment(i.payload, i.expected)).real_settlement_verified, true);
  assert.deepEqual(s.fake.state.calls, []);
});
test('EUR is rejected before outbound calls', async t => {
  const s = await setup(t);
  const i = input();
  i.expected.currency = 'EUR';
  await assert.rejects(s.run(i), e => e.code === 'x402_currency_unsupported');
  assert.deepEqual(s.fake.state.calls, []);
});
test('disabled and invalid configuration report missingConfig', () => {
  assert.ok(x402MissingConfig(x402Config({}), true).includes('AGENTCART_X402_MODE'));
  assert.ok(x402MissingConfig(x402Config({ AGENTCART_X402_MODE: 'settle' }), true).includes('AGENTCART_VERIFIER_REPLAY_STORE_DRIVER'));
});
test('supported capability caches for ten minutes; payments do not require it', async t => {
  const s = await setup(t);
  assert.equal(s.verifier.capability(true).facilitator.supported_kind_confirmed, null);
  await s.verifier.refresh();
  await s.verifier.refresh();
  assert.equal(s.verifier.capability(true).facilitator.supported_kind_confirmed, true);
  assert.deepEqual(s.fake.state.calls, ['/supported']);
});
test('outbound calls cap response bytes and elapsed time', async t => {
  const server = http.createServer((req, res) => {
    if (req.url === '/large') res.end('x'.repeat(262145));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  const base = `http://127.0.0.1:${server.address().port}`;
  await assert.rejects(x402Fetch(`${base}/large`, { allowPrivate: true }), /too large/);
  const started = Date.now();
  await assert.rejects(x402Fetch(`${base}/hang`, { allowPrivate: true, timeout: 100 }), /timeout/);
  assert.ok(Date.now() - started < 1000);
});
test('global deadline includes pre-provider work and stops submission', async t => {
  const s = await setup(t);
  const i = input();
  await assert.rejects(s.verifier.payment(i.payload, i.expected, Date.now() - 1), retryable);
  assert.deepEqual(s.fake.state.calls, []);
});
async function processVerifier(config) {
  const portServer = http.createServer();
  await new Promise(resolve => portServer.listen(0, '127.0.0.1', resolve));
  const port = portServer.address().port;
  await new Promise(resolve => portServer.close(resolve));
  const child = spawn(process.execPath, ['scripts/stripe-mpp-verifier.mjs'], {
    cwd: new URL('..', import.meta.url),
    env: {
      ...process.env, STRIPE_MPP_VERIFIER_PORT: String(port), AGENTCART_PAYMENT_VERIFIER_TOKEN: 'v'.repeat(40),
      AGENTCART_VERIFIER_ENABLED_RAILS: 'x402-compatible', AGENTCART_X402_MODE: config.mode,
      AGENTCART_X402_ALLOW_PRIVATE_URLS: 'true', AGENTCART_X402_FACILITATOR_URL: config.facilitator,
      AGENTCART_X402_RPC_URL: config.rpc, AGENTCART_VERIFIER_REPLAY_STORE_DRIVER: 'sqlite',
      AGENTCART_VERIFIER_REPLAY_STORE_PATH: config.db,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let output = '';
  child.stdout.on('data', data => output += data);
  child.stderr.on('data', data => output += data);
  const base = `http://127.0.0.1:${port}`;
  for (let n = 0; n < 100; n++) {
    try {
      await fetch(`${base}/health`);
      break;
    } catch {
      if (child.exitCode !== null) throw new Error(output);
      await new Promise(resolve => setTimeout(resolve, 50));
    }
  }
  return {
    close: async () => {
      if (child.exitCode === null) {
        const exit = new Promise(resolve => child.once('exit', resolve));
        child.kill();
        await exit;
      }
    },
    post: async payload => {
      const res = await fetch(`${base}/agentcart/verify`, {
        method: 'POST', headers: { 'content-type': 'application/json', authorization: `Bearer ${'v'.repeat(40)}` },
        body: JSON.stringify(payload),
      });
      return { status: res.status, body: await res.json() };
    },
  };
}
function httpInput() {
  const i = input();
  Object.assign(i.payload.expected, {
    amount_cents: 100, currency: 'USD', merchant_id: 'test-shop', rail: 'x402-compatible',
    quote_hash: i.expected.quoteHash, payment_contract_hash: i.expected.paymentContractHash,
  });
  return i;
}
test('actual verifier HTTP payment, restart persistence, refund rejection and disabled mode', async t => {
  const s = await setup(t);
  const i = httpInput();
  let process = await processVerifier(s.config);
  let result = await process.post(i.payload);
  assert.equal(result.status, 200, JSON.stringify(result));
  assert.equal(result.body.real_settlement_verified, true);
  await process.close();
  const count = [s.fake.state.calls.length, s.fake.state.rpcCalls.length];
  process = await processVerifier(s.config);
  result = await process.post(i.payload);
  assert.equal(result.status, 200);
  assert.deepEqual([s.fake.state.calls.length, s.fake.state.rpcCalls.length], count);
  result = await process.post({ operation: 'refund', rail: 'x402-compatible' });
  assert.equal(result.status, 400);
  assert.equal(result.body.error, 'x402_refund_unsupported');
  assert.equal(result.body.real_refund_verified, false);
  await process.close();
  process = await processVerifier({ ...s.config, mode: 'disabled' });
  result = await process.post(i.payload);
  assert.equal(result.status, 503);
  await process.close();
});
test('multi-rail quote verifies against the selected rail contract, not the default rail hash', async t => {
  const s = await setup(t);
  const i = httpInput();
  const tempoHash = 'c'.repeat(64);
  const contracts = [
    { rail: 'tempo-mpp', payment_contract_hash: tempoHash },
    { rail: 'x402-compatible', payment_contract_hash: i.expected.paymentContractHash },
  ];
  i.payload.quote = {
    quote_hash: i.expected.quoteHash, total_cents: 100, currency: 'USD', merchant_id: 'test-shop',
    payment_requirements: {
      checkout_endpoint: RESOURCE, payment_contract_hash: tempoHash,
      verification: { payment_contract_hash: tempoHash }, verification_contracts: contracts,
    },
  };
  const verifier = await processVerifier(s.config);
  t.after(() => verifier.close());
  let result = await verifier.post(i.payload);
  assert.equal(result.status, 200, JSON.stringify(result.body));
  assert.equal(result.body.real_settlement_verified, true);
  i.payload.quote.payment_requirements.verification_contracts = [contracts[0]];
  result = await verifier.post(i.payload);
  assert.equal(result.status, 400);
  assert.match(String(result.body.error), /exactly one verification contract/);
  i.payload.quote.payment_requirements.verification_contracts = [contracts[0], { ...contracts[1], payment_contract_hash: 'd'.repeat(64) }];
  result = await verifier.post(i.payload);
  assert.equal(result.status, 400);
  assert.match(String(result.body.error), /payment_contract_hash values do not match/);
});
test('old settlement beyond 600 blocks reconciles from reservation', async t => {
  const s = await setup(t);
  const i = input();
  s.fake.state.ambiguous = true;
  s.fake.state.unresolved = true;
  await assert.rejects(s.run(i), retryable);
  s.fake.state.settled = true;
  s.fake.state.latestBlock = 2000;
  assert.equal((await s.run(i)).real_settlement_verified, true);
  assert.equal(s.fake.state.calls.filter(call => call === '/settle').length, 1);
  assert.equal(x402Store(s.config.db).get(authorizationKey(i)).start_block, '101');
});
test('verify invalid after submission remains retryable then finalizes', async t => {
  const s = await setup(t);
  const i = input();
  s.fake.state.ambiguous = true;
  s.fake.state.unresolved = true;
  await assert.rejects(s.run(i), retryable);
  s.fake.state.invalid = true;
  await assert.rejects(s.run(i), retryable);
  assert.equal(x402Store(s.config.db).get(authorizationKey(i)).state, 'settling');
  s.fake.state.settled = true;
  assert.equal((await s.run(i)).real_settlement_verified, true);
  assert.equal(s.fake.state.calls.filter(call => call === '/settle').length, 1);
});
test('numeric RPC error codes become retryable settlement errors', async t => {
  const s = await setup(t);
  s.fake.state.rpcError = { code: -32000, message: 'temporarily unavailable' };
  await assert.rejects(s.run(input()), retryable);
});
test('wrong nonce rejects before verify', async t => {
  const s = await setup(t);
  const i = input();
  i.payment.payload.authorization.nonce = `0x${'ef'.repeat(32)}`;
  encode(i);
  await assert.rejects(s.run(i), e => e.code === 'x402_authorization_nonce_mismatch');
  assert.deepEqual(s.fake.state.calls, []);
});
test('resource mismatch rejects before verify', async t => {
  const s = await setup(t);
  const i = input();
  i.payment.resource.url += '/other';
  encode(i);
  await assert.rejects(s.run(i), e => e.code === 'x402_resource_mismatch');
  assert.deepEqual(s.fake.state.calls, []);
});
for (const [field, offset] of [['validAfter', 61], ['validBefore', 361], ['validBefore', -1]]) {
  test(`authorization window ${field} ${offset} rejects before verify`, async t => {
    const s = await setup(t);
    const now = Date.now();
    t.mock.method(Date, 'now', () => now);
    const i = input();
    i.payment.payload.authorization[field] = String(Math.floor(Date.now() / 1000) + offset);
    encode(i);
    await assert.rejects(s.run(i), e => e.code === 'x402_authorization_window_invalid');
    assert.deepEqual(s.fake.state.calls, []);
  });
}
test('busy release cannot replace a successfully finalized payment', async t => {
  const s = await setup(t);
  x402Store(s.config.db);
  runSqlite(s.config.db, `CREATE TRIGGER busy_release BEFORE UPDATE OF lease_until ON x402_authorizations
    WHEN OLD.state='settled' BEGIN SELECT RAISE(FAIL, 'SQLITE_BUSY: database is locked'); END;`);
  assert.equal((await s.run(input())).real_settlement_verified, true);
});
test('settle has enough time for a delayed Base Sepolia facilitator', async t => {
  const s = await setup(t);
  s.fake.state.callsDelay['/settle'] = 3200;
  assert.equal((await s.run(input())).real_settlement_verified, true);
  assert.ok(!s.fake.state.rpcCalls.includes('eth_getLogs'));
});

test('capability fails readiness for missing replay database or unsupported facilitator', async t => {
  const s = await setup(t);
  const missingDatabase = await processVerifier({ ...s.config, db: '' });
  t.after(() => missingDatabase.close());
  let response = await missingDatabase.post({ operation: 'capabilities' });
  assert.equal(response.body.ok, false);
  assert.equal(response.body.x402.configured, false);
  assert.ok(response.body.missing.includes('AGENTCART_VERIFIER_REPLAY_STORE_PATH'));
  s.fake.state.unsupported = true;
  const unsupported = await processVerifier(s.config);
  t.after(() => unsupported.close());
  response = await unsupported.post({ operation: 'capabilities' });
  assert.equal(response.body.x402.configured, true);
  assert.equal(response.body.x402.facilitator.supported_kind_confirmed, false);
});

test('chunked scanning resumes after a missing-log retry', async t => {
  const s = await setup(t);
  const i = input();
  s.fake.state.ambiguous = true;
  s.fake.state.unresolved = true;
  await assert.rejects(s.run(i), retryable);
  s.fake.state.settled = true;
  s.fake.state.missingAuthorization = true;
  s.fake.state.latestBlock = 2000;
  await assert.rejects(s.run(i), retryable);
  const op = x402Store(s.config.db).get(authorizationKey(i));
  assert.equal(op.state, 'settling');
  assert.equal(op.scan_cursor, '2000');
  const ranges = s.fake.state.rpcRequests.filter(request => request.method === 'eth_getLogs').map(request => request.params[0]);
  assert.ok(ranges.every(range => BigInt(range.toBlock) - BigInt(range.fromBlock) < 500n));
  s.fake.state.missingAuthorization = false;
  s.fake.state.settlementBlock = 2000;
  assert.equal((await s.run(i)).real_settlement_verified, true);
});

test('unused expired reservations fail but used expired reservations finalize', async t => {
  const s = await setup(t);
  const i = input();
  s.fake.state.ambiguous = true;
  s.fake.state.unresolved = true;
  await assert.rejects(s.run(i), retryable);
  const clock = Date.now;
  Date.now = () => clock() + 400000;
  try {
    s.fake.state.settled = true;
    assert.equal((await s.run(i)).real_settlement_verified, true);
  } finally {
    Date.now = clock;
  }
  const second = await setup(t);
  const j = input();
  second.fake.state.ambiguous = true;
  second.fake.state.unresolved = true;
  await assert.rejects(second.run(j), retryable);
  second.fake.state.blockTimestamp = Number(j.payment.payload.authorization.validBefore) + 2;
  Date.now = () => clock() + 400000;
  try {
    await assert.rejects(second.run(j), e => e.code === 'x402_authorization_expired');
    assert.equal(x402Store(second.config.db).get(authorizationKey(j)).state, 'failed');
    assert.equal(second.fake.state.calls.filter(call => call === '/settle').length, 1);
  } finally {
    Date.now = clock;
  }
});

test('wall-clock expiry with lagging RPC stays retryable then finalizes', async t => {
  const s = await setup(t);
  const i = input();
  const now = Date.now();
  const expiry = Math.floor(now / 1000) + 2;
  i.payment.payload.authorization.validBefore = String(expiry);
  encode(i);
  s.fake.state.blockTimestamp = expiry - 1;
  s.fake.state.ambiguous = true;
  s.fake.state.unresolved = true;
  await assert.rejects(s.run(i), retryable);
  t.mock.method(Date, 'now', () => now + 3000);
  await assert.rejects(s.run(i), retryable);
  assert.equal(x402Store(s.config.db).get(authorizationKey(i)).state, 'settling');
  s.fake.state.settled = true;
  assert.equal((await s.run(i)).real_settlement_verified, true);
  assert.equal(s.fake.state.calls.filter(call => call === '/settle').length, 1);
});

test('unused authorization expires only at confirmed chain time', async t => {
  const s = await setup(t);
  const i = input();
  const now = Date.now();
  t.mock.method(Date, 'now', () => now);
  const expiry = Number(i.payment.payload.authorization.validBefore);
  s.config.confirmations = 3;
  s.fake.state.ambiguous = true;
  s.fake.state.unresolved = true;
  await assert.rejects(s.run(i), retryable);
  // Latest has passed expiry, but B=latest-confirmations has not.
  s.fake.state.blockTimestamp = expiry + 5;
  await assert.rejects(s.run(i), retryable);
  assert.equal(x402Store(s.config.db).get(authorizationKey(i)).state, 'settling');
  // B now has timestamp exactly validBefore, with unused nonce pinned to B.
  s.fake.state.blockTimestamp = expiry + 6;
  await assert.rejects(s.run(i), e => e.code === 'x402_authorization_expired');
  assert.equal(x402Store(s.config.db).get(authorizationKey(i)).state, 'failed');
});

test('latest unused cannot override a used authorization at the confirmed block', async t => {
  const s = await setup(t);
  const i = input();
  const now = Date.now();
  s.fake.state.ambiguous = true;
  s.fake.state.unresolved = true;
  await assert.rejects(s.run(i), retryable);
  t.mock.method(Date, 'now', () => now + 400000);
  s.fake.state.blockTimestamp = Number(i.payment.payload.authorization.validBefore) + 2;
  s.fake.state.authorizationStateOverrides['0x64'] = true;
  await assert.rejects(s.run(i), retryable);
  assert.equal(x402Store(s.config.db).get(authorizationKey(i)).state, 'settling');
  s.fake.state.settled = true;
  assert.equal((await s.run(i)).real_settlement_verified, true);
});

test('135-byte resource nonce matches the viem padding-boundary vector', () => {
  const resource = 'https://shop.example/' + 'a'.repeat(114);
  assert.equal(Buffer.byteLength(resource), 135);
  assert.equal(x402AuthorizationNonce('a'.repeat(64), 'b'.repeat(64), resource),
    '0x797957b73a812296388f2a4949c7373c301db0a72979366e53b07bf7688150a5');
});
