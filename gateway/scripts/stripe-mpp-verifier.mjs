#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";

import Stripe from "stripe";
import { Challenge, Receipt } from "mppx";
import { Mppx, stripe as mppStripe } from "mppx/server";

const host = process.env.STRIPE_MPP_VERIFIER_BIND || "127.0.0.1";
const port = Number(process.env.STRIPE_MPP_VERIFIER_PORT || "4260");
const stripeSecretKey = (
  process.env.STRIPE_SANDBOX_SECRET_KEY ||
  process.env.STRIPE_SECRET_KEY ||
  ""
).trim();
const stripeProfileId = (process.env.STRIPE_PROFILE_ID || process.env.AGENTCART_STRIPE_PROFILE_ID || "").trim();
const mppSecretKey = (process.env.MPP_SECRET_KEY || "").trim();
const verifierToken = (process.env.AGENTCART_PAYMENT_VERIFIER_TOKEN || "").trim();
const replayStorePath = (
  process.env.AGENTCART_VERIFIER_REPLAY_STORE_PATH ||
  process.env.STRIPE_MPP_REPLAY_STORE_PATH ||
  ""
).trim();
const replayStoreLockTimeoutMs = Number(process.env.AGENTCART_VERIFIER_REPLAY_LOCK_TIMEOUT_MS || "5000");
const requireDurableReplayStore = envFlag(process.env.AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY);
const defaultCurrency = (process.env.STRIPE_MPP_CURRENCY || "eur").trim().toLowerCase();
const paymentMethodTypes = (process.env.STRIPE_MPP_PAYMENT_METHOD_TYPES || "card,link")
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);

const stripeClient = stripeSecretKey
  ? new Stripe(stripeSecretKey, { apiVersion: "2026-02-25.preview" })
  : null;
const memoryReplayStore = blankReplayStore();

function envFlag(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").trim().toLowerCase());
}

function jsonResponse(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body, null, 2) + "\n", {
    status,
    headers: {
      "cache-control": "no-store",
      "content-type": "application/json; charset=utf-8",
      ...headers,
    },
  });
}

function missingConfig() {
  const missing = [];
  if (!stripeSecretKey) missing.push("STRIPE_SANDBOX_SECRET_KEY");
  if (!stripeProfileId) missing.push("STRIPE_PROFILE_ID");
  if (!mppSecretKey) missing.push("MPP_SECRET_KEY");
  if (!verifierToken) missing.push("AGENTCART_PAYMENT_VERIFIER_TOKEN");
  if (requireDurableReplayStore && !replayStorePath) {
    missing.push("AGENTCART_VERIFIER_REPLAY_STORE_PATH");
  }
  return missing;
}

function readiness() {
  const missing = missingConfig();
  const replay = replayStoreDiagnostics();
  const ok = missing.length === 0 && !replay.error;
  return {
    ok,
    service: "agentcart-stripe-mpp-verifier",
    mode: "sandbox",
    endpoints: {
      health: `http://${host}:${port}/health`,
      challenge: `http://${host}:${port}/stripe-mpp/challenge`,
      paid: `http://${host}:${port}/stripe-mpp/paid`,
      verify: `http://${host}:${port}/agentcart/verify`,
    },
    stripe_profile_id: stripeProfileId || null,
    default_currency: defaultCurrency,
    payment_method_types: paymentMethodTypes,
    token_required: verifierToken !== "",
    replay_store: replay.label,
    replay_store_kind: replay.kind,
    replay_store_required: requireDurableReplayStore,
    replay_store_durable: replay.durable,
    replay_store_locking: replay.locking,
    replay_store_counts: replay.counts,
    replay_store_error: replay.error,
    missing,
  };
}

function requireReady() {
  const status = readiness();
  if (!status.ok) {
    return jsonResponse(
      {
        ok: false,
        error: "Stripe MPP verifier is not configured.",
        missing: status.missing,
        replay_store_required: status.replay_store_required,
        replay_store_durable: status.replay_store_durable,
        replay_store_error: status.replay_store_error,
      },
      503,
    );
  }
  return null;
}

