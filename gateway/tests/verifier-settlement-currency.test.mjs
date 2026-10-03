import assert from 'node:assert/strict';
import { test } from 'node:test';
import http from 'node:http';
import { spawnVerifier } from './helpers/spawn-verifier.mjs';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const hash = `0x${'a'.repeat(64)}`;
const payer = `0x${'2'.repeat(40)}`;
const recipient = `0x${'1'.repeat(40)}`;
const token = '0x20c0000000000000000000000000000000000000';
function payload(currency) {
  return {
    operation: 'payment', quote_hash: 'a'.repeat(64), payment_contract_hash: 'b'.repeat(64),
    payment_receipt: {
      method: 'tempo-mpp', rail: 'tempo-mpp', amount_cents: 1580, currency,
      merchant_id: 'test-shop',
      quote_hash: 'a'.repeat(64), payment_contract_hash: 'b'.repeat(64),
      external_value_proof: { provider: 'tempo_mpp', state: 'succeeded', amount: '15.80',
        network: 'testnet', recipient, payer_address: payer, transaction_reference: hash, token_address: token },
    },
    expected: { amount_cents: 1580, currency, merchant_id: 'test-shop', rail: 'tempo-mpp',
      quote_hash: 'a'.repeat(64),
      payment_contract_hash: 'b'.repeat(64), tempo_network: 'testnet', tempo_recipient: recipient },
  };
}
async function listen(server) {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  return server.address().port;
}
async function fixture(t, mode) {
  let rpcCalls = 0;
  const rpc = http.createServer(async (req, res) => {
    let raw = ''; for await (const chunk of req) raw += chunk;
    const respond = ({ id, method }) => {
      rpcCalls++;
      const receipt = { transactionHash: hash, transactionIndex: '0x0', blockHash: `0x${'c'.repeat(64)}`,
        blockNumber: '0x10', from: payer, to: token, cumulativeGasUsed: '0x1', gasUsed: '0x1',
        effectiveGasPrice: '0x1', contractAddress: null, logsBloom: `0x${'0'.repeat(512)}`, status: '0x1', type: '0x0',
        logs: [{ address: token, topics: ['0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef',
          `0x${payer.slice(2).padStart(64, '0')}`, `0x${recipient.slice(2).padStart(64, '0')}`],
          data: `0x${(15800000n).toString(16).padStart(64, '0')}`, blockNumber: '0x10', transactionHash: hash,
          transactionIndex: '0x0', blockHash: `0x${'c'.repeat(64)}`, logIndex: '0x0', removed: false }] };
      return { jsonrpc: '2.0', id, result: method === 'eth_getTransactionReceipt' ? receipt : '0x10' };
    };
    const body = JSON.parse(raw);
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify(Array.isArray(body) ? body.map(respond) : respond(body)));
  });
  const rpcPort = await listen(rpc);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'settlement-currency-'));
  let verifier;
  // Registered before spawning: a failed start must not leave the fake RPC server holding the test open.
  t.after(async () => {
    if (verifier) await verifier.close();
    await new Promise(resolve => rpc.close(resolve)); fs.rmSync(dir, { recursive: true, force: true });
  });
  verifier = await spawnVerifier({
    AGENTCART_VERIFIER_ENABLED_RAILS: 'tempo-mpp', AGENTCART_PAYMENT_VERIFIER_TOKEN: 'v'.repeat(40),
    AGENTCART_VERIFIER_REPLAY_STORE_DRIVER: 'file', AGENTCART_VERIFIER_REPLAY_STORE_PATH: path.join(dir, 'replay.json'),
    AGENTCART_TEMPO_SETTLEMENT_MODE: mode, AGENTCART_TEMPO_SETTLEMENT_RPC_URL: `http://127.0.0.1:${rpcPort}`,
    AGENTCART_TEMPO_SETTLEMENT_TOKEN_ADDRESS: token, AGENTCART_TEMPO_SETTLEMENT_ASSET: 'pathUSD',
    AGENTCART_TEMPO_REFUND_MODE: 'disabled',
  });
  const base = verifier.base;
  let ready = false;
  for (let attempt = 0; attempt < 100; attempt++) {
    if (verifier.child.exitCode !== null) throw new Error(verifier.output());
    try { ready = (await (await fetch(`${base}/health`)).json()).ok === true; } catch {}
    if (ready) break;
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  assert.ok(ready, verifier.output());
  return { rpcCalls: () => rpcCalls, verify: async input => {
    const response = await fetch(`${base}/agentcart/verify`, { method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${'v'.repeat(40)}` },
      body: JSON.stringify(typeof input === 'string' ? payload(input) : input) });
    return { status: response.status, body: await response.json() };
  } };
}

test('EUR pathUSD payment is rejected before RPC or replay claim; USD transfer still verifies', async t => {
  const verifier = await fixture(t, 'verify');
  const eur = await verifier.verify('EUR');
  assert.equal(eur.status, 400, JSON.stringify(eur));
  assert.equal(eur.body.provider_error_class, 'tempo_settlement_currency_mismatch');
  assert.equal(verifier.rpcCalls(), 0);
  const usd = await verifier.verify('USD');
  assert.equal(usd.status, 200, JSON.stringify(usd));
  assert.equal(usd.body.real_settlement_verified, true);
  assert.equal(usd.body.settlement_verification.raw_amount, '15800000');
  assert.equal(usd.body.idempotent_replay, undefined);
});

test('EUR demo proof explicitly labels numeric conversion and never claims real settlement', async t => {
  const verifier = await fixture(t, 'disabled');
  const result = await verifier.verify('EUR');
  assert.equal(result.status, 200, JSON.stringify(result));
  assert.equal(result.body.real_settlement_verified, false);
  assert.equal(result.body.fx.mode, 'demo_fixed_1_1');
  assert.equal(result.body.fx.quote_currency, 'EUR');
  assert.equal(verifier.rpcCalls(), 0);
});

for (const [field, error] of [
  ['amount_cents', 'expected.amount_cents must be a positive integer.'],
  ['currency', 'expected.currency is required.'],
  ['rail', 'Unsupported rail for this verifier: '],
  ['quote_hash', 'quote_hash is required.'],
  ['merchant_id', 'expected.merchant_id is required.'],
  ['tempo_recipient', 'expected.tempo_recipient is required.'],
  ['tempo_network', 'expected.tempo_network is required.'],
]) {
  test(`receipt-only ${field} cannot supply a trusted payment expectation`, async t => {
    const verifier = await fixture(t, 'verify');
    const request = payload('USD');
    delete request.expected[field];
    const result = await verifier.verify(request);
    assert.equal(result.status, 400, JSON.stringify(result));
    assert.equal(result.body.error, error);
    assert.equal(verifier.rpcCalls(), 0);
  });
}

test('trusted quote fields can supply expectations and still bind receipt values', async t => {
  const verifier = await fixture(t, 'verify');
  const request = payload('USD');
  request.quote = { total_cents: 1580, currency: 'USD', rail: 'tempo-mpp',
    quote_hash: 'a'.repeat(64), merchant: { id: 'test-shop' },
    payment_requirements: { protocols: [{ id: 'tempo-mpp', network: 'testnet', recipient }] } };
  for (const field of ['amount_cents', 'currency', 'rail', 'quote_hash', 'merchant_id', 'tempo_recipient', 'tempo_network']) {
    delete request.expected[field];
  }
  request.payment_receipt.currency = 'EUR';
  const mismatch = await verifier.verify(request);
  assert.equal(mismatch.status, 400);
  assert.equal(mismatch.body.error, 'payment_receipt.currency does not match expected.currency.');
  assert.equal(verifier.rpcCalls(), 0);
  request.payment_receipt.currency = 'USD';
  const result = await verifier.verify(request);
  assert.equal(result.status, 200, JSON.stringify(result));
  assert.equal(result.body.real_settlement_verified, true);
});
