import assert from 'node:assert/strict';
import { test } from 'node:test';
import { spawnSync } from 'node:child_process';
import { generatePrivateKey, privateKeyToAccount } from 'viem/accounts';
import { hashDomain, recoverTypedDataAddress } from 'viem';
import { fakeX402 } from './helpers/fake-x402.mjs';
import { createX402Verifier, x402Config } from '../scripts/verifier-x402.mjs';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

function python(command, args) {
  const result = spawnSync('python3', ['shopbridge-direct-skill/scripts/shopbridge-command.py'], {
    input: JSON.stringify({ command, args }), encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

test('registry-bound skill typed data signs with an external ephemeral wallet and settles', async t => {
  const fixture = spawnSync('python3', ['-c', `import json
from tests.test_shopbridge_direct_skill import X402BuyerTests, shopbridge_direct
quote = X402BuyerTests().bound_quote()
approval = shopbridge_direct.approval_packet(quote)
print(json.dumps({'quote': quote, 'approval': approval}))`], { encoding: 'utf8' });
  assert.equal(fixture.status, 0, fixture.stderr);
  const { quote, approval } = JSON.parse(fixture.stdout);
  const approvalArgs = { quote, payment_rail: 'x402-compatible', approved: true,
    approval_hash: approval.approval_hash };
  const handoff = python('payment_handoff', approvalArgs);
  const account = privateKeyToAccount(generatePrivateKey());
  const signingArgs = { ...approvalArgs, payment_handoff: handoff, payer: account.address };
  const { typed_data: typedData } = python('x402_typed_data', signingArgs);
  assert.equal(hashDomain({ domain: typedData.domain, types: typedData.types }),
    '0x71f17a3b2ff373b803d70a5a07c046c1a2bc8e89c09ef722fcb047abe94c9818');
  const signature = await account.signTypedData(typedData);
  assert.equal((await recoverTypedDataAddress({ ...typedData, signature })).toLowerCase(), account.address.toLowerCase());
  const result = python('x402_receipt', { ...signingArgs, signature });
  const checkout = python('checkout_payload', {
    ...approvalArgs, payment_receipt: result.payment_receipt, ...result.checkout_args,
  });
  const fake = await fakeX402({ derivePayer: true });
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'x402-wallet-'));
  t.after(async () => { await fake.close(); fs.rmSync(dir, { recursive: true, force: true }); });
  const verifier = createX402Verifier({ ...x402Config({}), mode: 'settle', allowPrivate: true,
    facilitator: fake.facilitator, rpc: fake.rpc, driver: 'sqlite', db: path.join(dir, 'replay.db') });
  const accepted = handoff.payment_request.accepted;
  const settled = await verifier.payment({ ...checkout, quote,
    expected: { x402_network: accepted.network, x402_asset: accepted.asset, x402_pay_to: accepted.payTo,
      x402_payment_requirements: accepted }, payment_receipt: result.payment_receipt }, {
    amountCents: quote.total_cents, currency: quote.currency, quoteHash: quote.quote_hash,
    paymentContractHash: result.payment_receipt.payment_contract_hash,
    merchantId: quote.merchant.id, rail: 'x402-compatible',
  });
  assert.equal(settled.real_settlement_verified, true);
  assert.deepEqual(fake.state.calls, ['/verify', '/settle']);
});