async function parseJsonRequest(request) {
  const text = await request.text();
  if (!text.trim()) return {};
  try {
    return JSON.parse(text);
  } catch {
    throw Object.assign(new Error("Request body must be valid JSON."), { status: 400 });
  }
}

function bearerToken(request) {
  const header = request.headers.get("authorization") || "";
  const match = header.match(/^Bearer\s+(.+)$/i);
  return match?.[1]?.trim() || "";
}

function requireVerifierToken(request) {
  if (!verifierToken) return null;
  const supplied = bearerToken(request);
  const expected = Buffer.from(verifierToken);
  const actual = Buffer.from(supplied);
  if (actual.length !== expected.length || !crypto.timingSafeEqual(actual, expected)) {
    return jsonResponse({ ok: false, error: "Unauthorized verifier request." }, 401);
  }
  return null;
}

function normalizeRail(value) {
  const rail = String(value || "").trim().toLowerCase().replaceAll("_", "-");
  if (rail === "stripe" || rail === "stripe-card" || rail === "stripe-card-mpp") return "stripe-card-mpp";
  if (rail === "tempo" || rail === "tempo-mpp" || rail === "mpp") return "tempo-mpp";
  return rail || "stripe-card-mpp";
}

function blankReplayStore() {
  return {
    schema: "agentcart.verifierReplay.v1",
    payments: {},
    refund_requests: {},
    refunds: {},
  };
}

function replayStoreLabel() {
  return replayStorePath || "memory";
}

