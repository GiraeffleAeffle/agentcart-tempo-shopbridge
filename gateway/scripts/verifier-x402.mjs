import crypto from 'node:crypto';
import dns from 'node:dns/promises';
import http from 'node:http';
import https from 'node:https';
import net from 'node:net';
import { isDeepStrictEqual } from 'node:util';
import { createPublicClient, http as transport, keccak256 } from 'viem';
import { baseSepolia } from 'viem/chains';
import { ensureSQLiteReplayStore, runSqlite, sqlString as q, replayReferenceHash, normalizeReplayMetadata } from './verifier-sqlite-replay-store.mjs';

export const X402_NETWORK = 'eip155:84532';
export const X402_ASSET = '0x036CbD53842c5426634e7929541eC2318f3dCF7e';
export const AUTHORIZATION_USED_TOPIC = '0x98de503528ee59b575ef0c0a2576a82497bfc029a5685b209e9ec333479b10a5';
export const X402_GLOBAL_BUDGET_MS = 12000;
const VERIFY_BUDGET_MS = 2500;
const CONFIRM_BUDGET_MS = 1500;
const LOG_CHUNK_BLOCKS = 500n;
const TRANSFER_TOPIC = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef';
const address = value => /^0x[\da-f]{40}$/i.test(String(value)) ? String(value).toLowerCase() : '';
const hash = value => /^0x[\da-f]{64}$/i.test(String(value));
const topicAddress = value => `0x${'0'.repeat(24)}${value.slice(2).toLowerCase()}`;
const canonical = value => JSON.stringify(normalizeReplayMetadata(value));
function fail(code, status = 400, retryable = false) {
  throw Object.assign(new Error(code), { code, status, retryable });
}
function unconfirmed() {
  fail('x402_settlement_unconfirmed', 502, true);
}
function protocolError(error) {
  if (typeof error.code === 'string' && error.code.startsWith('x402_')) throw error;
  unconfirmed();
}
function mutate(db, sql) {
  return runSqlite(db, `PRAGMA busy_timeout=500;\n${sql}`);
}
function rows(db, sql) {
  return JSON.parse(runSqlite(db, `.timeout 500\n${sql}`, { json: true }).trim() || '[]');
}

export function x402AuthorizationNonce(quoteHash, paymentContractHash, resourceUrl) {
  if (!/^[\da-f]{64}$/i.test(quoteHash) || !/^[\da-f]{64}$/i.test(paymentContractHash) || typeof resourceUrl !== 'string' || !resourceUrl) {
    fail('x402_authorization_binding_invalid');
  }
  return keccak256(Buffer.concat([
    Buffer.from('shopbridge-x402-nonce-v1', 'utf8'),
    Buffer.from(quoteHash, 'hex'),
    Buffer.from(paymentContractHash, 'hex'),
    Buffer.from(keccak256(Buffer.from(resourceUrl, 'utf8')).slice(2), 'hex'),
  ])).toLowerCase();
}