function replayStoreLockPath() {
  return replayStorePath ? `${replayStorePath}.lock` : "";
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function normalizeReplayStore(raw) {
  const store = raw && typeof raw === "object" ? raw : {};
  return {
    schema: "agentcart.verifierReplay.v1",
    payments: store.payments && typeof store.payments === "object" ? store.payments : {},
    refund_requests:
      store.refund_requests && typeof store.refund_requests === "object" ? store.refund_requests : {},
    refunds: store.refunds && typeof store.refunds === "object" ? store.refunds : {},
  };
}

function loadReplayStore() {
  if (!replayStorePath) return memoryReplayStore;
  if (!fs.existsSync(replayStorePath)) return blankReplayStore();
  try {
    return normalizeReplayStore(JSON.parse(fs.readFileSync(replayStorePath, "utf8")));
  } catch (error) {
    throw Object.assign(new Error(`Could not read verifier replay store: ${error.message}`), { status: 500 });
  }
}

function saveReplayStore(store) {
  if (!replayStorePath) return;
  const directory = path.dirname(replayStorePath);
  fs.mkdirSync(directory, { recursive: true });
  const tempPath = `${replayStorePath}.${process.pid}.${Date.now()}.tmp`;
  fs.writeFileSync(tempPath, `${JSON.stringify(store, null, 2)}\n`, { mode: 0o600 });
  fs.renameSync(tempPath, replayStorePath);
}

async function acquireReplayStoreLock() {
  if (!replayStorePath) {
    return () => {};
  }
  const lockPath = replayStoreLockPath();
  const started = Date.now();
  fs.mkdirSync(path.dirname(replayStorePath), { recursive: true });
  while (true) {
    try {
      const fd = fs.openSync(lockPath, "wx", 0o600);
      fs.writeFileSync(fd, JSON.stringify({ pid: process.pid, created_at: new Date().toISOString() }));
      fs.closeSync(fd);
      return () => {
        try {
          fs.unlinkSync(lockPath);
        } catch {
          // Ignore stale cleanup races; the next claimant can recover.
        }
      };
    } catch (error) {
      if (error?.code !== "EEXIST") {
        throw Object.assign(new Error(`Could not acquire verifier replay lock: ${error.message}`), { status: 500 });
      }
      try {
        const stat = fs.statSync(lockPath);
        if (Date.now() - stat.mtimeMs > replayStoreLockTimeoutMs) {
          fs.unlinkSync(lockPath);
          continue;
        }
      } catch (statError) {
        if (statError?.code !== "ENOENT") {
          throw Object.assign(new Error(`Could not inspect verifier replay lock: ${statError.message}`), {
            status: 500,
          });
        }
      }
      if (Date.now() - started > replayStoreLockTimeoutMs) {
        throw Object.assign(new Error("Timed out acquiring verifier replay lock."), { status: 503 });
      }
      await sleep(25 + Math.floor(Math.random() * 50));
    }
  }
}

async function withReplayStoreMutation(mutator) {
  const release = await acquireReplayStoreLock();
  try {
    const store = loadReplayStore();
    const result = mutator(store);
    if (result?.save !== false) {
      saveReplayStore(store);
    }
    return result;
  } finally {
    release();
  }
}

function replayStoreDiagnostics() {
  const diagnostics = {
    label: replayStoreLabel(),
    kind: replayStorePath ? "file" : "memory",
    durable: Boolean(replayStorePath),
    locking: replayStorePath ? "lockfile" : "process",
    counts: null,
    error: null,
  };
  try {
    const store = loadReplayStore();
    diagnostics.counts = {
      payments: Object.keys(store.payments || {}).length,
      refund_requests: Object.keys(store.refund_requests || {}).length,
      refunds: Object.keys(store.refunds || {}).length,
    };
  } catch (error) {
    diagnostics.error = error.message;
  }
  return diagnostics;
}

async function claimReplayReference(bucket, reference, metadata = {}) {
  const key = String(reference || "").trim();
  if (!key) {
    return { ok: false, response: jsonResponse({ ok: false, error: "replay reference is required." }, 400) };
  }
  return withReplayStoreMutation((store) => {
    if (!store[bucket] || typeof store[bucket] !== "object") store[bucket] = {};
    if (store[bucket][key]) {
      return {
        ok: false,
        save: false,
        response: jsonResponse(
          {
            ok: false,
            error: `${bucket.slice(0, -1).replace("_", " ")} reference has already been used.`,
            replay_reference: key,
            first_seen_at: store[bucket][key].first_seen_at || null,
          },
          409,
        ),
      };
    }
    store[bucket][key] = {
      ...metadata,
      first_seen_at: new Date().toISOString(),
    };
    return { ok: true };
  });
}

function expectedFromPayload(payload) {
  const expected = payload.expected && typeof payload.expected === "object" ? payload.expected : {};
  const quote = payload.quote && typeof payload.quote === "object" ? payload.quote : {};
  const receipt =
    payload.payment_receipt && typeof payload.payment_receipt === "object" ? payload.payment_receipt : {};
  const quoteHash = String(payload.quote_hash || expected.quote_hash || quote.quote_hash || receipt.quote_hash || "");
  const amountCents = Number(expected.amount_cents ?? quote.total_cents ?? receipt.amount_cents);
  const currency = String(expected.currency || quote.currency || receipt.currency || defaultCurrency).toLowerCase();
  const merchantId = String(expected.merchant_id || quote.merchant_id || receipt.merchant_id || "");
  const rail = normalizeRail(expected.rail || receipt.rail || receipt.method || receipt.provider || payload.rail);
  const profileId = String(expected.stripe_profile_id || stripeProfileId);
  const tempoNetwork = String(expected.tempo_network || "").trim();
  const tempoRecipient = String(expected.tempo_recipient || "").trim().toLowerCase();
  const requirements =
    quote.payment_requirements && typeof quote.payment_requirements === "object" ? quote.payment_requirements : {};
  const verification =
    requirements.verification && typeof requirements.verification === "object" ? requirements.verification : {};
  const suppliedContractHashes = [
    payload.payment_contract_hash,
    expected.payment_contract_hash,
    requirements.payment_contract_hash,
    verification.payment_contract_hash,
    receipt.payment_contract_hash,
    receipt.contract_hash,
  ]
    .map((value) => String(value || "").trim())
    .filter(Boolean);
  const uniqueContractHashes = new Set(suppliedContractHashes);
  if (!Number.isSafeInteger(amountCents) || amountCents <= 0) {
    throw Object.assign(new Error("expected.amount_cents must be a positive integer."), { status: 400 });
  }
  if (!currency) {
    throw Object.assign(new Error("expected.currency is required."), { status: 400 });
  }
  if (!quoteHash) {
    throw Object.assign(new Error("quote_hash is required."), { status: 400 });
  }
  if (!["stripe-card-mpp", "tempo-mpp"].includes(rail)) {
    throw Object.assign(new Error(`Unsupported rail for this verifier: ${rail}`), { status: 400 });
  }
  if (rail === "stripe-card-mpp" && profileId !== stripeProfileId) {
    throw Object.assign(new Error("Stripe profile id does not match verifier configuration."), { status: 400 });
  }
  if (uniqueContractHashes.size > 1) {
    throw Object.assign(new Error("payment_contract_hash values do not match."), { status: 400 });
  }
  return {
    amountCents,
    currency,
    merchantId,
    paymentContractHash: suppliedContractHashes[0] || "",
    profileId,
    quoteHash,
    rail,
    tempoNetwork,
    tempoRecipient,
  };
}

function assertReceiptMatchesExpected(receipt, expected) {
  if (!receipt || typeof receipt !== "object") return;
  const amount = receipt.amount_cents;
  if (amount !== undefined && Number(amount) !== expected.amountCents) {
    throw Object.assign(new Error("payment_receipt.amount_cents does not match expected.amount_cents."), { status: 400 });
  }
  const currency = String(receipt.currency || "").trim();
  if (currency && currency.toUpperCase() !== expected.currency.toUpperCase()) {
    throw Object.assign(new Error("payment_receipt.currency does not match expected.currency."), { status: 400 });
  }
  const quoteHash = String(receipt.quote_hash || "").trim();
  if (quoteHash && quoteHash !== expected.quoteHash) {
    throw Object.assign(new Error("payment_receipt.quote_hash does not match expected quote_hash."), { status: 400 });
  }
  const receiptRail = normalizeRail(receipt.rail || receipt.method || receipt.provider || "");
  if (receiptRail && receiptRail !== expected.rail) {
    throw Object.assign(new Error("payment_receipt rail does not match expected.rail."), { status: 400 });
  }
  const receiptContractHash = String(receipt.payment_contract_hash || receipt.contract_hash || "").trim();
  if (receiptContractHash && expected.paymentContractHash && receiptContractHash !== expected.paymentContractHash) {
    throw Object.assign(new Error("payment_receipt.payment_contract_hash does not match expected payment_contract_hash."), {
      status: 400,
    });
  }
  const receiptProfile = String(receipt.stripe_profile_id || "").trim();
  if (expected.rail === "stripe-card-mpp" && receiptProfile && receiptProfile !== expected.profileId) {
    throw Object.assign(new Error("payment_receipt.stripe_profile_id does not match expected Stripe profile."), {
      status: 400,
    });
  }
}

function decimalAmountToCents(value) {
  const raw = String(value ?? "").trim();
  const match = raw.match(/^(\d+)(?:\.(\d{1,6}))?$/);
  if (!match) return NaN;
  const whole = Number(match[1]);
  const fraction = (match[2] || "").padEnd(2, "0").slice(0, 2);
  return whole * 100 + Number(fraction);
}

function centsToDecimal(cents) {
  return `${Math.floor(cents / 100)}.${String(cents % 100).padStart(2, "0")}`;
}

function tempoProofFromReceipt(receipt) {
  if (!receipt || typeof receipt !== "object") return {};
  const proof =
    receipt.external_value_proof && typeof receipt.external_value_proof === "object"
      ? receipt.external_value_proof
      : receipt;
  const body = proof.body && typeof proof.body === "object" ? proof.body : {};
  const proofReceipt =
    proof.payment_receipt && typeof proof.payment_receipt === "object" ? proof.payment_receipt : {};
  return { proof, body, proofReceipt };
}

function chargeOptions(expected) {
  return {
    amount: String(expected.amountCents),
    currency: expected.currency,
    decimals: 2,
    description: `AgentCart quote ${expected.quoteHash.slice(0, 12)}`,
    externalId: expected.quoteHash,
    metadata: {
      agentcart_quote_hash: expected.quoteHash,
      agentcart_payment_contract_hash: expected.paymentContractHash,
      agentcart_merchant_id: expected.merchantId,
      agentcart_rail: expected.rail,
    },
    networkId: expected.profileId,
    paymentMethodTypes,
  };
}

function createMppx(expected) {
  if (!stripeClient) throw Object.assign(new Error("Stripe client is not configured."), { status: 503 });
  return Mppx.create({
    methods: [
      mppStripe.charge({
        client: stripeClient,
        ...chargeOptions(expected),
      }),
    ],
    realm: "agentcart-stripe-mpp-verifier",
    secretKey: mppSecretKey,
  });
}

function providerErrorClass(error) {
  const type = String(error?.type || error?.name || "").toLowerCase();
  const code = String(error?.code || "").toLowerCase();
  const status = Number(error?.statusCode || error?.status || 0);
  if (code === "rate_limit" || type.includes("ratelimit")) return "provider_rate_limited";
  if (status >= 500) return "provider_unavailable";
  if (type.includes("authentication")) return "provider_authentication_failed";
  if (type.includes("permission")) return "provider_permission_denied";
  if (type.includes("invalidrequest")) return "provider_invalid_request";
  if (type.includes("card")) return "provider_card_error";
  if (type.includes("api")) return "provider_api_error";
  return "provider_error";
}

function providerErrorResponse(operation, error) {
  const classification = providerErrorClass(error);
  const status = Number(error?.statusCode || error?.status || 0);
  const retryable = classification === "provider_rate_limited" || classification === "provider_unavailable";
  return jsonResponse(
    {
      ok: false,
      error: `${operation} failed at payment provider.`,
      provider: "stripe",
      provider_error_class: classification,
      provider_status: status || null,
      provider_code: error?.code || null,
      request_id: error?.requestId || null,
      retryable,
    },
    retryable ? 502 : 400,
  );
}

function credentialFromReceipt(receipt) {
  if (!receipt || typeof receipt !== "object") return "";
  for (const key of [
    "authorization",
    "mpp_authorization",
    "payment_authorization",
    "credential",
    "mpp_credential",
  ]) {
    const value = receipt[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

async function challenge(payload) {
  const ready = requireReady();
  if (ready) return ready;
  const expected = expectedFromPayload(payload);
  const mppx = createMppx(expected);
  const challenge = await mppx.challenge.stripe.charge(chargeOptions(expected));
  return jsonResponse({
    ok: true,
    rail: "stripe-card-mpp",
    quote_hash: expected.quoteHash,
    payment_contract_hash: expected.paymentContractHash || undefined,
    amount_cents: expected.amountCents,
    currency: expected.currency.toUpperCase(),
    stripe_profile_id: stripeProfileId,
    challenge,
    www_authenticate: Challenge.serialize(challenge),
    authorization_hint: "Use link-cli to create a test SPT and retry with Authorization: Payment ...",
  });
}

async function verifyPayment(payload) {
  const ready = requireReady();
  if (ready) return ready;
  const expected = expectedFromPayload(payload);
  const receipt =
    payload.payment_receipt && typeof payload.payment_receipt === "object" ? payload.payment_receipt : {};
  assertReceiptMatchesExpected(receipt, expected);
  if (expected.rail === "tempo-mpp") {
    return verifyTempoFxPayment(receipt, expected);
  }
  const authorization = credentialFromReceipt(receipt);
  if (!authorization) {
    return jsonResponse(
      {
        ok: false,
        error: "payment_receipt.authorization or payment_receipt.credential is required.",
      },
      400,
    );
  }
  const mppx = createMppx(expected);
  let mppReceipt;
  try {
    mppReceipt = await mppx.verifyCredential(authorization, { request: chargeOptions(expected) });
  } catch (error) {
    return providerErrorResponse("Stripe/card MPP credential verification", error);
  }
  const transactionReference = String(mppReceipt.reference || "").trim();
  const replayClaim = await claimReplayReference("payments", transactionReference, {
    provider: "stripe",
    rail: "stripe-card-mpp",
    amount_cents: expected.amountCents,
    currency: expected.currency.toUpperCase(),
    quote_hash: expected.quoteHash,
    payment_contract_hash: expected.paymentContractHash || undefined,
    stripe_profile_id: stripeProfileId,
  });
  if (!replayClaim.ok) return replayClaim.response;
  return jsonResponse({
    ok: true,
    provider: "stripe",
    rail: "stripe-card-mpp",
    amount_cents: expected.amountCents,
    currency: expected.currency.toUpperCase(),
    quote_hash: expected.quoteHash,
    payment_contract_hash: expected.paymentContractHash || undefined,
    stripe_profile_id: stripeProfileId,
    transaction_reference: transactionReference,
    mpp_receipt: mppReceipt,
    real_settlement_verified: true,
  });
}

async function verifyTempoFxPayment(receipt, expected) {
  const { proof, body, proofReceipt } = tempoProofFromReceipt(receipt);
  const provider = String(proof.provider || body.provider || receipt.provider || "").trim();
  const state = String(proof.state || body.state || "").trim();
  if (provider !== "tempo_mpp") {
    return jsonResponse({ ok: false, error: "Tempo proof is required for tempo-mpp verification." }, 400);
  }
  if (state && state !== "succeeded") {
    return jsonResponse({ ok: false, error: `Tempo proof state is ${state}.` }, 400);
  }
  const settlementAmount = body.amount ?? proof.amount ?? proof.receipt?.amount;
  const settlementAmountCents = decimalAmountToCents(settlementAmount);
  if (settlementAmountCents !== expected.amountCents) {
    return jsonResponse(
      {
        ok: false,
        error: "Tempo proof amount does not match the demo FX policy.",
        expected_settlement_amount: centsToDecimal(expected.amountCents),
        actual_settlement_amount: settlementAmount || null,
      },
      400,
    );
  }
  const network = String(proof.network || body.network || proofReceipt.network || expected.tempoNetwork || "");
  if (expected.tempoNetwork && network && network !== expected.tempoNetwork) {
    return jsonResponse({ ok: false, error: "Tempo proof network does not match merchant configuration." }, 400);
  }
  const recipient = String(body.recipient || proof.recipient || "").trim().toLowerCase();
  if (expected.tempoRecipient && recipient && recipient !== expected.tempoRecipient) {
    return jsonResponse({ ok: false, error: "Tempo proof recipient does not match merchant configuration." }, 400);
  }
  const transactionReference = String(
    proof.transaction_reference ||
      proof.reference ||
      proofReceipt.reference ||
      body.transaction_reference ||
      body.reference ||
      "",
  ).trim();
  if (!transactionReference) {
    return jsonResponse({ ok: false, error: "Tempo proof transaction reference is required." }, 400);
  }
  const replayClaim = await claimReplayReference("payments", transactionReference, {
    provider: "tempo_mpp",
    rail: "tempo-mpp",
    amount_cents: expected.amountCents,
    currency: expected.currency.toUpperCase(),
    quote_hash: expected.quoteHash,
    payment_contract_hash: expected.paymentContractHash || undefined,
    network: expected.tempoNetwork || network,
    recipient: expected.tempoRecipient || recipient,
  });
  if (!replayClaim.ok) return replayClaim.response;
  return jsonResponse({
    ok: true,
    provider: "tempo_mpp",
    rail: "tempo-mpp",
    amount_cents: expected.amountCents,
    currency: expected.currency.toUpperCase(),
    quote_hash: expected.quoteHash,
    payment_contract_hash: expected.paymentContractHash || undefined,
    network: expected.tempoNetwork || network,
    recipient: expected.tempoRecipient || recipient,
    transaction_reference: transactionReference,
    real_settlement_verified: false,
    fx: {
      mode: "demo_fixed_1_1",
      quote_currency: expected.currency.toUpperCase(),
      settlement_asset: "pathUSD",
      settlement_amount: centsToDecimal(expected.amountCents),
      note: "Hackathon demo verifier: numeric 1:1 EUR-to-pathUSD testnet binding, not production FX settlement.",
    },
  });
}

async function verifyRefund(payload) {
  const ready = requireReady();
  if (ready) return ready;
  if (!stripeClient) return jsonResponse({ ok: false, error: "Stripe client is not configured." }, 503);
  const expected = payload.expected && typeof payload.expected === "object" ? payload.expected : {};
  const refund = payload.refund && typeof payload.refund === "object" ? payload.refund : {};
  const amountCents = Number(expected.amount_cents ?? refund.amount_cents);
  const currency = String(expected.currency || refund.currency || defaultCurrency).toUpperCase();
  const quoteHash = String(expected.quote_hash || payload.quote_hash || "");
  const originalReference = String(
    expected.original_transaction_reference ||
      payload.original_transaction_reference ||
      payload.order?.transaction_reference ||
      payload.order?.payment_verification?.transaction_reference ||
      "",
  );
  const rail = normalizeRail(refund.rail || payload.rail || "stripe-card-mpp");
  if (rail !== "stripe-card-mpp") {
    return jsonResponse({ ok: false, error: `Unsupported refund rail: ${rail}` }, 400);
  }
  if (!Number.isSafeInteger(amountCents) || amountCents <= 0) {
    return jsonResponse({ ok: false, error: "refund.amount_cents must be a positive integer." }, 400);
  }
  if (!originalReference) {
    return jsonResponse({ ok: false, error: "original transaction reference is required." }, 400);
  }
  const requestedReference = String(refund.requested_reference || payload.requested_reference || "").trim();
  if (!requestedReference) {
    return jsonResponse({ ok: false, error: "refund.requested_reference is required." }, 400);
  }
  let refundResult;
  try {
    refundResult = await stripeClient.refunds.create(
      {
        amount: amountCents,
        metadata: {
          agentcart_quote_hash: quoteHash,
          agentcart_refund_reason: String(refund.reason || "AgentCart refund"),
        },
        payment_intent: originalReference,
        reason: "requested_by_customer",
      },
      {
        idempotencyKey: requestedReference,
      },
    );
  } catch (error) {
    return providerErrorResponse("Stripe/card refund", error);
  }
  const requestClaim = await claimReplayReference("refund_requests", requestedReference, {
    provider: "stripe",
    rail,
    amount_cents: amountCents,
    currency,
    quote_hash: quoteHash,
    original_transaction_reference: originalReference,
    refund_reference: refundResult.id,
  });
  if (!requestClaim.ok) return requestClaim.response;
  const refundClaim = await claimReplayReference("refunds", refundResult.id, {
    provider: "stripe",
    rail: "stripe-card-mpp",
    amount_cents: amountCents,
    currency,
    quote_hash: quoteHash,
    original_transaction_reference: originalReference,
    requested_reference: requestedReference,
  });
  if (!refundClaim.ok) return refundClaim.response;
  return jsonResponse({
    ok: true,
    provider: "stripe",
    rail: "stripe-card-mpp",
    amount_cents: amountCents,
    currency,
    quote_hash: quoteHash,
    original_transaction_reference: originalReference,
    refund_reference: refundResult.id,
    refund_status: refundResult.status,
    real_refund_verified: true,
  });
}

async function paid(request, payload) {
  const ready = requireReady();
  if (ready) return ready;
  const expected = expectedFromPayload(payload);
  if (expected.rail !== "stripe-card-mpp") {
    return jsonResponse({ ok: false, error: `Unsupported paid endpoint rail: ${expected.rail}` }, 400);
  }
  const mppx = createMppx(expected);
  const result = await mppx.compose([
    "stripe/charge",
    chargeOptions(expected),
  ])(request);
  if (result.status === 402) return result.challenge;
  return result.withReceipt(
    jsonResponse({
      ok: true,
    rail: "stripe-card-mpp",
    quote_hash: expected.quoteHash,
    payment_contract_hash: expected.paymentContractHash || undefined,
    amount_cents: expected.amountCents,
    currency: expected.currency.toUpperCase(),
      stripe_profile_id: stripeProfileId,
    }),
  );
}

async function handler(request) {
  const url = new URL(request.url);
  if (request.method === "GET" && (url.pathname === "/" || url.pathname === "/health")) {
    const status = readiness();
    return jsonResponse(status, status.ok ? 200 : 503);
  }
  if (request.method !== "POST") {
    return jsonResponse({ ok: false, error: "not found" }, 404);
  }
  const payload = await parseJsonRequest(request);
  if (url.pathname === "/stripe-mpp/challenge") return challenge(payload);
  if (url.pathname === "/stripe-mpp/paid") return paid(request, payload);
  if (url.pathname === "/agentcart/verify") {
    const unauthorized = requireVerifierToken(request);
    if (unauthorized) return unauthorized;
    const operation = String(payload.operation || "payment").toLowerCase();
    if (operation === "payment" || operation === "charge") return verifyPayment(payload);
    if (operation === "refund") return verifyRefund(payload);
    return jsonResponse({ ok: false, error: `Unsupported operation: ${operation}` }, 400);
  }
  return jsonResponse({ ok: false, error: "not found" }, 404);
}

async function sendResponse(response, nodeResponse) {
  nodeResponse.statusCode = response.status;
  response.headers.forEach((value, key) => {
    nodeResponse.setHeader(key, value);
  });
  nodeResponse.end(Buffer.from(await response.arrayBuffer()));
}

const server = http.createServer(async (request, response) => {
  try {
    const body = await new Promise((resolve, reject) => {
      const chunks = [];
      request.on("data", (chunk) => chunks.push(chunk));
      request.on("end", () => resolve(Buffer.concat(chunks)));
      request.on("error", reject);
    });
    const url = `http://${request.headers.host}${request.url}`;
    const headers = new Headers();
    for (const [name, value] of Object.entries(request.headers)) {
      if (Array.isArray(value)) {
        for (const entry of value) headers.append(name, entry);
      } else if (value !== undefined) {
        headers.set(name, value);
      }
    }
    const fetchRequest = new Request(url, {
      body: ["GET", "HEAD"].includes(request.method || "GET") ? undefined : body,
      headers,
      method: request.method,
    });
    await sendResponse(await handler(fetchRequest), response);
  } catch (error) {
    await sendResponse(
      jsonResponse(
        {
          ok: false,
          error: error instanceof Error ? error.message : String(error),
        },
        Number.isInteger(error?.status) ? error.status : 500,
      ),
      response,
    );
  }
});

server.listen(port, host, () => {
  const status = readiness();
  console.log(`AgentCart Stripe MPP verifier listening on http://${host}:${port}`);
  console.log(JSON.stringify({ ...status, token_required: Boolean(verifierToken) }, null, 2));
});