export function x402Config(env = process.env) {
  const mode = env.AGENTCART_X402_MODE || 'disabled';
  return {
    mode: ['disabled', 'settle'].includes(mode) ? mode : 'invalid',
    network: env.AGENTCART_X402_NETWORK || X402_NETWORK,
    facilitator: env.AGENTCART_X402_FACILITATOR_URL || 'https://x402.org/facilitator',
    rpc: env.AGENTCART_X402_RPC_URL || 'https://sepolia.base.org',
    confirmations: Number(env.AGENTCART_X402_CONFIRMATIONS || 1),
    timeout: Number(env.AGENTCART_X402_FACILITATOR_TIMEOUT_MS || 7000),
    allowPrivate: env.AGENTCART_X402_ALLOW_PRIVATE_URLS === 'true',
    db: env.AGENTCART_VERIFIER_REPLAY_STORE_PATH || '',
    driver: env.AGENTCART_VERIFIER_REPLAY_STORE_DRIVER || '',
  };
}
export function x402MissingConfig(config, enabled) {
  const missing = [];
  if (!enabled) return missing;
  if (config.mode !== 'settle') missing.push('AGENTCART_X402_MODE');
  if (config.network !== X402_NETWORK) missing.push('AGENTCART_X402_NETWORK');
  if (!Number.isInteger(config.confirmations) || config.confirmations < 1) missing.push('AGENTCART_X402_CONFIRMATIONS');
  if (!Number.isInteger(config.timeout) || config.timeout < 100 || config.timeout > 7000) missing.push('AGENTCART_X402_FACILITATOR_TIMEOUT_MS');
  if (config.driver !== 'sqlite') missing.push('AGENTCART_VERIFIER_REPLAY_STORE_DRIVER');
  if (!config.db) missing.push('AGENTCART_VERIFIER_REPLAY_STORE_PATH');
  for (const [key, value] of [
    ['AGENTCART_X402_FACILITATOR_URL', config.facilitator],
    ['AGENTCART_X402_RPC_URL', config.rpc],
  ]) {
    try {
      const url = new URL(value);
      if ((!config.allowPrivate && url.protocol !== 'https:') || !['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.hash || url.search) missing.push(key);
    } catch {
      missing.push(key);
    }
  }
  return missing;
}
function globalIP(ip) {
  if (net.isIP(ip) === 4) {
    const [a, b] = ip.split('.').map(Number);
    return !(a === 0 || a === 10 || a === 127 || a >= 224 || (a === 100 && b >= 64 && b <= 127) || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31) || (a === 192 && [0, 168].includes(b)) || (a === 198 && [18, 19, 51].includes(b)) || (a === 203 && b === 0));
  }
  // Permit only global-unicast IPv6, excluding documentation and mapped IPv4.
  return net.isIP(ip) === 6 && /^[23]/.test(ip) && !/^(2001:(0:|2:|10:|20:|db8:)|2002:|3fff:)/i.test(ip);
}
export async function x402Fetch(url, { method = 'GET', body, headers = {}, signal, timeout = 1500, allowPrivate = false } = {}) {
  const deadline = Date.now() + timeout;
  const parsed = new URL(url);
  if ((!allowPrivate && parsed.protocol !== 'https:') || !['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) fail('x402_outbound_url_rejected');
  const hostname = parsed.hostname.replace(/^\[|\]$/g, '');
  let dnsTimer;
  let resolved;
  try {
    resolved = await Promise.race([
      dns.lookup(hostname, { all: true }),
      new Promise((_, reject) => {
        dnsTimer = setTimeout(() => reject(new Error('DNS timeout')), timeout);
      }),
    ]);
  } finally {
    clearTimeout(dnsTimer);
  }
  if (!resolved.length || (!allowPrivate && resolved.some(item => !globalIP(item.address)))) fail('x402_outbound_private_host');
  const selected = resolved[0];
  return new Promise((resolve, reject) => {
    const req = (parsed.protocol === 'https:' ? https : http).request(parsed, {
      method, headers, signal,
      lookup: (_host, options, cb) => options?.all ? cb(null, [selected]) : cb(null, selected.address, selected.family),
    }, res => {
      if (res.statusCode >= 300 && res.statusCode < 400) {
        res.resume();
        reject(new Error('x402 redirect rejected'));
        return;
      }
      const chunks = [];
      let size = 0;
      res.on('data', chunk => {
        size += chunk.length;
        if (size > 262144) req.destroy(new Error('x402 response too large'));
        else chunks.push(chunk);
      });
      res.on('end', () => resolve(new Response([204, 205].includes(res.statusCode) ? null : Buffer.concat(chunks), { status: res.statusCode, headers: res.headers })));
      res.on('error', reject);
    });
    const timer = setTimeout(() => req.destroy(new Error('x402 outbound timeout')), Math.max(1, deadline - Date.now()));
    req.on('close', () => clearTimeout(timer));
    req.on('error', reject);
    if (body) req.write(body);
    req.end();
  });
}

export function x402Store(db) {
  ensureSQLiteReplayStore(db, { busyTimeoutMs: 500 });
  mutate(db, `CREATE TABLE IF NOT EXISTS x402_authorizations (
    key TEXT PRIMARY KEY, binding_json TEXT NOT NULL, state TEXT NOT NULL,
    result_json TEXT NOT NULL DEFAULT '{}', lease TEXT NOT NULL DEFAULT '',
    lease_until INTEGER NOT NULL DEFAULT 0, valid_before INTEGER NOT NULL,
    start_block TEXT NOT NULL DEFAULT '0', scan_cursor TEXT NOT NULL DEFAULT '0',
    transaction_hash TEXT NOT NULL DEFAULT ''
  );`);
  // Older reservations have no block reference: scan from genesis, never a moving tail.
  const columns = rows(db, 'PRAGMA table_info(x402_authorizations)').map(column => column.name);
  for (const [name, defaultValue] of [['start_block', '0'], ['scan_cursor', '0'], ['transaction_hash', '']]) {
    if (!columns.includes(name)) mutate(db, `ALTER TABLE x402_authorizations ADD COLUMN ${name} TEXT NOT NULL DEFAULT ${q(defaultValue)};`);
  }
  const get = key => rows(db, `SELECT * FROM x402_authorizations WHERE key=${q(key)}`)[0];
  return {
    get,
    reserve(key, binding, validBefore, startBlock) {
      mutate(db, `BEGIN IMMEDIATE;
        INSERT OR IGNORE INTO x402_authorizations(key,binding_json,state,valid_before,start_block,scan_cursor)
        VALUES(${q(key)},${q(canonical(binding))},'settling',${validBefore},${q(String(startBlock))},${q(String(startBlock))});
        COMMIT;`);
      const op = get(key);
      if (op.binding_json !== canonical(binding)) fail('x402_authorization_binding_conflict', 409);
      return op;
    },
    acquire(key, owner) {
      mutate(db, `BEGIN IMMEDIATE;
        UPDATE x402_authorizations SET lease=${q(owner)},lease_until=${Date.now() + X402_GLOBAL_BUDGET_MS + 1000}
        WHERE key=${q(key)} AND state='settling' AND lease_until<${Date.now()}; COMMIT;`);
      return get(key).lease === owner;
    },
    release(key, owner) {
      mutate(db, `UPDATE x402_authorizations SET lease_until=0 WHERE key=${q(key)} AND lease=${q(owner)}`);
    },
    failed(key, reason) {
      mutate(db, `UPDATE x402_authorizations SET state='failed',result_json=${q(JSON.stringify({ reason }))} WHERE key=${q(key)} AND state='settling'`);
    },
    cursor(key, nextBlock) {
      mutate(db, `UPDATE x402_authorizations SET scan_cursor=${q(String(nextBlock))} WHERE key=${q(key)} AND CAST(scan_cursor AS INTEGER)<${nextBlock}`);
    },
    transaction(key, tx) {
      mutate(db, `UPDATE x402_authorizations SET transaction_hash=${q(tx.toLowerCase())} WHERE key=${q(key)} AND state='settling'`);
    },
    finalize(key, result) {
      const reference = replayReferenceHash(result.transaction_reference);
      const metadata = { ...JSON.parse(get(key).binding_json), authorization_key: key, rail: 'x402-compatible', provider: 'x402', transaction_reference: result.transaction_reference };
      const json = canonical(metadata);
      const now = new Date().toISOString();
      mutate(db, `BEGIN IMMEDIATE;
        INSERT OR IGNORE INTO replay_claims(bucket,reference_hash,request_hash,metadata_json,first_seen_at,last_seen_at)
        VALUES('payments',${q(reference)},${q(replayReferenceHash(json))},${q(json)},${q(now)},${q(now)});
        UPDATE x402_authorizations SET state='settled',result_json=${q(JSON.stringify(result))},lease_until=0
        WHERE key=${q(key)} AND state='settling' AND EXISTS(SELECT 1 FROM replay_claims WHERE bucket='payments' AND reference_hash=${q(reference)} AND metadata_json=${q(json)});
        COMMIT;`);
      const op = get(key);
      if (op.state !== 'settled') fail('x402_transaction_replay_conflict', 409);
      return JSON.parse(op.result_json);
    },
  };
}

export function x402TrustedRequirements(payload, expected) {
  const protocols = payload.quote?.payment_requirements?.protocols || [];
  const protocol = protocols.find(item => item.id === 'x402-compatible') || {};
  const trusted = payload.expected || {};
  const network = trusted.x402_network || protocol.network;
  const asset = trusted.x402_asset || protocol.asset;
  const payTo = trusted.x402_pay_to || protocol.pay_to || protocol.payTo;
  if (expected.currency.toUpperCase() !== 'USD') fail('x402_currency_unsupported');
  if (network !== X402_NETWORK || address(asset) !== X402_ASSET.toLowerCase() || !address(payTo)) fail('x402_destination_mismatch');
  const maxTimeoutSeconds = Number(trusted.x402_max_timeout_seconds ?? protocol.max_timeout_seconds ?? 300);
  if (!Number.isInteger(maxTimeoutSeconds) || maxTimeoutSeconds < 30 || maxTimeoutSeconds > 300) fail('x402_requirements_invalid');
  const built = {
    scheme: 'exact', network, amount: (BigInt(expected.amountCents) * 10000n).toString(),
    asset, payTo, maxTimeoutSeconds, extra: { name: 'USDC', version: '2' },
  };
  if (trusted.x402_amount !== undefined && String(trusted.x402_amount) !== built.amount) fail('x402_requirements_invalid');
  if (trusted.x402_payment_requirements && !isDeepStrictEqual(trusted.x402_payment_requirements, built)) fail('x402_requirements_invalid');
  return built;
}
function bindings(payload, expected, requirements) {
  const receipt = payload.payment_receipt || {};
  const binding = {
    network: requirements.network, asset: requirements.asset, pay_to: requirements.payTo,
    amount: requirements.amount, quote_hash: expected.quoteHash,
    payment_contract_hash: expected.paymentContractHash, currency: 'USD', amount_cents: expected.amountCents,
  };
  for (const [key, value] of Object.entries(binding)) {
    const actual = receipt[key];
    if (['asset', 'pay_to'].includes(key) ? address(actual) !== address(value) : String(actual) !== String(value)) fail('x402_receipt_binding_mismatch');
  }
  if (receipt.method !== 'x402-compatible' || receipt.status !== 'authorized' || receipt.x402_version !== 2) fail('x402_receipt_binding_mismatch');
  const encoded = receipt.x402_payment_signature;
  if (typeof encoded !== 'string' || encoded.length > 65536 || encoded.length % 4 || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(encoded)) fail('x402_payment_signature_invalid');
  let paymentPayload;
  try {
    paymentPayload = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(Buffer.from(encoded, 'base64')));
  } catch {
    fail('x402_payment_signature_invalid');
  }
  if (paymentPayload.x402Version !== 2 || !isDeepStrictEqual(paymentPayload.accepted, requirements)) fail('x402_accepted_mismatch');
  const authorization = paymentPayload.payload?.authorization;
  if (!authorization || !address(authorization.from) || address(authorization.to) !== address(requirements.payTo)
      || authorization.value !== requirements.amount || !hash(authorization.nonce)
      || !/^0x[\da-f]+$/i.test(paymentPayload.payload.signature || '')
      || typeof authorization.validAfter !== 'string' || !/^\d+$/.test(authorization.validAfter)
      || typeof authorization.validBefore !== 'string' || !/^\d+$/.test(authorization.validBefore)
      || !Number.isSafeInteger(Number(authorization.validAfter)) || !Number.isSafeInteger(Number(authorization.validBefore))) fail('x402_authorization_invalid');
  const resourceUrl = payload.quote?.payment_requirements?.checkout_endpoint;
  if (typeof resourceUrl !== 'string' || !resourceUrl
      || (paymentPayload.resource !== undefined && paymentPayload.resource?.url !== resourceUrl)) fail('x402_resource_mismatch');
  if (authorization.nonce !== x402AuthorizationNonce(expected.quoteHash, expected.paymentContractHash, resourceUrl)) fail('x402_authorization_nonce_mismatch');
  binding.asset = address(binding.asset);
  binding.pay_to = address(binding.pay_to);
  return { paymentPayload, authorization, binding };
}
const stateAbi = [{ type: 'function', name: 'authorizationState', stateMutability: 'view', inputs: [{ type: 'address', name: 'authorizer' }, { type: 'bytes32', name: 'nonce' }], outputs: [{ type: 'bool' }] }];
const authorizationEvent = { type: 'event', name: 'AuthorizationUsed', inputs: [{ name: 'authorizer', type: 'address', indexed: true }, { name: 'nonce', type: 'bytes32', indexed: true }] };
export function createX402Verifier(config) {
  const inflight = new Map();
  const supported = { checked: null, confirmed: null };
  const capability = enabled => ({
    schema: 'agentcart.verifier_x402_capability.v1', mode: config.mode,
    configured: enabled && x402MissingConfig(config, enabled).length === 0,
    x402_version: 2, scheme: 'exact', asset_transfer_method: 'eip3009',
    networks: [{
      network: X402_NETWORK, chain_id: 84532, rpc_url_configured: Boolean(config.rpc), confirmations: config.confirmations,
      assets: [{ asset: X402_ASSET.toLowerCase(), symbol: 'USDC', eip712_name: 'USDC', eip712_version: '2', decimals: 6, currency: 'USD' }],
    }],
    facilitator: { url: config.facilitator, auth: 'none', supported_checked_at: supported.checked, supported_kind_confirmed: supported.confirmed },
    refunds: 'unsupported',
  });
  async function refresh() {
    if (supported.checked && Date.now() - Date.parse(supported.checked) < 600000) return;
    try {
      const response = await x402Fetch(`${config.facilitator.replace(/\/$/, '')}/supported`, { timeout: Math.min(config.timeout, VERIFY_BUDGET_MS), allowPrivate: config.allowPrivate });
      if (!response.ok) throw new Error('supported failed');
      const data = await response.json();
      supported.confirmed = data.kinds?.some(kind => kind.x402Version === 2 && kind.scheme === 'exact' && kind.network === X402_NETWORK) === true;
    } catch {
      supported.confirmed = false;
    }
    supported.checked = new Date().toISOString();
  }
  async function payment(payload, expected, deadline = Date.now() + X402_GLOBAL_BUDGET_MS) {
    if (config.mode !== 'settle') fail('x402_rail_disabled', 503);
    const requirements = x402TrustedRequirements(payload, expected);
    const bound = bindings(payload, expected, requirements);
    const a = bound.authorization;
    const key = `${X402_NETWORK}:${X402_ASSET.toLowerCase()}:${address(a.from)}:${a.nonce}`;
    const store = x402Store(config.db);
    const prior = store.get(key);
    if (prior && prior.binding_json !== canonical(bound.binding)) fail('x402_authorization_binding_conflict', 409);
    if (prior?.state === 'settled') return JSON.parse(prior.result_json);
    if (prior?.state === 'failed') fail(JSON.parse(prior.result_json).reason, 409);
    const now = Math.floor(Date.now() / 1000);
    if (Number(a.validAfter) > now + 60 || Number(a.validBefore) > now + requirements.maxTimeoutSeconds + 60
        || (!prior && Number(a.validBefore) <= now)) fail('x402_authorization_window_invalid');
    if (inflight.has(key)) return inflight.get(key);
    const task = execute(store, key, prior, requirements, bound, expected, deadline);
    inflight.set(key, task);
    try {
      return await task;
    } finally {
      inflight.delete(key);
    }
  }
  async function execute(store, key, prior, requirements, bound, expected, deadline) {
    const owner = crypto.randomUUID();
    const { paymentPayload, authorization: a, binding } = bound;
    let phaseDeadline = deadline;
    const remaining = max => {
      const ms = Math.min(max, deadline - Date.now(), phaseDeadline - Date.now());
      if (ms <= 0) unconfirmed();
      return ms;
    };
    const client = createPublicClient({
      chain: baseSepolia,
      transport: transport(config.rpc, {
        retryCount: 0, timeout: CONFIRM_BUDGET_MS,
        fetchFn: (url, options) => x402Fetch(url, { ...options, timeout: remaining(CONFIRM_BUDGET_MS), allowPrivate: config.allowPrivate }),
      }),
    });
    function finalize(tx) {
      const settle = { success: true, transaction: tx.toLowerCase(), network: X402_NETWORK, payer: address(a.from) };
      return store.finalize(key, {
        ok: true, rail: 'x402-compatible', provider: 'x402', amount_cents: expected.amountCents, currency: 'USD',
        quote_hash: expected.quoteHash, payment_contract_hash: expected.paymentContractHash,
        network: X402_NETWORK, asset: X402_ASSET.toLowerCase(), pay_to: address(requirements.payTo),
        amount: requirements.amount, payer_address: address(a.from), transaction_reference: settle.transaction,
        settlement_reference: settle.transaction, real_settlement_verified: true,
        x402_settle_response: settle, payment_response_header: 'PAYMENT-RESPONSE',
        payment_response_header_value: Buffer.from(JSON.stringify(settle)).toString('base64'),
      });
    }
    async function confirm(tx) {
      if (!hash(tx)) unconfirmed();
      phaseDeadline = Math.min(deadline, Date.now() + CONFIRM_BUDGET_MS);
      try {
        const receipt = await client.getTransactionReceipt({ hash: tx });
        const latest = await client.getBlockNumber({ cacheTime: 0 });
        if (latest - receipt.blockNumber + 1n < BigInt(config.confirmations)) unconfirmed();
        const logs = receipt.logs || [];
        const auth = logs.some(log => address(log.address) === X402_ASSET.toLowerCase()
          && log.topics?.[0]?.toLowerCase() === AUTHORIZATION_USED_TOPIC
          && log.topics?.[1]?.toLowerCase() === topicAddress(a.from) && log.topics?.[2]?.toLowerCase() === a.nonce);
        // A facilitator's transaction alone is not evidence about this nonce.
        if (!auth) unconfirmed();
        const transfer = logs.some(log => address(log.address) === X402_ASSET.toLowerCase()
          && log.topics?.[0]?.toLowerCase() === TRANSFER_TOPIC
          && log.topics?.[1]?.toLowerCase() === topicAddress(a.from)
          && log.topics?.[2]?.toLowerCase() === topicAddress(requirements.payTo)
          && /^0x[\da-f]+$/i.test(log.data) && BigInt(log.data) === BigInt(requirements.amount));
        if (receipt.status !== 'success' || !transfer) {
          store.failed(key, 'x402_settlement_transfer_missing');
          fail('x402_settlement_transfer_missing');
        }
        return finalize(tx);
      } finally {
        phaseDeadline = deadline;
      }
    }
    async function reconcile() {
      const current = store.get(key);
      if (current.transaction_hash) {
        try {
          return await confirm(current.transaction_hash);
        } catch (error) {
          if (typeof error.code === 'string' && error.code.startsWith('x402_') && error.retryable !== true) throw error;
          // Receipt may still be pending; search the nonce rather than trusting the facilitator hash.
        }
      }
      const used = await client.readContract({ address: X402_ASSET, abi: stateAbi, functionName: 'authorizationState', args: [a.from, a.nonce] });
      if (!used) {
        const latest = await client.getBlockNumber({ cacheTime: 0 });
        const depth = BigInt(config.confirmations);
        if (latest < depth) unconfirmed();
        const confirmedBlockNumber = latest - depth;
        const confirmedBlock = await client.getBlock({ blockNumber: confirmedBlockNumber });
        if (confirmedBlock.timestamp >= BigInt(current.valid_before)) {
          const usedAtConfirmedBlock = await client.readContract({
            address: X402_ASSET, abi: stateAbi, functionName: 'authorizationState',
            args: [a.from, a.nonce], blockNumber: confirmedBlockNumber,
          });
          if (usedAtConfirmedBlock) unconfirmed();
          store.failed(key, 'x402_authorization_expired');
          fail('x402_authorization_expired');
        }
        return null;
      }
      const latest = await client.getBlockNumber({ cacheTime: 0 });
      let cursor = BigInt(current.scan_cursor);
      while (cursor <= latest) {
        remaining(CONFIRM_BUDGET_MS);
        const end = cursor + LOG_CHUNK_BLOCKS - 1n < latest ? cursor + LOG_CHUNK_BLOCKS - 1n : latest;
        const logs = await client.getLogs({
          address: X402_ASSET, fromBlock: cursor, toBlock: end, event: authorizationEvent,
          args: { authorizer: a.from, nonce: a.nonce },
        });
        if (logs.length) {
          store.transaction(key, logs[0].transactionHash);
          return confirm(logs[0].transactionHash);
        }
        // Do not skip an unconfirmed tip: it can still change on a later RPC read.
        const safeNext = end + 1n - BigInt(config.confirmations);
        if (safeNext > cursor) store.cursor(key, safeNext);
        cursor = end + 1n;
      }
      unconfirmed();
    }
    async function facilitator(endpoint) {
      const response = await x402Fetch(`${config.facilitator.replace(/\/$/, '')}/${endpoint}`, {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ x402Version: 2, paymentPayload, paymentRequirements: requirements }),
        timeout: remaining(endpoint === 'verify' ? Math.min(config.timeout, VERIFY_BUDGET_MS) : config.timeout),
        allowPrivate: config.allowPrivate,
      });
      if (!response.ok) fail('x402_facilitator_unavailable', 502, true);
      return response.json();
    }
    async function verify(previouslySubmitted) {
      const verified = await facilitator('verify');
      if (verified.isValid === true && (!verified.payer || address(verified.payer) === address(a.from))) return null;
      if (previouslySubmitted) {
        const resolved = await reconcile();
        if (resolved) return resolved;
        unconfirmed();
      }
      fail('x402_verify_invalid');
    }
    async function settle() {
      let response;
      try {
        response = await facilitator('settle');
      } catch {
        // Every unsuccessful/ambiguous submission is recovered by chain evidence.
      }
      if (hash(response?.transaction)) store.transaction(key, response.transaction);
      return response;
    }
    let acquired = false;
    try {
      // Capture a fixed chain reference before any possible submission.
      const op = prior || store.reserve(key, binding, Number(a.validBefore), await client.getBlockNumber({ cacheTime: 0 }));
      acquired = store.acquire(key, owner);
      if (!acquired) {
        while (Date.now() < deadline - 500) {
          const current = store.get(key);
          if (current.state === 'settled') return JSON.parse(current.result_json);
          if (current.state === 'failed') fail(JSON.parse(current.result_json).reason, 409);
          const resolved = await reconcile();
          if (resolved) return resolved;
          if (store.acquire(key, owner)) {
            acquired = true;
            break;
          }
          await new Promise(resolve => setTimeout(resolve, 50));
        }
        if (!acquired) unconfirmed();
      }
      const previouslySubmitted = Boolean(op.lease);
      if (previouslySubmitted) {
        const resolved = await reconcile();
        if (resolved) return resolved;
      }
      if (Math.floor(Date.now() / 1000) >= op.valid_before) {
        const resolved = await reconcile();
        if (resolved) return resolved;
        unconfirmed();
      }
      const recovered = await verify(previouslySubmitted);
      if (recovered) return recovered;
      const settled = await settle();
      if (settled?.success === true && settled.network === X402_NETWORK
          && (!settled.payer || address(settled.payer) === address(a.from)) && hash(settled.transaction)) {
        try {
          return await confirm(settled.transaction);
        } catch (error) {
          if (typeof error.code === 'string' && error.code.startsWith('x402_') && error.retryable !== true) throw error;
        }
      }
      const resolved = await reconcile();
      if (resolved) return resolved;
      unconfirmed();
    } catch (error) {
      protocolError(error);
    } finally {
      if (acquired) {
        // Finalization already clears the lease. Cleanup failures must not hide success
        // or replace the retryable error; an unreleased lease expires automatically.
        try {
          store.release(key, owner);
        } catch {
          // The bounded durable lease is the fallback for SQLite contention.
        }
      }
    }
  }
  return { capability, refresh, payment };
}
